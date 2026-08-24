#!/usr/bin/env python3
"""Rebuild the vector index for the demo corpus, into THIS repo.

Uses lab_rag's chunking and embedding so the index matches what its query path
expects. lab_rag.py is not modified: CHROMA_DIR is overridden as a runtime
attribute in this process only, leaving the team lead's repo pristine.

Run this after changing anything in demo/corpus/. A stale index does not error,
it just quietly makes the agent blind to the new files.

    python demo/reindex.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "rag"))
sys.path.insert(0, os.path.expanduser("~/labagent/rag"))

TARGET = os.path.join(REPO, "rag", "chroma_db")
CORPUS = os.path.join(HERE, "corpus")


def main() -> int:
    import lab_rag

    lab_rag.CHROMA_DIR = TARGET
    lab_rag.index_directory(CORPUS)

    os.environ["LAB_CHROMA_DIR"] = TARGET
    import lab_query

    drift = lab_query.index_drift(CORPUS)
    if drift["missing_from_index"] or drift["missing_from_disk"]:
        print("\nWARNING: index still does not match the corpus:")
        print(f"  missing from index: {drift['missing_from_index']}")
        print(f"  missing from disk:  {drift['missing_from_disk']}")
        return 1
    print("\nIndex matches the corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
