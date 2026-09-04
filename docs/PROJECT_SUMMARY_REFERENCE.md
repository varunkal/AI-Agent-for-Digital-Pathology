# Levy Lab AI Research Agent — Reference Summary

Copy-paste reference. Everything here is measured and reproducible from the
repo. Written 2026-09-04.

## One-line description

A locally hosted, retrieval-augmented AI agent that answers questions about a
clinical pathology research lab's codebase, running entirely on Dartmouth's HPC
so patient-adjacent data never leaves institutional hardware.

## The stack

| Layer | Choice |
|---|---|
| Language model | Qwen3-Coder, 30.5B parameters, Q4_K_M quantized (18.6GB on disk) |
| Model server | Ollama |
| Embeddings | nomic-embed-text (768-dim) |
| Vector database | ChromaDB |
| Keyword search | BM25 (custom, ~60 lines, standard library) |
| Compute | Dartmouth Discovery HPC — SLURM, NVIDIA V100 / L40S / H200 |
| Interface | Slack bot (teammate's component) |

## What the system does

User asks a question in Slack -> the system searches the lab's files for the
5 most relevant text chunks -> pastes them into the model's prompt -> the model
answers using only that retrieved material, with citations. If the right file
isn't retrieved, the answer is built on wrong material and can't recover.

## The core contribution: measuring and fixing retrieval

Most student RAG projects have no evaluation. This one has a benchmark and a
measured, non-obvious fix.

**Benchmark:** 30 questions (25 scorable) with hand-verified ground truth over
the PanCyto clinical pathology codebase (used with the owner's permission).
Questions span locating files, recovering parameters, and reproducing workflows.

**Key finding — semantic search collapses as the corpus grows:**

| Corpus | Method | Top-5 accuracy |
|---|---|---|
| 49 files | Semantic only | 88% |
| 49 files | Hybrid | 96% |
| 610 files | Semantic only (was deployed) | 56% |
| 610 files | Keyword only | 88% |
| 610 files | Hybrid, equal weight | 80% |
| 610 files | Hybrid, keyword-weighted 3x | 88% |

Reading it: on the full codebase, meaning-based search fell to 56% because the
added files are legitimately similar lab code it can't tell apart. Keyword
search held at 88% (exact file names stay unique). Combining them naively made
things worse (80%); weighting keyword search 3x restored 88%. Same files, same
questions — only the search strategy changed.

**Why hybrid wins:** semantic and keyword miss *different* questions. On 49
files, semantic missed 3, keyword missed 2, but only 1 was missed by both.
Merging their ranked lists (reciprocal rank fusion) recovers each one's misses.

**Silent failure (safety finding):** when retrieval misses, the bot doesn't say
so — it writes a confident, cited answer from the wrong files. Example: asked
for the funding source, it answered "qdp-alpha" from a billing line in a batch
script — real citation, wrong conclusion. In a clinical setting, a tool that
invents plausible answers is more dangerous than one that admits ignorance.

## Performance profiling

| Stage | Time |
|---|---|
| Embed the question | ~6.5s |
| Search | <0.2s even at 6,275 chunks |
| Generate answer | ~11s |
| Total per query | ~17s |
| Cold start (load 18.6GB model) | ~11-170s, once per server launch |

Search is nearly free; time is model loading and generation. The 6.5s to embed
one question is a fixable target (caused by models swapping in/out of GPU
memory). Retrieving more chunks (k) helps the small corpus (92%->96%) but does
nothing on the large one, where missed files rank ~#200, not ~#6.

## What I built vs. teammate

- **Me:** the RAG pipeline, the benchmark, the baseline/hybrid evaluation, the
  performance profiling, the scaling and complementary-failure analysis.
- **Teammate (Avilash):** the Slack integration and server-side handling.

## Honest limitations (state these — owning them reads as competence)

- 25 scorable questions, single run, one corpus. True accuracy behind an "88%"
  could reasonably sit anywhere ~70-96%.
- Ground truth verified by reading the code, not confirmed by the author on
  every item. One question (rep-007) is flagged unverified and missed by all
  methods — likely a bad question, not a bad retriever.
- The 610-file result is one project; the system was never shown to work across
  many projects.

## Not done yet

Re-ranking: on 610 files the system is stuck at 88% and neither weighting nor
more chunks moves it. Standard next step — retrieve ~50 candidates, have a model
re-score them, keep the best 5.

## Reproduce

```
python evaluation/baseline_retrieval.py --corpus <PanCyto> --tasks evaluation/tasks_pancyto.jsonl --outdir runs
python evaluation/hybrid_retrieval.py   --corpus <PanCyto> --tasks evaluation/tasks_pancyto.jsonl --outdir runs --cache embed_cache.json
python pathology-agent/evaluation/analyze.py --tasks evaluation/tasks_pancyto.jsonl --runs runs/*.jsonl
```

## Figures

- docs/figure_scaling.svg — accuracy vs corpus size (semantic dives, keyword
  flat, hybrid on top)
- docs/figure_complementary.svg — per-question view of why hybrid beats either
  method alone
