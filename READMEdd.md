# AI Agent for Digital Pathology Research

A lab-personalized AI agent for reproducible digital pathology research, built for the Levy Lab at Dartmouth-Hitchcock Medical Center.

## Team
- Varun Kalidindi (Lead)
- Nehan Mohammed
- Avilash Angirekula
- Mentor: Zarif Azher

## What This Is
A locally-hosted AI coding agent that runs entirely on Dartmouth's Discovery HPC cluster. It can read lab files, write and execute Python scripts, and will soon intelligently search across the lab's notebooks, datasets, and documentation using RAG.

No data ever leaves Dartmouth's infrastructure.

## Tech Stack
- LLM: Qwen3-Coder (open-source, 18GB) served via Ollama
- Agent Framework: qwen-code v0.19.4
- Runtime: Ollama on Discovery HPC (V100 GPUs)
- RAG (planned): ChromaDB + LlamaIndex
- Environment: Python 3.11 via Conda

## Privacy and Safety
- All models run locally on Discovery HPC GPUs
- No external API calls for real lab data
- Agent has read-only access to lab materials
- OpenAI API only used for benchmarking on de-identified data

## Part of the EDIT AI/ML Internship Program
Dartmouth College / Dartmouth-Hitchcock Medical Center, Summer 2026
