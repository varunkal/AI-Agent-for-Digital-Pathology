# Project Handoff: AI Agent for Digital Pathology Research ("Levy Lab Copilot")

This document is a point-in-time snapshot meant to let any AI assistant (or teammate) pick up this project without re-deriving context. Written 2026-08-03.

**Program**: EDIT AI/ML Internship, Dartmouth College / Dartmouth-Hitchcock Medical Center, Summer 2026
**GitHub**: `github.com/varunkal/AI-Agent-for-Digital-Pathology`
**Team**: Varun Kalidindi (lead/dev), Avilash Angirekula (dev, Slack bot), Nehan Mohammed (OpenAI credits) · Mentor: Zarif Azher (weekly Mon 5pm, available most days after 5pm)
**NetID**: f0082z8 · **HPC username**: VarunKalidindi

## Goal

Locally-hosted AI agent on Dartmouth's Discovery HPC that indexes the Levy Lab's research files (notebooks, scripts, datasets) and answers questions about lab workflows. **Hard constraint: no data leaves institutional infrastructure.**

## Tech stack (installed & working)

- LLM: **Qwen3-Coder** (18GB) via **Ollama v0.30.9** — only this model works with qwen-code tool-calling; Qwen2.5-Coder outputs JSON instead of executing tools
- Agent framework: **qwen-code v0.19.4** (npm global install)
- RAG: **ChromaDB 1.5.9** + **nomic-embed-text** embeddings
- Python 3.11 via Conda, env name **`labagent`**
- Node v25.8.2 (conda-installed, for qwen-code)
- Everything lives under `/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/users/VarunKalidindi/` (home dir has a 50GB cap — intentionally avoided)

## HPC / SLURM specifics

- Cluster: Dartmouth Discovery, login via `ssh f0082z8@discovery8`
- GPU node: `gv01` or `p02`–`p04` (V100 32GB), **exclusive GPU mode**
- `srun -p v100_vaickus --account=qdp-alpha --gpu_cmode=exclusive --time=02:00:00 --gres=gpu:1 --pty /bin/bash`
- **Key gotcha solved**: exclusive GPU mode throws "device busy" if the embedding model and Qwen3-Coder try to load simultaneously → fix is `export OLLAMA_MAX_LOADED_MODELS=1` before `ollama serve`
- Sessions expire with the time limit; filesystem persists but the Ollama process dies and must be restarted each time

## Daily startup (3 blocks — see `startup.sh`)

```bash
# Block 1 — login node
source .../VarunKalidindi/anaconda3/etc/profile.d/conda.sh
conda activate labagent
srun -p v100_vaickus --account=qdp-alpha --gpu_cmode=exclusive --time=02:00:00 --gres=gpu:1 --pty /bin/bash

# Block 2 — GPU node
source .../VarunKalidindi/anaconda3/etc/profile.d/conda.sh
conda activate labagent
export OLLAMA_MODELS=.../VarunKalidindi/ollama/models
export OLLAMA_MAX_LOADED_MODELS=1
ollama serve > ollama.log 2>&1 &
sleep 3 && curl http://localhost:11434

# Block 3 — start agent
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_MODEL="qwen3-coder"
cd .../AI-Agent-for-Digital-Pathology
qwen
```

## RAG pipeline — `rag/lab_rag.py`

- Commands: `index /path`, `query "question"`, `chat`
- Indexes `.py .ipynb .md .txt .sh .yaml .yml .json .csv .tsv .r .R .cfg .conf .toml`; notebooks parsed cell-by-cell (code + markdown); CSV/TSV capped at 50 lines
- Chunking: 800 chars, 100 overlap, MD5-hashed chunk IDs
- Embeds via `ollama.embed(model="nomic-embed-text")`, stores in **ChromaDB** at `rag/chroma_db/` (cosine similarity)
- Query: top-5 chunks → prompt (persona "Levy Lab Copilot", must cite sources) → `ollama.chat(model="qwen3-coder")`
- **Not yet wired into qwen-code** — still two separate tools. This is the top architectural remaining-work item.

## Dummy case study: PatchCamelyon (PCam)

- Kaggle histopathologic cancer detection, 220K 96×96 H&E patches, binary label (tumor in center 32×32 or not), `train_labels.csv`
- Downloaded (~6.3GB) + unzipped to `AI-Agent-for-Digital-Pathology/data/` — **not yet verified or used**
- One-pager: load images → train ResNet-18/simple CNN → evaluate accuracy/AUC/confusion matrix/ROC → becomes the paper's results section, and tests how much of the ML pipeline the agent can do autonomously from a high-level prompt

## Git / GitHub state

- Auth: classic PAT (username `varunkal`), stored in this Mac's keychain — push/pull works without prompting
- Known issues you'd hit again: rejected pushes from editing both on GitHub web and locally → fix is `git pull origin main --rebase` before pushing; a nested-repo accident was previously fixed with `git rm --cached AI-Agent-for-Digital-Pathology`
- 2026-08-03: this Mac had accidentally git-initialized the *entire home directory* and pointed it at an unrelated old repo (`vibercoder27/m3mathchalenege-2026`, leftover from a math competition project). That was removed (no files touched, just stray git tracking). A fresh, correctly-scoped local repo now lives at `~/Claude/Projects/AI Agent for Digital Pathology Research`, tracking `origin/main` of the real `varunkal/AI-Agent-for-Digital-Pathology` repo, fully in sync.

## Remaining work, in priority order

1. Verify PCam dataset unzipped correctly (`ls data/`, `head -5 data/train_labels.csv`)
2. Run agent on the dummy project end-to-end (write training script, execute, evaluate)
3. Wire RAG into qwen-code so retrieval happens automatically before answering
4. Case study evaluation: agent-assisted vs. human workflow
5. Scale RAG to real Levy Lab project folders
6. Slack bot integration (Avilash — read-only v1; he has repo link, startup steps, Ollama API details)
7. Paper writeup: methods, results, architecture diagrams, case study analysis

## House rules

No sycophantic openers, no closing fluff, no em-dashes, concise output. No guessing APIs/versions/flags/package names without verifying against the actual repo/environment first.
