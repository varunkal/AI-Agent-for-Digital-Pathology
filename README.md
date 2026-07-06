# AI Agent for Digital Pathology Research

A lab-personalized AI agent for reproducible digital pathology research, built for the Levy Lab at Dartmouth-Hitchcock Medical Center as part of the EDIT AI/ML Internship Program (Summer 2026).

## Overview

Digital pathology researchers spend significant time on operational tasks instead of focusing on scientific reasoning. This project builds a locally-hosted AI agent that understands the lab's own files, code, and workflows, helping researchers work faster while keeping all data secure on institutional infrastructure.

The agent runs entirely on Dartmouth's Discovery HPC cluster. No data ever leaves the institution.

## Team

- Varun Kalidindi (Lead Developer)
- Nehan Mohammed (Developer)
- Avilash Angirekula (Developer)
- Zarif Azher (Faculty Mentor)

## Tech Stack

- LLM: Qwen3-Coder (open-source, 18GB) served via Ollama
- Agent Framework: qwen-code v0.19.4
- Runtime: Ollama on Discovery HPC (V100 GPUs)
- RAG (planned): ChromaDB + LlamaIndex
- Environment: Python 3.11 / Conda

## Current Capabilities

- Locally-hosted LLM on Discovery HPC (no external API calls)
- Agent can read files and directories on the HPC
- Agent can write and execute Python scripts autonomously
- Daily startup script for reproducible sessions

## Planned

- RAG over lab notebooks, scripts, and datasets
- Web interface (Streamlit/Gradio) for researcher access
- Case study evaluation against human workflows

## Privacy and Security

- All models run locally on Discovery HPC V100 GPUs
- No patient data or lab files are sent to external APIs
- OpenAI API access used only for benchmarking on de-identified data
- Agent operates with read-only access to original lab materials
