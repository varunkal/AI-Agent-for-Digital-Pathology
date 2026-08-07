# Performance findings

Measurements from the Levy Lab Copilot RAG pipeline on Dartmouth Discovery.
Recorded for the paper's systems/limitations section.

## Run 1: 2026-08-07, baseline characterization

**Environment**

| | |
|---|---|
| Node | `gv01.hpcc.dartmouth.edu` |
| GPU | Tesla V100-PCIE-32GB |
| Partition | `v100_vaickus`, `--gpu_cmode=exclusive` |
| Models | `qwen3-coder` (18GB), `nomic-embed-text` (274MB), via Ollama |
| Constraint | `OLLAMA_MAX_LOADED_MODELS=1` |
| Python | 3.11.15, conda env `labagent` |
| Code | commit `3f65d89` |

### Finding 1: directory traversal dominates indexing cost

| Target | Files walked | Time |
|---|---|---|
| `rag/` only | 14 | 0.1s |
| Whole repo | 204,936 | 26.2s |

The project directory contains ~200K PatchCamelyon `.tif` image patches under
`data/`. `os.walk` enumerates every file before the extension filter is
applied, so each index run spends ~26s listing images it will never index.

**Implication:** the mitigation proposed in the 2026-08 project meeting
(restricting the corpus to `.py` and `.ipynb`) would not have addressed this.
Extension filtering happens after enumeration, so traversal cost is unchanged.
The fix is to prune data directories during the walk itself.

### Finding 2: query latency under exclusive-mode GPU scheduling

| Query | Latency |
|---|---|
| First (cold) | 118s |
| Second | 24s |

A single query embeds the question with `nomic-embed-text`, then generates with
`qwen3-coder`. Under `OLLAMA_MAX_LOADED_MODELS=1`, required to avoid CUDA
contention in exclusive GPU mode, only one model may be resident. Each query
therefore evicts one model and loads the other, and one of them is 18GB.

This is the likely root cause of the poor responsiveness observed when the
pipeline was integrated with the Slack bot. It is a scheduling and memory
residency problem, not a retrieval problem: no amount of retrieval tuning
changes it.

**Candidate fix:** move embedding off the GPU to CPU inference, keeping
`qwen3-coder` permanently resident. The L40S node in this partition has
substantial system RAM, making CPU embedding viable.

**Generalizable point for the paper:** exclusive-mode GPU allocation on shared
HPC creates a hard tension for multi-model RAG. The setting that prevents CUDA
contention is the same setting that forces per-query model eviction.

### Finding 3: incremental indexing verified live

| Pass | Chunks embedded | Time |
|---|---|---|
| Cold index | 22 | 21s |
| Re-index, unchanged | 0 | 14s |

Batched embedding executed against live Ollama without error, confirming the
client accepts `Sequence[str]` input. Re-indexing an unchanged corpus embedded
nothing, confirming per-file reconciliation works outside the test harness.

Retrieved chunks were correctly cited and the generated answer was accurate.

## Known gaps in this run

- **No old-vs-new comparison.** The pre-`a00d601` implementation was not run,
  so no speedup figure for batched embedding is claimed. With a 22-chunk
  corpus any difference would be marginal; batching pays off with scale.
  A controlled comparison on a larger corpus is needed before citing a number.
- **Corpus too small for retrieval evaluation.** 22 chunks from a single file.
  All five retrieved chunks came from `lab_rag.py` because it was the only
  indexable file present. No retrieval-quality conclusions can be drawn.
- **Single run, no repetition.** Latencies are single measurements, not means
  over trials. Cold-start effects are not separated from steady state.

## Planned next measurements

1. Controlled old-vs-new indexing throughput on a corpus of several hundred
   files. Can run CPU-only, since the comparison concerns HTTP round-trip
   overhead rather than GPU throughput.
2. Query latency before and after moving embeddings to CPU.
3. Retrieval accuracy (Recall@k, MRR) once a real lab corpus is available.
