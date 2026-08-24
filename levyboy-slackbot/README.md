# LevyBoy — Slack interface for the Levy Lab digital-pathology agent

The researcher-facing surface, so lab members can ask the agent questions where
they already work: `@LevyBoy how was figure 3 made?`

## What it does
Every message goes to the agent. The agent has tools over the lab's real files
and decides for itself which to use, so nobody has to learn a syntax or classify
their own question before asking it.

It handles the whole range of what people actually ask:

| You ask | What happens |
|---|---|
| `what normalization was applied?` | searches the indexed corpus, reads what looks relevant, answers with the files |
| `how was results/figure3_recurrence.png produced?` | traces the real dependency chain, computed from the files, not generated |
| `open src/niche_discovery.py and explain it` | reads the file and explains it |
| `explain that more simply` | answers from the thread, no re-searching |
| `what is Leiden clustering?` | general background, and it says that is what it is |
| `why was resolution 0.7 chosen?` | searches, finds nothing, and says so rather than guessing |

Every answer ends with where it came from: the files it opened, or a plain
statement that it did not open any. That line is the point. An answer with files
listed can be checked.

## Why Socket Mode
The agent runs on **Discovery HPC**, which cannot accept inbound web requests.
Socket Mode uses an **outbound** WebSocket to Slack, so the bot runs from behind
the HPC firewall with **no public URL**. That is what makes it deployable next to
Ollama on a GPU node.

## Architecture
```
Slack (@LevyBoy) → Socket Mode WebSocket → app.py (slack_bolt, no logic)
    → handlers.py   threads, placeholder, live progress, per-thread memory
    → agent.ask()   the single integration seam
    → lab_agent.run_agent()          the agent loop, up to 8 steps
          ├── search_lab_files   ChromaDB "levy_lab" + nomic-embed-text
          ├── read_file          through safety.PathGuard
          ├── trace_pipeline     deterministic, computed from file references
          └── list_files
    → answer posted in-thread, with its sources
```

The two repos meet at exactly one place: `PYTHONPATH` includes
`~/pathology-agent/rag`, and this bot does `import lab_agent`. Nothing is copied
or vendored.

## Backends
Pick with `LEVYBOY_BACKEND`:

| Value | Behavior | Use when |
|---|---|---|
| `stub` (default) | Canned replies, nothing to install | Exercising the Slack plumbing with no model running |
| `rag` | The real agent: local Qwen via Ollama, tools over the corpus | Everything else |

## Safety — read-only by design
Dr. Levy (7/10): *"Please be careful about using agents modifying existing file
structure... make sure safeguards are in place."*

This bot performs **retrieval, reading and generation only**. It never writes,
edits, or deletes lab files, and never executes agent-authored code:
`allow_execution` stays False, so the `run_python` tool is not even offered to
the model. File reads go through `safety.PathGuard`, which confines them to
`LEVYBOY_CORPUS` and blocks symlink escapes.

## Run it

Stub mode, nothing else needed:
```bash
pip install -r requirements.txt
cp .env.example .env      # fill in SLACK_BOT_TOKEN and SLACK_APP_TOKEN
python app.py
```

The real agent (this is what `RUN_REAL.sh` in pathology-agent does for you):
```bash
bash ~/pathology-agent/RUN_REAL.sh
```

Verify with no Slack at all:
```bash
PYTHONPATH=~/pathology-agent/rag python -m pytest -q
```

## Slack app setup (one-time, needs a workspace admin)
At api.slack.com/apps: enable **Socket Mode** (gives the `xapp-` token, scope
`connections:write`); bot scopes `app_mentions:read`, `chat:write`, `im:history`,
`im:read`; subscribe to `app_mention` and `message.im`; install to the workspace
and copy the `xoxb-` token.

## Status
- [x] Slack layer: mentions, DMs, threaded replies, placeholder to answer, error handling
- [x] Live progress while the agent works, so a 40s answer does not look like a hang
- [x] Per-thread conversation memory, so follow-ups work
- [x] One agent path, no prefixes; the agent chooses its own tools
- [x] Every answer states where it came from
- [x] 35 unit tests, verified end to end against the real model and corpus
- [ ] Run against the live index on Discovery — needs HPC access
- [ ] Slack app created/installed in the EDIT workspace — needs admin
