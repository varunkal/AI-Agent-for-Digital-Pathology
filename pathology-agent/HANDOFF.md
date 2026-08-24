# Handoff — Levy Lab pathology agent

Written 2026-08-03. Every claim below was checked against the working tree, not
recalled. Re-verify before trusting: this file goes stale the moment someone
commits.

## Repo state

Two repos, both local, **neither has a git remote**. Nothing is backed up off
this machine.

| | `~/pathology-agent` | `~/levyboy-slackbot` |
|---|---|---|
| branch | `main` | `main` |
| HEAD | `79b61cd` Let the agent see prior turns of a conversation | `1e90b0f` Remember the conversation, per Slack thread |
| tree | **dirty** | **dirty** |

Uncommitted, and it is real work — the clarifying-question change, tested live
but never committed:

- `pathology-agent/rag/lab_agent.py` — SYSTEM_PROMPT rule for unresolvable
  questions; `is_clarifying_question()`; `AgentResult.asked_for_clarification`
- `pathology-agent/tests/test_all.py` — 3 tests for the above
- `pathology-agent/rag/chroma_db/chroma.sqlite3` — binary churn, see Hacks
- `levyboy-slackbot/agent.py` — trailer logic that suppresses the memory
  warning when the model asked a question instead of answering

## Files created or modified this session

**`pathology-agent/rag/lab_agent.py`** — the agent loop. Gained: `history`
parameter on `run_agent()` (prior conversation turns, validated); the
`used_prior_context` and `asked_for_clarification` result fields;
`is_clarifying_question()` at line 433; a SYSTEM_PROMPT rule telling the model
to ask which thing they mean rather than describe itself.

**`levyboy-slackbot/handlers.py`** — Slack-free bot logic. Gained the
per-thread conversation store (`thread_history`, `remember`, `forget_all`,
`_spoken_part`) and the wiring that passes history into `agent.ask`.

**`levyboy-slackbot/agent.py`** — the router. `ask()` and `_ask_agent()` now
take `history`. The no-tools trailer splits three ways: silent when the model
asked a clarifying question, neutral on a follow-up, `:warning:` only when a
fresh question was answered from model memory.

**`pathology-agent/tests/test_all.py`** — `FakeChat` records `first_messages`;
6 new tests covering history ordering, malformed-history rejection, and
clarification detection boundaries.

**`levyboy-slackbot/test_handlers.py`** — 7 new tests for the thread store;
existing fakes updated for the `history=` kwarg.

**`pathology-agent/RUN_REAL.sh`** — earlier in the session: `OLLAMA_MAX_LOADED_MODELS=2`,
`LEVYBOY_AGENT_TIMEOUT=300`, interpreter pinned.

## Architecture

```
Slack (Socket Mode, outbound WebSocket — no public URL, works behind firewalls)
  └─ app.py ................ thin slack_bolt adapter, no logic
     └─ handlers.py ........ placeholder → answer → edit; owns thread memory
        └─ agent.py ........ ROUTER (this file is in levyboy-slackbot)
           ├─ "help"        static text
           ├─ "trace:"      workflow.trace(), deterministic, <1s
           ├─ "fast:"       lab_query.answer_question(), one retrieval
           └─ default       lab_agent.run_agent()  ← the agent
              │
              └─ loop, ≤8 steps: model picks a tool, tool runs, repeat
                 ├─ search_lab_files → lab_query.retrieve() → ChromaDB
                 ├─ read_file        → safety.PathGuard
                 ├─ trace_pipeline   → workflow.trace()
                 ├─ list_files       → safety.PathGuard.walk_readable()
                 └─ run_python       → safe_exec  (NOT offered; allow_execution=False)
```

The two repos meet at exactly one place: `PYTHONPATH` includes
`~/pathology-agent/rag`, and the Slack bot does `import lab_agent`. Nothing is
copied or vendored.

Data flow for a question: Slack event → strip mention → thread history lookup →
router → agent loop → each model turn gets `[system, ...history, user, ...tool
exchanges]` → answer plus a trail of which tools ran and which files were
touched.

`trace_pipeline` is the load-bearing claim: `workflow.py` parses real file
references out of the corpus and builds the dependency graph itself. The model
only writes prose over a finished structure, so it cannot invent a step.

## Commands that work

Start the bot. Foreground, needs its own terminal, does **not** hot-reload:

```bash
bash ~/pathology-agent/RUN_REAL.sh
```

Tests:

```bash
cd ~/pathology-agent && /opt/anaconda3/bin/python3 -m pytest -q
```

```bash
cd ~/levyboy-slackbot && PYTHONPATH=/Users/avilash/pathology-agent/rag /opt/anaconda3/bin/python3 -m pytest -q
```

Agent from the CLI, no Slack:

```bash
cd ~/pathology-agent/rag && PYTHONPATH=. /opt/anaconda3/bin/python3 lab_agent.py ../demo/corpus "how was results/figure3_recurrence.png produced?"
```

Check the model is not starved (this is the usual cause of "it's slow"):

```bash
/opt/anaconda3/bin/python3 -c "import ollama; r=ollama.chat(model='qwen3:4b',messages=[{'role':'user','content':'What is 2+2?'}]); print(round(r['eval_count']/(r['eval_duration']/1e9),1),'tok/s')"
```

Healthy is 25-40 tok/s on this M3. Under 10 means something is eating the
machine — check `uptime` and `ps -Ao %cpu,comm -r | head`.

There is no build, no lint config, and no deploy.

## Environment

Python **3.13.5** at `/opt/anaconda3/bin/python3`. Bare `python3` lacks the
deps, which is why `RUN_REAL.sh` pins the interpreter and fails loudly.

Ollama **0.32.5** (homebrew, arm64 native). chromadb **1.5.9**, numpy 2.1.3,
scipy 1.15.3, plus `ollama`, `slack_bolt`, `python-dotenv`. Nothing was added
this session.

Env vars — names only:

| name | purpose |
|---|---|
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` | sourced from `~/.levyboy_tokens` (chmod 600, gitignored) |
| `LEVYBOY_BACKEND` | `rag` \| `cli` \| `stub`; must be `rag` for the real stack |
| `LEVYBOY_CORPUS` | corpus root; enables agent mode and tracing |
| `LEVYBOY_AGENT_TIMEOUT` | seconds; **300** in the launcher, 120 is the code default |
| `LEVYBOY_LAB_RAG_PATH` | only for the `cli` backend |
| `LAB_CHAT_MODEL` | the one line that moves this to Discovery |
| `LAB_PROFILE_PATH` | lab conventions injected into prompts |
| `LAB_EMBED_MODEL`, `LAB_CHROMA_DIR`, `LAB_COLLECTION` | supported overrides, not currently set |
| `OLLAMA_MAX_LOADED_MODELS` | **must be 2**, see Hacks |
| `OLLAMA_KEEP_ALIVE`, `PYTHONPATH` | |

## Test status

**141 passing** in pathology-agent, **25 passing** in levyboy-slackbot. Zero
failures, zero skips.

Untested, and worth knowing before claiming coverage:

- `evaluation/run_arms.py` has no tests at all
- `safe_exec.run_python` has **never been exercised by a live model** —
  `allow_execution=False` everywhere, so the sandbox is unproven in practice
- `app.py` is untested; it is deliberately a thin adapter so the logic in
  `handlers.py` can be tested without Slack
- No end-to-end test hits a real Slack workspace

## Known bugs, gaps, hacks

**The ChromaDB index does not exist.** `chromadb.PersistentClient(path=
rag/chroma_db).list_collections()` returns `[]`. Collection `levy_lab` is
absent, so `search_lab_files` fails with "corpus isn't indexed" and the answer
gets stamped `search failed — this answer did NOT use retrieval`. Trace, read,
and list still work. **This is the single most important thing to fix.**

**`rag/chroma_db/chroma.sqlite3` is tracked in git.** A binary that rewrites on
every run, permanently dirtying the tree and bloating history. Should be
gitignored and rebuilt from source files.

**Slack tokens are in git history** at commit `8c51d3e`. They were moved out of
the tracked launcher, but history still has them. **Rotate at api.slack.com.**
Not done.

**`OLLAMA_MAX_LOADED_MODELS` is load-bearing and both extremes break it.**
Unset: swap thrash, 83s for a trivial prompt. Set to 1: the embed and chat
models unload/reload every agent step, Ollama drops connections mid-request
(`httpx.RemoteProtocolError`), and Slack hangs on "thinking…" forever. 2 is
correct. `RUN_REAL.sh` documents this.

**Hardcoded absolute paths** — `demo/slack_live.py:69` and `demo/demo.py:200`
both hardcode `/Users/avilash/...`. Breaks for anyone else.

**Scratch dir under `/tmp`** — `rag/lab_agent.py:391` and `:723` use
`/tmp/lab_agent_scratch`, which macOS periodically clears.

**`lab_query.verify_paths` (line 313) accepts basename matches** as "exists".
Intentional and documented, but it makes the metric more generous than a strict
path check; `evaluation/analyze.py` has the stricter `classify_citation()`.
Don't mix them up when writing results.

**`workflow._direction` (line 123)** classifies read-vs-write by substring and
can misclassify. Known, unfixed.

**Three of four promised metrics are not instrumented** — usefulness,
reproducibility, time saved. No rating rubric exists. Task set is 8 questions,
protocol calls for ~30 with ≥12 undocumented controls. One replicate, protocol
calls for three. No human arm.

**BM25 ties the assistant** — 0 discordant pairs, p = 1.0. This is a real
measured result. Report it.

## Conventions a fresh session would violate

**Never edit `~/labagent`.** That is Varun's repo, pulled from
varunkal/AI-Agent-for-Digital-Pathology. It is kept pristine and configured
through the `LAB_*` env vars instead, so his `git pull` never conflicts. Editing
it silently reverts on his next pull. This was learned the hard way.

**Retrieval is not forced, on purpose.** The model decides when to call
`search_lab_files`. That is Aim 1 — the agent chooses its tools — and
`used_no_tools` exists to catch it when it skips. Avilash was offered
always-retrieve on 2026-08-03 and explicitly declined. Do not "fix" this.

**Warnings must stay rare to stay meaningful.** The no-tools warning fires only
when a fresh question was answered from model memory — not on follow-ups, not
when the model asked for clarification. Adding a warning that fires on correct
behavior trains people to ignore all of them.

**Comments explain why, not what.** The existing comments record the failure
that motivated the code, often with measured numbers. Match that. Do not strip
them.

**Every scoring change gets audited for direction.** Six scoring bugs were
found in this project and every one of them favored the project. Assume the
next one does too.

**Report the unflattering numbers.** The BM25 tie and the 0/6 hallucination
rate are both real; the first is bad news and gets said out loud. That is what
makes the rest credible.
