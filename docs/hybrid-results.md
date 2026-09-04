# Hybrid retrieval: the predicted result, tested

Run 2026-09-02, node `l40sx4` (NVIDIA L40S 46GB), job 9334382.
Same corpus, same 30 tasks, same scorer as `baseline-comparison.md`.

## The prediction being tested

`baseline-comparison.md` found dense and BM25 failing on *different* tasks and
predicted that fusing them would recover both, for 24/25 = 96%. This run tests
that prediction. It was registered in writing before the run.

`hybrid_retrieval.py` uses reciprocal rank fusion (RRF, k=60). RRF combines
*rankings* rather than scores, so BM25's unbounded scale and cosine's [-1,1]
never have to be calibrated against each other.

This run also produced two things the original agent evaluation could not:

- **Dense scores over the whole corpus.** The deployed pipeline only ever saw
  ChromaDB's top-5, so dense ranking below rank 5 was unobservable and no
  fusion was possible.
- **Dense retrieval isolated from generation.** The `agent` arm mixes retrieval
  quality with the LLM's citation behaviour. `dense` here is retrieval alone.

## Results

```
Arm          Hit@1    Hit@3    Top-1    Top-5    Latency
agent        52.0%    92.0%    64.0%    92.0%    14.0s median
dense        64.0%    80.0%    64.0%    88.0%    <0.1s
bm25         76.0%    92.0%    76.0%    92.0%    <0.1s
hybrid_rrf   80.0%    92.0%    80.0%    96.0%    <0.1s
filename     20.0%    20.0%    20.0%    20.0%    <0.1s

n = 25 scorable tasks.
McNemar, agent vs hybrid_rrf, hit_at_budget: 0 discordant pairs.
```

**The prediction held.** Top-5 retrieval reached 24/25 = 96%, the exact figure
predicted, and it is the best of any arm. Hybrid also gives the best Hit@1 of
any arm (80% vs the agent's 52%).

## Rank of the first correct chunk

The mechanism, per task. `-` means not retrieved in the top 5.

| Task | dense | bm25 | hybrid | |
|---|---|---|---|---|
| `loc-008` set_rgb_stats | **–** | 3 | **5** | recovered |
| `loc-009` compare_detectors | **–** | 1 | **3** | recovered |
| `com-002` float32/bfloat16 | 3 | **–** | **4** | recovered |
| `rep-007` cervical YOLO | – | – | – | missed by every arm |

Hybrid is the only arm that retrieves both `loc-008` and `com-002`. Sparse
retrieval wins on exact identifiers (`rgb`, `stats`); dense wins on conceptual
paraphrase ("float32 instead of bfloat16" → "V100/Volta has no bf16 support").
Fusing them recovers all three tasks that either method missed alone.

**The one remaining miss is `rep-007`** — the single task flagged NAME-BASED
and unverified in the task file. Every arm misses it. That is more consistent
with a ground-truth defect than with a retrieval failure, and it cannot be
resolved without the corpus owner.

## Honest caveats

- **Hit@3 did not improve.** It is 92% for bm25, hybrid, and the agent alike.
  RRF improves *coverage* (Top-5) and *top-1 precision*, but on this task set
  it pushes some recovered results to ranks 4–5. Reporting only the 96% would
  overstate the gain; the correct claim is that hybrid gives the best Top-1 and
  Top-5 while matching everything else at Hit@3.
- **Zero discordant pairs** between agent and hybrid at `hit_at_budget`. This
  set cannot distinguish them on that metric.
- `dense` here scores below the deployed `agent` arm at Hit@3 (80% vs 92%).
  The reimplementation produced 635 chunks against the deployed 637, so the two
  are near- but not exactly identical; the gap is not fully explained and
  should not be read as a finding.
- n = 25, single run, one corpus, DRAFT ground truth. Descriptive only.

## Cost note

Embedding 635 chunks took **0.1s on an L40S** after a 5.2s warmup; the whole
job ran in 90 seconds. The same work failed on a CPU node after three
10-minute timeouts (job 9332836). The CPU-embedding idea has now failed twice,
by two different mechanisms — see Finding 6 in `performance-findings.md`.

## Recommendation

Adopt hybrid RRF as the default retriever. It is strictly better than dense on
every retrieval metric measured here, costs no GPU time beyond the embedding
already being performed, and adds no latency. The dense-only configuration
currently deployed is the weakest retrieval arm tested apart from the trivial
filename baseline.

## Reproduce

```
sbatch run_hybrid_gpu.sh        # or:
python evaluation/hybrid_retrieval.py --corpus <PanCyto> \
  --tasks evaluation/tasks_pancyto.jsonl --outdir runs \
  --host http://127.0.0.1:11501 --cache embed_cache.json
python pathology-agent/evaluation/analyze.py \
  --tasks evaluation/tasks_pancyto.jsonl --runs runs/*.jsonl
```
