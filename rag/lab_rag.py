#!/usr/bin/env python3
"""
Levy Lab RAG Pipeline
---------------------
Indexes lab files (notebooks, scripts, docs) into a ChromaDB vector store,
then answers questions using retrieved context + Qwen3-Coder via Ollama.

Usage:
  python lab_rag.py index /path/to/lab/project/folder
  python lab_rag.py index /path/to/folder --rebuild   (force full re-index)
  python lab_rag.py query "What preprocessing was used on the H&E images?"
  python lab_rag.py chat   (interactive mode)

Environment:
  LAB_RAG_CHROMA_DIR      Where the vector database lives. On Discovery this
                          should be scratch, not home and not /dartfs/rc.
  LAB_RAG_EXTENSIONS      Comma-separated file types to index, e.g. ".py,.ipynb".
                          Defaults to the full set in DEFAULT_EXTENSIONS.
  LAB_RAG_SKIP_DIRS       Extra directory names never descended into.
  LAB_RAG_MAX_DIR_ENTRIES Directories larger than this are skipped whole
                          (default 5000), so dataset folders do not dominate
                          index time.
  LAB_RAG_EMBED_HOST      Ollama endpoint for embeddings. Point at a CPU-only
                          instance so the chat model stays GPU-resident.
  LAB_RAG_CHAT_HOST       Ollama endpoint for generation. Defaults to local.
"""

import os
import sys
import json
import hashlib
import chromadb
import ollama

# === CONFIGURATION ===
# Storage location for the vector database.
# On Discovery, point this at scratch: /dartfs/rc is full and lab policy
# prohibits storing data in home directories. Scratch gives 5TB per user but
# purges files after 45 days, so anything durable needs a periodic copy.
#   export LAB_RAG_CHROMA_DIR=/dartfs-hpc/scratch/$USER/levy_lab_index
CHROMA_DIR = os.environ.get(
    "LAB_RAG_CHROMA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db"),
)

COLLECTION_NAME = "levy_lab"
EMBED_MODEL = "nomic-embed-text"    # Small embedding model (pulled via Ollama)
CHAT_MODEL = "qwen3-coder"          # Main LLM for answering
CHUNK_SIZE = 800                     # Characters per chunk
CHUNK_OVERLAP = 100                  # Overlap between chunks
TOP_K = 5                           # Number of chunks to retrieve per query
EMBED_BATCH_SIZE = 50               # Chunks embedded per Ollama call

# File types we can index. Override to narrow the corpus, e.g. code only:
#   export LAB_RAG_EXTENSIONS=".py,.ipynb"
DEFAULT_EXTENSIONS = {
    ".py", ".ipynb", ".md", ".txt", ".sh", ".yaml", ".yml",
    ".json", ".csv", ".tsv", ".r", ".R", ".cfg", ".conf", ".toml"
}

if os.environ.get("LAB_RAG_EXTENSIONS"):
    INDEXABLE_EXTENSIONS = {
        ext.strip() if ext.strip().startswith(".") else "." + ext.strip()
        for ext in os.environ["LAB_RAG_EXTENSIONS"].split(",")
        if ext.strip()
    }
else:
    INDEXABLE_EXTENSIONS = set(DEFAULT_EXTENSIONS)

# Directories never descended into. Add project-specific ones with:
#   export LAB_RAG_SKIP_DIRS="data,checkpoints"
DEFAULT_SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".ipynb_checkpoints",
    ".venv", "venv", "site-packages", "chroma_db",
}
SKIP_DIRS = set(DEFAULT_SKIP_DIRS)
if os.environ.get("LAB_RAG_SKIP_DIRS"):
    SKIP_DIRS |= {
        d.strip() for d in os.environ["LAB_RAG_SKIP_DIRS"].split(",") if d.strip()
    }

# A directory holding more entries than this is skipped whole. Dataset folders
# (the PCam corpus has ~150k images in one directory) otherwise dominate index
# time: enumerating them costs ~26s per run to find nothing indexable.
MAX_DIR_ENTRIES = int(os.environ.get("LAB_RAG_MAX_DIR_ENTRIES", "5000"))

# Serving the embedding model and the chat model from one Ollama instance costs
# a full model swap per query. Under exclusive-mode GPU allocation only one
# model may be resident, so every question evicts the 18GB chat model to load
# the embedder, then reloads it: measured at 118s for a cold query.
#
# Pointing embeddings at a second, CPU-only Ollama instance leaves the chat
# model permanently resident on the GPU. Deliberately the *same* embedding
# model, just on CPU, so vectors are unchanged and existing indexes stay valid.
# A different embedding library would silently invalidate every stored vector.
#
#   export LAB_RAG_EMBED_HOST=http://localhost:11435
EMBED_HOST = os.environ.get("LAB_RAG_EMBED_HOST")
CHAT_HOST = os.environ.get("LAB_RAG_CHAT_HOST")

# Falls back to the ollama module itself, so a single-server setup still works
# unchanged and needs no configuration.
embed_client = ollama.Client(host=EMBED_HOST) if EMBED_HOST else ollama
chat_client = ollama.Client(host=CHAT_HOST) if CHAT_HOST else ollama


# === FILE READING ===

def read_file(filepath):
    """Read a file and return its text content. Handles notebooks specially."""
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == ".ipynb":
            return read_notebook(filepath)
        elif ext == ".csv" or ext == ".tsv":
            # Only read first 50 lines of data files (headers + sample)
            with open(filepath, "r", errors="ignore") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 50:
                        break
                    lines.append(line)
                return "".join(lines)
        else:
            with open(filepath, "r", errors="ignore") as f:
                return f.read()
    except Exception as e:
        print(f"  Warning: Could not read {filepath}: {e}")
        return ""


def read_notebook(filepath):
    """Extract code and markdown cells from a Jupyter notebook."""
    try:
        with open(filepath, "r", errors="ignore") as f:
            nb = json.load(f)

        cells = nb.get("cells", [])
        text_parts = []

        for i, cell in enumerate(cells):
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))

            if cell_type == "markdown":
                text_parts.append(f"[Markdown Cell {i+1}]\n{source}")
            elif cell_type == "code":
                text_parts.append(f"[Code Cell {i+1}]\n{source}")

                # Include output if it's text
                outputs = cell.get("outputs", [])
                for out in outputs:
                    if "text" in out:
                        output_text = "".join(out["text"])
                        text_parts.append(f"[Output {i+1}]\n{output_text[:500]}")

        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"  Warning: Could not parse notebook {filepath}: {e}")
        return ""


# === CHUNKING ===

def chunk_text(text, filepath, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks, each tagged with source file."""
    chunks = []
    if not text.strip():
        return chunks

    # Split by paragraphs first, then by size
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a newline near the end
        last_newline = chunk.rfind("\n", chunk_size // 2)
        if last_newline > 0:
            chunk = chunk[:last_newline]
            end = start + last_newline

        # Hash includes the chunk text, not just position, so editing a file
        # in place produces new IDs and forces a re-embed. Hashing only
        # path+offset would silently keep stale content in the index.
        chunk_id = hashlib.md5(
            f"{filepath}:{start}:{chunk}".encode()
        ).hexdigest()

        chunks.append({
            "id": chunk_id,
            "text": chunk.strip(),
            "metadata": {
                "source": filepath,
                "start_char": start,
                "filename": os.path.basename(filepath),
            }
        })

        start = end - overlap

    return chunks


# === INDEXING ===

def collect_files(directory, skip_dirs=None, max_entries=None):
    """Find indexable files, without enumerating dataset directories.

    Returns (files, skipped). A directory holding more than `max_entries`
    entries is skipped in full rather than read partially, so a run either
    indexes a directory or does not: no half-indexed corpus, which would make
    results irreproducible. Enumeration stops as soon as the limit is crossed,
    so a 150k-file image folder costs about `max_entries` stats, not 150k.

    Symlinks are not followed, which avoids loops and stops a link inside the
    corpus from pulling in files outside it.
    """
    skip_dirs = SKIP_DIRS if skip_dirs is None else skip_dirs
    max_entries = MAX_DIR_ENTRIES if max_entries is None else max_entries

    files, skipped, stack = [], [], [directory]

    while stack:
        current = stack.pop()
        found, subdirs, count, overflow = [], [], 0, False

        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    count += 1
                    if count > max_entries:
                        overflow = True
                        break
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in skip_dirs:
                                subdirs.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext in INDEXABLE_EXTENSIONS:
                                found.append(entry.path)
                    except OSError:
                        continue
        except OSError as exc:
            print(f"  Warning: could not read {current}: {exc}")
            continue

        if overflow:
            skipped.append(current)
            continue

        files.extend(found)
        stack.extend(subdirs)

    return files, skipped


def stored_ids_for_source(collection, source):
    """Chunk IDs currently stored for one source file."""
    try:
        got = collection.get(where={"source": source}, include=[])
    except Exception:
        return set()
    return set(got.get("ids") or [])


def stored_sources(collection):
    """Every source file currently represented in the collection."""
    try:
        got = collection.get(include=["metadatas"])
    except Exception:
        return set()
    return {
        m.get("source")
        for m in (got.get("metadatas") or [])
        if m and m.get("source")
    }


def index_directory(directory, rebuild=False):
    """Walk a directory, read all indexable files, chunk them, embed, store.

    Existing chunks are skipped unless `rebuild` is set, so re-indexing an
    unchanged corpus costs nothing.
    """
    directory = os.path.abspath(directory)
    print(f"\n=== Indexing: {directory} ===\n")

    all_files, skipped_dirs = collect_files(directory)

    for path in skipped_dirs:
        print(
            f"  Skipped {os.path.relpath(path, directory)}: over {MAX_DIR_ENTRIES} "
            f"entries. Raise LAB_RAG_MAX_DIR_ENTRIES to index it anyway."
        )

    print(f"Found {len(all_files)} indexable files.\n")

    if not all_files:
        print("No files found to index. Check the directory path.")
        return

    # Read and chunk all files
    all_chunks = []
    for fpath in all_files:
        rel_path = os.path.relpath(fpath, directory)
        print(f"  Reading: {rel_path}")
        text = read_file(fpath)
        if text:
            # Prepend filename context to help the model
            text = f"FILE: {rel_path}\n\n{text}"
            chunks = chunk_text(text, rel_path)
            all_chunks.extend(chunks)

    print(f"\nTotal chunks: {len(all_chunks)}")

    if not all_chunks:
        print("No content extracted. Files may be empty or unreadable.")
        return

    # Initialize ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    if rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("Rebuild requested: dropped existing collection.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # Reconcile per source file. Chunk IDs include content, so if a file's
    # stored IDs exactly match its current ones it is unchanged and skipped.
    # If they differ the file was edited, and its old chunks are dropped first
    # so the update replaces stale content instead of sitting beside it.
    by_source = {}
    for c in all_chunks:
        by_source.setdefault(c["metadata"]["source"], []).append(c)

    pending = []
    unchanged, updated, added = 0, 0, 0
    for source, chunks in by_source.items():
        stored = stored_ids_for_source(collection, source)
        current = {c["id"] for c in chunks}
        if stored and stored == current:
            unchanged += 1
            continue
        if stored:
            collection.delete(ids=list(stored))
            updated += 1
        else:
            added += 1
        pending.extend(chunks)

    # Drop files that vanished from the corpus, so the index never cites a
    # file that no longer exists.
    removed = stored_sources(collection) - set(by_source)
    for source in removed:
        collection.delete(where={"source": source})
    if removed:
        print(f"Removed {len(removed)} file(s) no longer in the corpus")

    print(f"Files: {unchanged} unchanged, {updated} modified, {added} new")

    if not pending:
        print("\n=== Nothing to embed. Collection is up to date. ===")
        print(f"Collection holds: {collection.count()} chunks")
        print(f"Database stored at: {CHROMA_DIR}")
        return

    print(f"To embed: {len(pending)} chunks\n")

    total_batches = (len(pending) - 1) // EMBED_BATCH_SIZE + 1
    for i in range(0, len(pending), EMBED_BATCH_SIZE):
        batch = pending[i:i + EMBED_BATCH_SIZE]
        texts = [c["text"] for c in batch]

        # One Ollama call for the whole batch. Embedding per chunk in a loop
        # costs one HTTP round trip each and dominates indexing time.
        response = embed_client.embed(model=EMBED_MODEL, input=texts)
        embeddings = response["embeddings"]

        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Embedding count mismatch: sent {len(texts)}, got {len(embeddings)}"
            )

        collection.add(
            ids=[c["id"] for c in batch],
            embeddings=embeddings,
            documents=texts,
            metadatas=[c["metadata"] for c in batch],
        )

        print(f"  Indexed batch {i // EMBED_BATCH_SIZE + 1}/{total_batches}")

    print(f"\n=== Done! {len(pending)} new chunks indexed into ChromaDB ===")
    print(f"Collection now holds: {collection.count()} chunks")
    print(f"Database stored at: {CHROMA_DIR}")


# === QUERYING ===

def query(question, verbose=True):
    """Retrieve relevant chunks and generate an answer."""
    # Load ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        print("Error: No indexed data found. Run 'python lab_rag.py index <directory>' first.")
        return ""

    # Embed the question
    q_embed = embed_client.embed(model=EMBED_MODEL, input=question)["embeddings"][0]

    # Retrieve top-K similar chunks
    results = collection.query(
        query_embeddings=[q_embed],
        n_results=TOP_K,
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    if verbose:
        print(f"\n--- Retrieved {len(documents)} chunks ---")
        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            print(f"  [{i+1}] {meta['source']} (chars {meta['start_char']}+)")
        print()

    # Build context for the LLM
    context = "\n\n---\n\n".join([
        f"Source: {meta['source']}\n{doc}"
        for doc, meta in zip(documents, metadatas)
    ])

    prompt = f"""You are the Levy Lab Copilot, an AI assistant for digital pathology researchers at Dartmouth.
Answer the question below using ONLY the provided context from lab files. If the context doesn't contain enough information, say so.
Always cite which file(s) your answer comes from.

CONTEXT FROM LAB FILES:
{context}

QUESTION: {question}

ANSWER:"""

    # Send to Qwen3-Coder
    response = chat_client.chat(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    answer = response["message"]["content"]

    if verbose:
        print(f"Levy Lab Copilot:\n{answer}\n")

    return answer


# === INTERACTIVE CHAT ===

def chat():
    """Interactive chat loop with RAG retrieval."""
    print("\n=== Levy Lab Copilot (RAG Mode) ===")
    print("Ask questions about indexed lab files. Type 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        query(question)


# === MAIN ===

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "index":
        args = [a for a in sys.argv[2:] if a != "--rebuild"]
        rebuild = "--rebuild" in sys.argv[2:]
        if not args:
            print("Usage: python lab_rag.py index /path/to/directory [--rebuild]")
            sys.exit(1)
        # Pull embedding model if not already present
        print("Ensuring embedding model is available...")
        try:
            embed_client.pull(EMBED_MODEL)
        except Exception:
            print(f"Warning: Could not pull {EMBED_MODEL}. Make sure Ollama is running.")
        index_directory(args[0], rebuild=rebuild)

    elif command == "query":
        if len(sys.argv) < 3:
            print("Usage: python lab_rag.py query \"your question here\"")
            sys.exit(1)
        query(" ".join(sys.argv[2:]))

    elif command == "chat":
        chat()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
