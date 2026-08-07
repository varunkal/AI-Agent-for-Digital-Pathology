#!/bin/bash
# Levy Lab Copilot - Daily Startup Script
# Run this after SSH'ing into discovery and getting a GPU node:
#   srun -p v100_vaickus --account=qdp-alpha --gpu_cmode=exclusive \
#        --time=02:00:00 --gres=gpu:1 --pty /bin/bash

LAB_ROOT=/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/users/VarunKalidindi

source "$LAB_ROOT/anaconda3/etc/profile.d/conda.sh"
conda activate labagent

export OLLAMA_MODELS="$LAB_ROOT/ollama/models"

# Required under exclusive GPU mode. Without it, loading the embedding model
# and qwen3-coder at the same time trips a CUDA "device busy" error.
export OLLAMA_MAX_LOADED_MODELS=1

# Vector database location. Not the repo (/dartfs/rc is full) and not home
# (lab policy prohibits storing data there). Scratch gives 5TB per user.
# Note: scratch purges files older than 45 days, so copy anything durable.
export LAB_RAG_CHROMA_DIR=/dartfs-hpc/scratch/$USER/levy_lab_index
mkdir -p "$LAB_RAG_CHROMA_DIR"

ollama serve > ollama.log 2>&1 &
sleep 5 && curl -s http://localhost:11434 && echo

# Point qwen-code at the local Ollama server instead of a cloud API.
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_MODEL="qwen3-coder"

echo "Ready."
echo "  Agent:  qwen"
echo "  RAG:    python rag/lab_rag.py index <dir>   |   query \"...\"   |   chat"
echo "  Index:  $LAB_RAG_CHROMA_DIR"
