"""
lexical_baseline.py — BM25 keyword search over the same corpus, no LLM.

WHY THIS EXISTS
---------------
The first question any reviewer asks is: "your assistant found the QC notebook —
would `grep` have found it too?" If plain keyword search does just as well, then
for that task the assistant is a slower, more expensive, hallucination-prone way
to do what Ctrl+F already does.

Both the methods referee and the literature review flagged the absence of this
comparison independently. The referee called it "the cheapest experiment in the
study and the one whose absence most threatens your contribution."

It is not a product. It is a control: ~150 lines, no model, no embeddings, no
dependencies. Its only job is to make the assistant's numbers mean something.

WHAT IT DOES AND DOESN'T DO
---------------------------
Returns ranked FILES for a query. It cannot answer questions, summarize, or
synthesize across files — so on "locate" tasks it is a fair fight, and on
"comprehend" tasks it structurally cannot compete. That asymmetry IS the expected
finding, and reporting it per-category is more informative than a single headline
number.

Implements Okapi BM25 from scratch (stdlib only) rather than pulling in rank-bm25,
so the baseline has no install burden and its behaviour is fully inspectable.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# Standard Okapi BM25 parameters. k1 controls term-frequency saturation, b
# controls length normalization. These are the conventional defaults; stating
# them matters because a tuned baseline and an untuned one are different claims.
K1 = 1.5
B = 0.75

INDEXABLE_EXTENSIONS = {
    ".py", ".ipynb", ".md", ".txt", ".sh", ".yaml", ".yml",
    ".json", ".csv", ".tsv", ".r", ".R", ".cfg", ".conf", ".toml",
}

_TOKEN = re.compile(r"[a-z0-9_]+")

# Words carrying no retrieval signal. Deliberately minimal — an aggressive stop
# list would be tuning the baseline, and an untuned baseline is the honest
# comparator.
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "for", "on",
    "and", "or", "what", "which", "where", "how", "why", "this", "that", "it",
    "i", "we", "you", "can", "do", "does", "did", "used", "use", "with", "from",
}


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


def read_indexable(path: str) -> str:
    """Read a file to text, matching lab_rag's handling so the corpora match.

    Notebooks are unpacked to cell source and CSV/TSV truncated to 50 lines,
    exactly as the assistant's indexer does. If the baseline saw different text
    the comparison would be unfair in an uncontrolled direction.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".ipynb":
            with open(path, "r", errors="ignore") as handle:
                notebook = json.load(handle)
            parts = []
            for cell in notebook.get("cells", []):
                if cell.get("cell_type") in ("markdown", "code"):
                    parts.append("".join(cell.get("source", [])))
            return "\n\n".join(parts)
        if ext in (".csv", ".tsv"):
            with open(path, "r", errors="ignore") as handle:
                return "".join(line for i, line in enumerate(handle) if i < 50)
        with open(path, "r", errors="ignore") as handle:
            return handle.read()
    except Exception:
        return ""


@dataclass
class BM25Index:
    """A BM25 index over whole files."""

    paths: List[str]
    term_freqs: List[Counter]
    lengths: List[int]
    doc_freq: Dict[str, int]
    avg_length: float

    @property
    def n_docs(self) -> int:
        return len(self.paths)

    def _idf(self, term: str) -> float:
        # Robertson/Sparck-Jones IDF with the +0.5 smoothing, floored at 0 so a
        # term appearing in nearly every document cannot contribute negatively.
        n_q = self.doc_freq.get(term, 0)
        if n_q == 0:
            return 0.0
        return max(
            0.0,
            math.log((self.n_docs - n_q + 0.5) / (n_q + 0.5) + 1.0),
        )

    def score(self, query: str) -> List[Tuple[str, float]]:
        """Rank every document. Returns (path, score), best first."""
        terms = tokenize(query)
        scored: List[Tuple[str, float]] = []
        for index, path in enumerate(self.paths):
            freqs = self.term_freqs[index]
            length = self.lengths[index] or 1
            total = 0.0
            for term in terms:
                freq = freqs.get(term, 0)
                if not freq:
                    continue
                numerator = freq * (K1 + 1)
                denominator = freq + K1 * (1 - B + B * length / (self.avg_length or 1))
                total += self._idf(term) * numerator / denominator
            if total > 0:
                scored.append((path, total))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored

    def search(self, query: str, top_k: int = 5) -> List[str]:
        return [path for path, _score in self.score(query)[:top_k]]


def build_index(root: str) -> BM25Index:
    """Index every indexable file under `root`, keyed by relative path."""
    root = os.path.abspath(root)
    paths, term_freqs, lengths = [], [], []
    doc_freq: Dict[str, int] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"__pycache__", "node_modules", ".git", ".ipynb_checkpoints"}
        ]
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in INDEXABLE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            # Include the path itself: a human searching for "qc notebook" would
            # match the filename, and excluding it would handicap the baseline.
            tokens = tokenize(rel.replace("/", " ") + "\n" + read_indexable(full))
            if not tokens:
                continue
            counts = Counter(tokens)
            paths.append(rel)
            term_freqs.append(counts)
            lengths.append(len(tokens))
            for term in counts:
                doc_freq[term] = doc_freq.get(term, 0) + 1

    avg = (sum(lengths) / len(lengths)) if lengths else 0.0
    return BM25Index(paths, term_freqs, lengths, doc_freq, avg)


def answer_record(index: BM25Index, question: str, top_k: int = 5) -> dict:
    """Produce a run record in the same shape the assistant produces.

    `answer` is deliberately not prose: BM25 cannot write one. Saying so
    explicitly in the record keeps anyone from later scoring it as if it had
    tried and failed to answer.
    """
    import time

    started = time.monotonic()
    ranked = index.search(question, top_k=top_k)
    elapsed = time.monotonic() - started
    return {
        "arm": "bm25",
        "question": question,
        "answer": (
            "[BM25 baseline — keyword ranking only, no generated answer] "
            + ("Top files: " + ", ".join(ranked) if ranked else "No matching files.")
        ),
        "sources": ranked,
        "chunks": [{"source": p, "start_char": None, "distance": None} for p in ranked],
        # BM25 does not "cite" — it ranks. Treating its ranking as citations would
        # let it be scored for hallucination, which it structurally cannot do.
        "cited_paths": [],
        "abstained": not ranked,
        "latency_s": round(elapsed, 4),
        "retrieval_enabled": True,
        "personalized": False,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print('Usage: python lexical_baseline.py <corpus_dir> "<question>"')
        raise SystemExit(1)
    idx = build_index(sys.argv[1])
    print(f"Indexed {idx.n_docs} files, avg length {idx.avg_length:.0f} tokens\n")
    for rank, (path, score) in enumerate(idx.score(" ".join(sys.argv[2:]))[:5], 1):
        print(f"  {rank}. {path:<40} {score:.3f}")
