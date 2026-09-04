"""
baseline_retrieval.py - sparse retrieval baselines on the PanCyto corpus.

Answers the question the agent evaluation could not: is 92% Hit@3 good, or is
the task easy? Without a baseline the number is uninterpretable.

Rebuilds the corpus with lab_rag.py's exact ingestion and chunking so the
comparison is apples-to-apples, then ranks chunks three ways:

  bm25_text  BM25 over chunk text only. The fair comparison to the dense
             retriever, which embeds chunk text and never sees the path
             (lab_rag.py:388 embeds c["text"]; the path lives in metadata).
  bm25_path  BM25 over "path + chunk text". Tests the hypothesis that both
             dense misses were exact-token failures on filenames.
  filename   Token overlap against the file path alone. The dumb baseline:
             if this scores well the retrieval task is trivial.

Read-only. Emits run logs in analyze.py's schema; computes no metrics itself.
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5

# Matches the corpus documented in tasks_pancyto.jsonl.
INDEX_SUBDIRS = ["scripts", "configs", "notebooks"]
EXTENSIONS = {".py", ".ipynb", ".yaml", ".yml", ".sh", ".sbatch"}
SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git"}


# --- ingestion: copied from lab_rag.py so the corpus is identical ---

def read_notebook(filepath):
    try:
        with open(filepath, "r", errors="ignore") as f:
            nb = json.load(f)
        parts = []
        for i, cell in enumerate(nb.get("cells", [])):
            ctype = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            if ctype == "markdown":
                parts.append(f"[Markdown Cell {i+1}]\n{source}")
            elif ctype == "code":
                parts.append(f"[Code Cell {i+1}]\n{source}")
                for out in cell.get("outputs", []):
                    if "text" in out:
                        parts.append(f"[Output {i+1}]\n{''.join(out['text'])[:500]}")
        return "\n\n".join(parts)
    except Exception:
        return ""


def read_file(filepath):
    if os.path.splitext(filepath)[1].lower() == ".ipynb":
        return read_notebook(filepath)
    try:
        with open(filepath, "r", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def chunk_text(text, filepath):
    """Byte-identical chunk boundaries to lab_rag.chunk_text."""
    chunks = []
    if not text.strip():
        return chunks
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        last_newline = chunk.rfind("\n", CHUNK_SIZE // 2)
        if last_newline > 0:
            chunk = chunk[:last_newline]
            end = start + last_newline
        chunks.append({"text": chunk.strip(), "source": filepath, "start_char": start})
        start = end - CHUNK_OVERLAP
        if start < 0:
            start = 0
        if end >= len(text):
            break
    return chunks


def build_corpus(root):
    chunks = []
    files = 0
    for sub in INDEX_SUBDIRS:
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() not in EXTENSIONS:
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                text = read_file(full)
                got = chunk_text(text, rel)
                if got:
                    files += 1
                    chunks.extend(got)
    return chunks, files


# --- tokenization ---

_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

def tokenize(text):
    """Lowercase alphanumeric tokens, with camelCase split into subtokens.

    Code identifiers carry meaning in their parts (set_rgb_stats -> set, rgb,
    stats), so a tokenizer that keeps them whole would understate BM25.
    """
    out = []
    for raw in _SPLIT.split(text):
        if not raw:
            continue
        for piece in _CAMEL.split(raw):
            piece = piece.lower()
            if piece:
                out.append(piece)
    return out


# --- BM25 Okapi, stdlib only ---

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avglen = sum(self.lens) / len(self.lens) if self.lens else 0.0
        n = len(docs)
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        # Robertson/Sparck-Jones idf with the +1 guard, so a term appearing in
        # every document scores 0 rather than going negative.
        self.idf = {
            t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()
        }

    def scores(self, query_tokens):
        out = [0.0] * len(self.docs)
        for i, doc in enumerate(self.docs):
            if not doc:
                continue
            dl = self.lens[i]
            s = 0.0
            for t in query_tokens:
                f = doc.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avglen)
                )
            out[i] = s
        return out


def filename_scores(chunks, query_tokens):
    """Token overlap between the query and the file path. The dumb baseline."""
    q = set(query_tokens)
    return [len(q & set(tokenize(c["source"]))) * 1.0 for c in chunks]


def load_tasks(path):
    tasks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tasks.append(json.loads(line))
    return tasks


def rank(scores, chunks, k):
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    return [i for i in order[:k] if scores[i] > 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    chunks, nfiles = build_corpus(args.corpus)
    print(f"corpus: {nfiles} files, {len(chunks)} chunks", file=sys.stderr)

    text_tokens = [tokenize(c["text"]) for c in chunks]
    path_tokens = [tokenize(c["source"]) + t for c, t in zip(chunks, text_tokens)]

    arms = {
        "bm25_text": BM25(text_tokens).scores,
        "bm25_path": BM25(path_tokens).scores,
        "filename": lambda q: filename_scores(chunks, q),
    }

    tasks = load_tasks(args.tasks)
    os.makedirs(args.outdir, exist_ok=True)

    for arm, scorer in arms.items():
        out = os.path.join(args.outdir, f"pancyto_{arm}.jsonl")
        with open(out, "w") as fh:
            for t in tasks:
                q = tokenize(t["question"])
                sc = scorer(q)
                top = rank(sc, chunks, TOP_K)
                rec = {
                    "task_id": t["id"],
                    "arm": arm,
                    "question": t["question"],
                    # Retrieval-only arm: no generation, so no prose and no
                    # cited paths. Scoring must use the chunk-level metrics.
                    "answer": "",
                    "sources": [chunks[i]["source"] for i in top],
                    "cited_paths": [],
                    "abstained": False,
                    "retrieval_enabled": True,
                    "latency_s": 0.0,
                    "chunks": [
                        {
                            "source": chunks[i]["source"],
                            "start_char": chunks[i]["start_char"],
                            "score": round(sc[i], 4),
                        }
                        for i in top
                    ],
                }
                fh.write(json.dumps(rec) + "\n")
        print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
