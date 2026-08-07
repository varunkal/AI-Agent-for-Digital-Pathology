# What's actually left — honest version

Written 2026-07-31. Two problems, and they are not the same kind of problem.

---

## Problem 1: not using a real Qwen — FIXABLE BY YOU, TODAY

The demo used a keyword matcher where the language model goes. That's now being
fixed: Ollama is installing, and once a Qwen model is pulled you can run
**Varun's actual `lab_rag.py`** against a real model on your Mac.

### Finish it (if the install completed)

```bash
# 1. Start the model server (leave this window open)
ollama serve
```

```bash
# 2. In a NEW terminal window — pull the models.
#    Only ~10GB free disk, so use the small model, not the 18GB production one.
ollama pull qwen2.5-coder:3b
ollama pull nomic-embed-text
```

```bash
# 3. Install what Varun's code needs
pip3 install chromadb ollama
```

```bash
# 4. Get his real code
cd ~
git clone https://github.com/varunkal/AI-Agent-for-Digital-Pathology.git labagent
cd labagent
```

```bash
# 5. Point his indexer at the demo corpus and build a REAL index
python3 rag/lab_rag.py index ~/pathology-agent/demo/corpus
```

```bash
# 6. Ask it a question — his code, real model, real retrieval
python3 rag/lab_rag.py query "what normalization was applied to the expression data?"
```

**One change needed:** his code hardcodes `CHAT_MODEL = "qwen3-coder"`, which won't
fit in 16GB. Edit `rag/lab_rag.py` line 25 to:

```python
CHAT_MODEL = "qwen2.5-coder:3b"
```

Note that in the demo — it's a smaller model than production, and saying so is the
honest framing.

### Then point the Slack bot at it

```bash
cd ~/pathology-agent
export LEVYBOY_BACKEND=rag
export PYTHONPATH=~/labagent/rag:$PYTHONPATH
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...
python3 -u demo/slack_live.py
```

Now Slack → real retrieval → real Qwen → answer with sources. The only thing
separating that from production is the size of the model and that the files are
synthetic.

---

## Problem 2: not on the cluster — NOT FIXABLE BY ANYONE HERE

Discovery is Dartmouth's HPC. Using it needs an **account granted to you by a
person.** No amount of code, reading Slack, or re-reading the project description
produces that access. It has been the blocker since June and it is still the
blocker.

**This is the single most important thing to chase.** Without it:
- The agent can't run on real lab files
- The evaluation can't produce real results
- There is no case study, so there is no paper

### Exactly what to ask

**To Varun:**
> "Can you walk me through getting Discovery access? I have the repo running
> locally against a small Qwen but I need to be on the cluster to run anything
> real. Also — has the index ever been built over actual lab files, or only test
> folders?"

**To Dr. Levy:**
> "Two things I'm blocked on. First, is there a completed project with recoverable
> correct answers we could use as the evaluation case study? Without one there's
> no retrospective study. Second, could you advise on the IRB determination — BMC
> says retrospective approval usually can't be obtained, so I'd like it settled
> before running anything on real data."

Send both. They are the whole critical path.

---

## What is genuinely finished

- Slack bot: built, tested, running live
- Search that reports its sources: built, tested, matches Varun's settings exactly
- Safety guardrails: built, tested against five escape attempts
- Evaluation system: built, 80 tests passing, six self-inflicted bugs found and fixed
- Design doc, evaluation protocol, paper skeleton, provenance record

## What is genuinely NOT finished

- **The agent and the search are not connected.** Varun's stated next task.
- **Lab personalization does not exist.** The agent knows nothing about this lab's
  conventions, naming, pipelines, or standards. This is the actual research
  contribution the project asked for, and nobody has started it.
- **Nothing has run on real lab data.** Every number so far is from synthetic
  fixtures, clearly labelled.
- **No results exist.** None have been invented.

---

## Honest assessment

The infrastructure is real and defensible. The science hasn't started, and it
can't start until someone grants cluster access and names a case study.

Building more tooling will not change that. **The next move is two messages, not
more code.**
