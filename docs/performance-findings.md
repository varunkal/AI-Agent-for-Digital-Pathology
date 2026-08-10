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

## Run 2: 2026-08-10, controlled A/B on node p03

Node `p03.hpcc.dartmouth.edu`, Tesla V100-SXM2-32GB. Same corpus (22 chunks),
same two questions, each arm launched from a fresh server so "cold" is
comparable.

### Finding 4: model weights are read over NFS at 242 MB/s

```
/dartfs/rc  (dartfs-nfs-t4)  212T, 96% full
model blob: 18,556,688,736 bytes
sequential read: 2.0 GiB in 8.9s = 242 MB/s
```

Loading the full model therefore costs roughly **77 seconds of pure I/O**.
This is the mechanism behind the cold-start latency: it is a storage
throughput limit, not a GPU limit. On local NVMe the same load would cost
under 10s and would not be noticeable.

### Finding 5: traversal cost is far worse on a cold metadata cache

```
old os.walk:        10 indexable files in 340.5s
new collect_files:  10 indexable files in   0.0s  (2 directories skipped)
```

Run 1 measured 26.2s for the same traversal on `gv01`, where NFS metadata was
already cached. On a cold cache the true cost is **5.7 minutes**. The honest
range for the old implementation is 26s warm to 340s cold.

### Finding 6 (NEGATIVE): serving embeddings from a CPU instance is 5x worse

| Arm | Configuration | Cold | Warm | Warm |
|---|---|---|---|---|
| A | Single instance, both models on GPU | 90s | 24s | |
| B | Chat on GPU (11434), embeddings on CPU (11435) | 231s | 119s | 119s |

Arm B behaved exactly as designed. Residency after the run:

```
GPU instance:  qwen3-coder       21 GB   100% GPU   resident
CPU instance:  nomic-embed-text  376 MB  100% CPU   resident
GPU memory in use: 21,290 MiB
```

Both models stayed loaded and no eviction occurred, which was the entire point
of the change. Warm latency still rose from 24s to 119s. The intervention is
rejected and `startup.sh` reverted to a single instance.

Cause is not established. The leading candidate is contention between the two
servers over the shared NFS-backed `OLLAMA_MODELS` store, a risk flagged
before the run. Recorded as an open question rather than a conclusion.

### Correction to Run 1's interpretation

Run 1 attributed the 118s query latency to the 18GB chat model being evicted
and reloaded on every query. **Arm A refutes this.** A warm query costs 24s,
far below the ~77s an NFS reload of the chat model would require. Ollama was
evicting the 376MB embedding model, not the 21GB chat model, and reloading
that is ~1.5s and effectively invisible.

The corrected picture:

- **Cold start**: ~77s of NFS I/O to load the chat model, paid once per
  server launch
- **Steady state**: ~24s per query, dominated by generation

Claims of the form "118-second per-query latency caused by repeated model
reloading" are not supported and should not appear in the paper or elsewhere.
Where the remaining ~24s actually goes has not been measured.

## Planned next measurements

1. **Stage-level profiling of a query.** Time the embed call, the ChromaDB
   retrieval, and the generation separately. Every latency conclusion so far
   has come from end-to-end timings plus inference about the mechanism, and
   Run 2 showed that inference can be wrong. This is small and would settle
   where the ~24s steady-state actually goes.
2. Why Arm B regressed. Likely NFS contention between two Ollama servers, but
   unproven.
3. Whether staging model weights on compute-node local scratch removes the
   77s cold start. Local scratch purges after 20 days but a cold start is a
   per-session cost, so a per-session copy may pay for itself.
4. Controlled old-vs-new indexing throughput on a corpus of several hundred
   files, to quantify the embedding-batching change. Can run CPU-only.
5. Retrieval accuracy (Recall@k, MRR) once a real lab corpus is available.
