#!/usr/bin/env python3
"""
Levy Lab RAG Pipeline
---------------------
Indexes lab files (notebooks, scripts, docs) into a ChromaDB vector store,
then answers questions using retrieved context + Qwen3-Coder via Ollama.

Usage:
  python lab_rag.py index /path/to/lab/project/folder
  python lab_rag.py query "What preprocessing was used on the H&E images?"
  python lab_rag.py chat   (interactive mode)
"""

import os
import sys
import json
import hashlib
import chromadb
import ollama

# === CONFIGURATION ===
CHROMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "levy_lab"
EMBED_MODEL = "nomic-embed-text"    # Small embedding model (pulled via Ollama)
CHAT_MODEL = "qwen3-coder"          # Main LLM for answering
CHUNK_SIZE = 800                     # Characters per chunk
CHUNK_OVERLAP = 100                  # Overlap between chunks
TOP_K = 5                           # Number of chunks to retrieve per query

# File types we can index
INDEXABLE_EXTENSIONS = {
    ".py", ".ipynb", ".md", ".txt", ".sh", ".yaml", ".yml",
    ".json", ".csv", ".tsv", ".r", ".R", ".cfg", ".conf", ".toml"
}


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

        chunk_id = hashlib.md5(f"{filepath}:{start}".encode()).hexdigest()

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

def index_directory(directory):
    """Walk a directory, read all indexable files, chunk them, embed, store."""
    directory = os.path.abspath(directory)
    print(f"\n=== Indexing: {directory} ===\n")

    # Collect all files
    all_files = []
    for root, dirs, files in os.walk(directory):
        # Skip hidden dirs and common junk
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                   {"__pycache__", "node_modules", ".git", ".ipynb_checkpoints"}]

        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in INDEXABLE_EXTENSIONS:
                all_files.append(os.path.join(root, fname))

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

    # Delete existing collection if re-indexing
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # Embed and store in batches
    BATCH_SIZE = 50
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        # Get embeddings from Ollama
        embeddings = []
        for text in texts:
            response = ollama.embed(model=EMBED_MODEL, input=text)
            embeddings.append(response["embeddings"][0])

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        print(f"  Indexed batch {i // BATCH_SIZE + 1}/{(len(all_chunks) - 1) // BATCH_SIZE + 1}")

    print(f"\n=== Done! {len(all_chunks)} chunks indexed into ChromaDB ===")
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
    q_embed = ollama.embed(model=EMBED_MODEL, input=question)["embeddings"][0]

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
    response = ollama.chat(
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
        if len(sys.argv) < 3:
            print("Usage: python lab_rag.py index /path/to/directory")
            sys.exit(1)
        # Pull embedding model if not already present
        print("Ensuring embedding model is available...")
        try:
            ollama.pull(EMBED_MODEL)
        except Exception:
            print(f"Warning: Could not pull {EMBED_MODEL}. Make sure Ollama is running.")
        index_directory(sys.argv[2])

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
