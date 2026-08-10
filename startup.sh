#!/bin/bash
# Levy Lab Copilot - Daily Startup Script
# Run this after SSH'ing into discovery and getting a GPU node:
#   srun -p v100_vaickus --account=qdp-alpha --gpu_cmode=exclusive \
#        --time=02:00:00 --gres=gpu:1 --pty /bin/bash

LAB_ROOT=/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/users/VarunKalidindi

source "$LAB_ROOT/anaconda3/etc/profile.d/conda.sh"
conda activate labagent

export OLLAMA_MODELS="$LAB_ROOT/ollama/models"

# Required under exclusive GPU mode. Without it, loading a second model
# alongside qwen3-coder trips a CUDA "device busy" error.
export OLLAMA_MAX_LOADED_MODELS=1

# Vector database location. Not the repo (/dartfs/rc is full) and not home
# (lab policy prohibits storing data there). Scratch gives 5TB per user.
# Note: scratch purges files older than 45 days, so copy anything durable.
export LAB_RAG_CHROMA_DIR=/dartfs-hpc/scratch/$USER/levy_lab_index
mkdir -p "$LAB_RAG_CHROMA_DIR"

# Never descend into the PCam image directories. They hold ~200k .tif files
# with nothing indexable, and enumerating them cost ~26s on every index run.
export LAB_RAG_SKIP_DIRS="data,datasets,checkpoints"

# Single Ollama instance.
#
# A two-instance setup (embeddings on a CPU-only server, port 11435) was
# tested on p03 and made things FIVE TIMES WORSE: warm queries went from 24s
# to 119s. Both models stayed resident exactly as intended, so the design
# worked and the outcome was still bad. Cause not yet established; likely
# contention between the two servers over the NFS-backed model store.
# lab_rag.py still supports LAB_RAG_EMBED_HOST, but do not set it until
# someone measures a configuration that actually helps.
# See docs/performance-findings.md, Run 2.

ollama serve > ollama.log 2>&1 &
OLLAMA_PID=$!

for i in $(seq 1 30); do
    curl -s http://localhost:11434 >/dev/null 2>&1 && break
    sleep 2
done
echo "  Ollama (11434): $(curl -s http://localhost:11434 || echo UNREACHABLE)"

# Point qwen-code at Ollama instead of a cloud API.
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_MODEL="qwen3-coder"

echo "Ready."
echo "  Agent:  qwen"
echo "  RAG:    python rag/lab_rag.py index <dir>   |   query \"...\"   |   chat"
echo "  Index:  $LAB_RAG_CHROMA_DIR"
echo "  Stop:   kill $GPU_PID $CPU_PID"
