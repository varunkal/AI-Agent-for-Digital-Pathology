#!/bin/bash
# Start LevyBoy on Discovery against the PanCyto corpus.
#
# The exclusions below are NOT optional and NOT cosmetic. Aaditya consented to
# us reading his code. He did not consent to his slide identifiers being put in
# a searchable store or quoted in Slack.
#
#   eval/      holds slide-ID lists (train_files.txt, eval_holdout_slides.txt)
#   compare*/  filenames ARE accession numbers (469506_RGB.png), and the chunker
#              stamps the path into every passage, so paths leak as well as
#              contents
#   runs/      near-duplicate configs that make several answers ambiguous
#
# LEVYBOY_CORPUS points at the project root, so the agent's read/list/trace
# tools walk the real tree. They honour LAB_RAG_SKIP_DIRS and
# LAB_RAG_EXTENSIONS, the same two variables the indexer uses, so one setting
# governs both and they cannot drift apart. Without that, three of the agent's
# four tools bypass the index entirely and can read what was excluded from it.
#
# Usage:  bash RUN_PANCYTO.sh

set -e

PANCYTO=/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/projects/PanCyto

if [ ! -d "$PANCYTO" ]; then
  echo "Cannot see $PANCYTO"
  echo "Either you are not on Discovery, or you lack read access to Aaditya's project."
  exit 1
fi

TOKENS="$HOME/.levyboy_tokens"
if [ ! -f "$TOKENS" ]; then
  echo "Missing $TOKENS with SLACK_BOT_TOKEN and SLACK_APP_TOKEN"
  exit 1
fi
# shellcheck disable=SC1090
source "$TOKENS"

# --- the allowlist, shared by the indexer and the agent's file tools ---
export LAB_RAG_SKIP_DIRS="corpus,eval,runs,extraction,compare,compare_v2,compare_v3,test_slides,third_party,preview,models,YOLO"
export LAB_RAG_EXTENSIONS=".py,.ipynb,.yaml,.yml,.sh,.sbatch"

# Index location. Not the repo and not home: /dartfs/rc has been full, and lab
# policy prohibits data in home directories. Scratch purges after 45 days, so
# this needs rebuilding periodically. It takes about a minute.
export LAB_RAG_CHROMA_DIR=/dartfs-hpc/scratch/$USER/pancyto/index
export LAB_CHROMA_DIR="$LAB_RAG_CHROMA_DIR"

export LEVYBOY_BACKEND=rag
export LEVYBOY_CORPUS="$PANCYTO"
export LEVYBOY_AGENT_TIMEOUT=300
export LAB_CHAT_MODEL="${LAB_CHAT_MODEL:-qwen3-coder}"
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_KEEP_ALIVE=30m

PYBIN="${LEVYBOY_PYTHON:-python3}"

# --- refuse to start if anything outside the allowlist reached the index ---
"$PYBIN" - <<'PYEOF'
import os, sys
sys.path.insert(0, os.path.expanduser("~/pathology-agent/rag"))
try:
    import chromadb
    col = chromadb.PersistentClient(
        path=os.environ["LAB_RAG_CHROMA_DIR"]).get_collection("levy_lab")
except Exception as exc:
    print(f"No index yet ({type(exc).__name__}). Build it first, see README.")
    raise SystemExit(1)

srcs = [m["source"] for m in col.get(include=["metadatas"])["metadatas"]]
bad = sorted({s for s in srcs if not s.startswith(("scripts/", "configs/", "notebooks/"))})
print(f"index: {col.count()} chunks, {len(set(srcs))} files")
if bad:
    print("REFUSING TO START. These are in the index and should not be:")
    for b in bad[:20]:
        print("   ", b)
    raise SystemExit(2)
print("index allowlist: clean")
PYEOF

cd ~/levyboy-slackbot
export PYTHONPATH=~/pathology-agent/rag:~/labagent/rag
pkill -f "levyboy-slackbot/app.py" 2>/dev/null || true
exec "$PYBIN" -u "$PWD/app.py"
