"""Offline test of lab_rag indexing logic with chromadb/ollama stubbed out.

Verifies:
  1. Embeddings are requested in batches, not one call per chunk.
  2. Re-indexing an unchanged corpus embeds nothing.
  3. Adding a file embeds only the new chunks.
  4. EDITING a file re-embeds it and removes the stale chunks.
  5. Deleting a file prunes it from the index.
  6. --rebuild forces a full re-embed.
"""
import os, sys, types, tempfile, shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- stub ollama ----
ollama = types.ModuleType("ollama")
ollama.embed_calls = []


def _embed(model=None, input=None):
    texts = input if isinstance(input, list) else [input]
    ollama.embed_calls.append(len(texts))
    return {"embeddings": [[0.1, 0.2, 0.3] for _ in texts]}


ollama.embed = _embed
ollama.pull = lambda *a, **k: None
ollama.chat = lambda *a, **k: {"message": {"content": "stub"}}
sys.modules["ollama"] = ollama

# ---- stub chromadb ----
chromadb = types.ModuleType("chromadb")


class FakeCollection:
    def __init__(self):
        self.docs = {}   # id -> text
        self.meta = {}   # id -> metadata

    def _match(self, where):
        if not where:
            return list(self.docs)
        return [
            i for i, m in self.meta.items()
            if all(m.get(k) == v for k, v in where.items())
        ]

    def get(self, ids=None, where=None, include=None):
        sel = [i for i in ids if i in self.docs] if ids is not None else self._match(where)
        out = {"ids": sel}
        if include and "metadatas" in include:
            out["metadatas"] = [self.meta[i] for i in sel]
        return out

    def add(self, ids=None, embeddings=None, documents=None, metadatas=None):
        for i, d, m in zip(ids, documents, metadatas):
            self.docs[i] = d
            self.meta[i] = m

    def delete(self, ids=None, where=None):
        target = ids if ids is not None else self._match(where)
        for i in target:
            self.docs.pop(i, None)
            self.meta.pop(i, None)

    def count(self):
        return len(self.docs)

    def sources(self):
        return {m["source"] for m in self.meta.values()}


class FakeClient:
    _collections = {}

    def __init__(self, path=None):
        self.path = path

    def get_or_create_collection(self, name=None, metadata=None):
        return FakeClient._collections.setdefault(name, FakeCollection())

    def delete_collection(self, name):
        FakeClient._collections.pop(name, None)


chromadb.PersistentClient = FakeClient
sys.modules["chromadb"] = chromadb

sys.path.insert(0, os.path.join(REPO, "rag"))
import lab_rag as L

work = tempfile.mkdtemp()


def write(name, text):
    with open(os.path.join(work, name), "w") as f:
        f.write(text)


def coll():
    return FakeClient._collections["levy_lab"]


write("a.py", "def alpha():\n    return 1\n" * 60)
write("b.md", "# Notes\nsome documentation here\n" * 40)

print("=== 1: initial index ===")
ollama.embed_calls = []
L.index_directory(work)
calls_1 = list(ollama.embed_calls)
chunks_1 = sum(calls_1)
assert chunks_1 > 0
assert len(calls_1) < chunks_1, "BATCHING FAILED: one call per chunk"
print(f"OK: {chunks_1} chunks in {len(calls_1)} call(s)\n")

print("=== 2: re-index unchanged ===")
ollama.embed_calls = []
L.index_directory(work)
assert ollama.embed_calls == [], f"re-embedded {sum(ollama.embed_calls)}"
print("OK: embedded nothing\n")

print("=== 3: add a file ===")
write("c.py", "def gamma():\n    pass\n" * 30)
ollama.embed_calls = []
L.index_directory(work)
assert 0 < sum(ollama.embed_calls) < chunks_1
print(f"OK: embedded only {sum(ollama.embed_calls)} new chunks\n")

print("=== 4: EDIT a file (the stale-content bug) ===")
before = coll().count()
write("b.md", "# Notes\nCOMPLETELY DIFFERENT CONTENT NOW\n" * 40)
ollama.embed_calls = []
L.index_directory(work)
assert sum(ollama.embed_calls) > 0, "edited file was NOT re-embedded"
stored = " ".join(
    t for i, t in coll().docs.items() if coll().meta[i]["source"] == "b.md"
)
assert "COMPLETELY DIFFERENT" in stored, "new content missing"
assert "some documentation here" not in stored, "STALE CONTENT STILL INDEXED"
print(f"OK: re-embedded, stale chunks gone (count {before} -> {coll().count()})\n")

print("=== 5: delete a file ===")
os.remove(os.path.join(work, "c.py"))
ollama.embed_calls = []
L.index_directory(work)
assert "c.py" not in coll().sources(), "deleted file still in index"
print(f"OK: pruned, sources now {sorted(coll().sources())}\n")

print("=== 6: --rebuild ===")
ollama.embed_calls = []
L.index_directory(work, rebuild=True)
assert sum(ollama.embed_calls) == coll().count()
print(f"OK: re-embedded all {sum(ollama.embed_calls)} chunks\n")

shutil.rmtree(work)
print("ALL CHECKS PASSED")
