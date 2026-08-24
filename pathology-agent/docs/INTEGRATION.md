# How to land this in the team repo

Everything here is **additive**. Nothing modifies `rag/lab_rag.py`, so it will not
conflict with Varun's in-flight work connecting RAG to the agent.

Verified against `varunkal/AI-Agent-for-Digital-Pathology` @ `ac31d22`
(clone inspected 2026-07-29). 59 tests passing locally.

## What to copy in

```
rag/lab_query.py              # retrieval that returns its sources
rag/safety.py                 # enforced read-only guards
evaluation/tasks.py
evaluation/analyze.py
evaluation/run_eval.py
evaluation/tasks.template.jsonl
evaluation/README.md
tests/test_all.py
tests/fixtures/               # synthetic; proves the pipeline, not a real task set
requirements.txt
docs/DESIGN_DOC.md
docs/EVALUATION_PROTOCOL.md
```

Open it as a PR rather than pushing to `main`, so Varun and Zarif can review the
safety posture before it lands.

## Bug to fix in the repo (one command)

The repo root contains a **broken git submodule**: a gitlink named
`AI-Agent-for-Digital-Pathology` (mode `160000`, pointing at commit `5db94ad` —
the repo referencing itself) with **no `.gitmodules`**. A fresh clone produces an
empty directory of that name, and `git submodule update` fails.

Confirmed with `git ls-files -s`:
```
160000 5db94ade78fa9a24d10bda3dc0e0218781430d52 0  AI-Agent-for-Digital-Pathology
```

Fix:
```bash
git rm --cached AI-Agent-for-Digital-Pathology
rmdir AI-Agent-for-Digital-Pathology 2>/dev/null
git commit -m "Remove self-referencing gitlink (broken submodule, no .gitmodules)"
```

## Two things worth raising with Varun

**1. Re-indexing wipes the previous index.** `index_directory()` calls
`client.delete_collection(COLLECTION_NAME)` before creating a new one, so indexing
project B destroys project A's index. For a lab-wide assistant covering several
project folders this needs either incremental adds or per-project collections.

**2. Embedding is one HTTP call per chunk.** `BATCH_SIZE = 50` batches only the
ChromaDB insert; the embed step is a per-chunk loop:
```python
for text in texts:
    response = ollama.embed(model=EMBED_MODEL, input=text)
```
With `CHUNK_SIZE = 800`, a real lab directory produces thousands of chunks, so
indexing will be slow. Batching the embed call is the fix.

Neither is a correctness bug and neither blocks the evaluation — but both are
worth a sentence in the paper's limitations if they aren't fixed.

**Not a bug:** I initially suspected `chunk_text()` could loop forever when
`rfind` finds no newline. Traced it — `rfind("\n", CHUNK_SIZE // 2)` starts at 400,
so any hit advances `start` by ≥300, and a miss advances by 700. It terminates.

## One coupling to be aware of

`lab_query.py` reproduces the prompt from `lab_rag.query()` so results from the two
code paths stay comparable. That prompt is a local string inside his function, so
it can't be imported. **If Varun edits his prompt, the two will silently drift.**
The clean fix is for him to lift it to a module-level constant
(`PROMPT_TEMPLATE = ...`) that `lab_query` can import. Worth asking.

Runtime config does *not* have this problem: `lab_query.config()` reads
`CHROMA_DIR`, `COLLECTION_NAME`, `EMBED_MODEL`, `CHAT_MODEL` and `TOP_K` from
`lab_rag` when it's importable, and there's a test pinning the offline fallbacks.

## Running it on Discovery

```bash
./startup.sh                       # Ollama + qwen3-coder on a GPU node
pip install -r requirements.txt
python rag/lab_rag.py index /path/to/project        # build the index
python evaluation/analyze.py --make-manifest /path/to/project > file_manifest.txt
```

Then the Slack bot, with sources shown in replies:
```bash
export LEVYBOY_BACKEND=rag
export PYTHONPATH=/path/to/repo/rag:$PYTHONPATH
python app.py
```

## Still open — needs a human

- **Case study subject** unconfirmed. A retrospective study needs a *completed*
  analysis with recoverable ground truth. Ask Dr. Levy.
- **Success thresholds** in the design doc are proposed, not agreed. Get sign-off
  *before* collecting data.
- **Read-only vs. write-capable** unresolved: qwen-code can write and execute
  (that's how `hello_lab.py` was made), which exceeds the project's stated
  read-only constraint. `safety.py` provides the mechanism; the team must decide
  the policy.
- **Arm B (generic LLM) needs written approval** before any external query. No
  API client is implemented, deliberately.
- **Springer deadline** for the *BioData Mining* "Uses of Agentic AI in Biodata
  Mining" collection — the page is behind auth; someone has to look it up.
