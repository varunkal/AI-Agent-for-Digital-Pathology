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

# --- Two Ollama instances, on purpose ---
# A query embeds with nomic-embed-text and generates with qwen3-coder. Served
# from one instance under OLLAMA_MAX_LOADED_MODELS=1, each query evicts the
# 18GB chat model to load the embedder and then reloads it. Measured at 118s.
#
# GPU instance (11434) holds qwen3-coder and nothing else.
# CPU instance (11435) serves embeddings; nomic-embed-text is only ~274MB, so
# CPU is fine and the GPU model never gets evicted.

ollama serve > ollama-gpu.log 2>&1 &
GPU_PID=$!

CUDA_VISIBLE_DEVICES="" OLLAMA_HOST=127.0.0.1:11435 \
    ollama serve > ollama-cpu.log 2>&1 &
CPU_PID=$!

for i in $(seq 1 30); do
    curl -s http://localhost:11434 >/dev/null 2>&1 \
        && curl -s http://localhost:11435 >/dev/null 2>&1 && break
    sleep 2
done

echo "  GPU  (11434): $(curl -s http://localhost:11434 || echo UNREACHABLE)"
echo "  CPU  (11435): $(curl -s http://localhost:11435 || echo UNREACHABLE)"

# Route embeddings to the CPU instance. Same model as before, so existing
# vectors stay valid and indexes do not need rebuilding.
export LAB_RAG_EMBED_HOST=http://localhost:11435

# Point qwen-code at the GPU instance instead of a cloud API.
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_MODEL="qwen3-coder"

echo "Ready."
echo "  Agent:  qwen"
echo "  RAG:    python rag/lab_rag.py index <dir>   |   query \"...\"   |   chat"
echo "  Index:  $LAB_RAG_CHROMA_DIR"
echo "  Stop:   kill $GPU_PID $CPU_PID"
