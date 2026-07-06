#!/bin/bash
# Levy Lab Copilot - Daily Startup Script
# Run this after SSH'ing into discovery and getting a GPU node

source /dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/users/VarunKalidindi/anaconda3/etc/profile.d/conda.sh
conda activate labagent
export OLLAMA_MODELS=/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/users/VarunKalidindi/ollama/models
ollama serve > ollama.log 2>&1 &
sleep 3 && curl http://localhost:11434
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_MODEL="qwen3-coder"
echo "Ready! Run 'qwen' to start the agent."
