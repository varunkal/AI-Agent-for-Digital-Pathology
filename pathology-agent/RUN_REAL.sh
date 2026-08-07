#!/bin/bash
# Start the Slack bot on the real stack: lab_rag + a local Qwen.
#
# Tokens are NOT stored here. They are secrets and this file is tracked in git.
# Put them in ~/.levyboy_tokens (which is gitignored), like this:
#
#     export SLACK_BOT_TOKEN=xoxb-...
#     export SLACK_APP_TOKEN=xapp-...
#
# Usage:  bash ~/pathology-agent/RUN_REAL.sh

set -e

TOKENS="$HOME/.levyboy_tokens"
if [ ! -f "$TOKENS" ]; then
  echo "Missing $TOKENS — create it with your two Slack tokens:"
  echo '    export SLACK_BOT_TOKEN=xoxb-...'
  echo '    export SLACK_APP_TOKEN=xapp-...'
  echo "Then:  chmod 600 $TOKENS"
  exit 1
fi
# shellcheck disable=SC1090
source "$TOKENS"

pkill -f "levyboy-slackbot/app.py" 2>/dev/null || true
# Model residency. Two settings, arrived at the hard way:
#
#   Unset (default 3+): the chat model, the embedding model AND a second chat
#   model all stayed resident (~6.3GB) on a 16GB Mac. It swapped hard -- 4.9GB
#   of swap, 83s for a trivial prompt.
#
#   =1: fixed the swapping but broke the agent. Every agent step needs the
#   embedding model (to search) then the chat model (to reason), so a cap of one
#   forced an unload/reload per step. Under that churn Ollama dropped connections
#   mid-request (httpx.RemoteProtocolError) and the bot hung on "thinking..."
#
#   =2: both models resident (~4.3GB together, comfortable), no swap thrash, no
#   reload per step.
#
# The team lead recorded the same class of problem on Discovery as a GPU
# exclusive-mode conflict, so model residency matters on the cluster too.
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_KEEP_ALIVE=30m
pgrep -x ollama >/dev/null || (nohup ollama serve >/tmp/ollama_serve.log 2>&1 & sleep 3)

cd ~/levyboy-slackbot
export LEVYBOY_BACKEND=rag
# The model, set here rather than by editing the team lead's repo. Moving to
# Discovery is this one line: qwen3:4b -> qwen3-coder
export LAB_CHAT_MODEL=qwen3:4b
# Agent deadline. A measured run using trace_pipeline took 169s on this laptop,
# so the 120s default would abandon runs that were working fine. 300s leaves
# headroom; on a GPU node this will be far lower.
export LEVYBOY_AGENT_TIMEOUT=300
export PYTHONPATH=~/pathology-agent/rag:~/labagent/rag
# Corpus root enables workflow tracing and agent mode.
export LEVYBOY_CORPUS=~/pathology-agent/demo/corpus
# Lab conventions injected into every answer (Aim 2).
export LAB_PROFILE_PATH=~/pathology-agent/demo/DEMO_LAB_PROFILE.md
# Pin the interpreter. Bare `python3` on this machine lacks dotenv/slack_bolt/
# chromadb/ollama, so the bot died at import with a ModuleNotFoundError that
# looked like a code fault rather than a PATH one.
PYBIN="${LEVYBOY_PYTHON:-/opt/anaconda3/bin/python3}"
if ! "$PYBIN" -c "import dotenv, slack_bolt" 2>/dev/null; then
  echo "ERROR: $PYBIN is missing dependencies."
  echo "Install them, or set LEVYBOY_PYTHON to an interpreter that has"
  echo "dotenv, slack_bolt, chromadb and ollama."
  exit 1
fi
exec "$PYBIN" -u app.py
