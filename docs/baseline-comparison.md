# Sparse retrieval baselines: is 92% Hit@3 actually good?

Run 2026-09-02. Same corpus, same 30 tasks, same scorer (`analyze.py`) as the
agent evaluation in `evaluation-results.md`.

## Why this run exists

The agent evaluation reported 92% Hit@3 with no baseline. A number with
nothing to compare it against does not say whether the system is good or
whether the task is easy. This run supplies the comparison.

Reproduce with:

```
python evaluation/baseline_retrieval.py \
  --corpus <PanCyto> --tasks evaluation/tasks_pancyto.jsonl --outdir runs
python pathology-agent/evaluation/analyze.py \
  --tasks evaluation/tasks_pancyto.jsonl --runs runs/*.jsonl
```

`baseline_retrieval.py` re-implements `lab_rag.py`'s ingestion and chunking
(800 chars, 100 overlap, same extensions, same three subdirectories) so the
arms see an identical corpus. It rebuilt 49 files / 635 chunks against the
indexed 49 files / 637 chunks; the two-chunk difference is an unreconciled
boundary edge case and is noted rather than hidden.

## Arms

| Arm | What it ranks by |
|---|---|
| `agent` | Dense embeddings, `nomic-embed-text` + Qwen3-Coder 30.5B (Q4_K_M) |
| `bm25_text` | BM25 over chunk text only. Fair comparison: `lab_rag.py:388` embeds `c["text"]`, so the dense retriever never sees the file path either |
| `bm25_path` | BM25 over path + chunk text |
| `filename` | Query/path token overlap. The trivial baseline |

## Results

```
Arm          Hit@1    Hit@3    Top-1     Top-5    Median latency
agent        52.0%    92.0%    64.0%     92.0%    14.0s
bm25_text    76.0%    92.0%    76.0%     92.0%    <0.1s
bm25_path    80.0%    92.0%    80.0%     92.0%    <0.1s
filename     20.0%    20.0%    20.0%     20.0%    <0.1s

n = 25 scorable tasks. All 95% CIs overlap heavily except filename.
McNemar, agent vs bm25_path, hit_at_budget: 22 both correct, 1 both wrong,
1 only agent, 1 only BM25. p = 1.0, 2 discordant pairs.
```

## What this means

**BM25 ties the agent at Hit@3 and beats it at Hit@1**, at roughly 1/1000th
the latency and with no GPU. The headline 92% is not evidence that dense
retrieval is working; a 1990s keyword algorithm reaches the same number.

**The benchmark is not trivial.** The filename baseline scores 20%. The tasks
require reading file contents, so the ties above are real ties, not an artifact
of easy questions.

**With 2 discordant pairs, this run cannot detect a difference even if one
exists.** p = 1.0 is not evidence of equivalence. What it does establish is
that no *large* dense advantage is present.

This independently reproduces Avilash's pilot result (agent 3/8 vs BM25 3/8,
p = 1.0, synthetic corpus). Two experiments, different corpora, same direction.

## The per-task table is the useful part

The two arms fail on *different* tasks:

| Task | Agent | BM25 | Why |
|---|---|---|---|
| `loc-008` `set_rgb_stats.py` | miss | hit@3 | "per-channel mean and standard deviation" is semantically adjacent to any statistics code. The literal tokens `rgb`/`stats` appear only in the target |
| `com-002` float32 vs bfloat16 | hit@3 | miss | The answer is "V100/Volta has no bf16 support". No shared keyword with the question; needs semantic matching |
| `rep-007` cervical YOLO sbatch | miss | miss | Missed by every arm. Also the one task flagged NAME-BASED in the task file, so it may be a ground-truth defect rather than a retrieval failure |

This is textbook complementary failure: sparse retrieval wins on exact
identifiers, dense wins on conceptual paraphrase. A hybrid would capture both
`loc-008` and `com-002`, giving 24/25 = 96%.

Hybrid retrieval was previously proposed on the strength of a hypothesis.
It now has a measured, per-task justification and a predicted target.

## What the LLM layer still contributes

The baselines retrieve. They do not answer. Not measurable in the sparse arms:

- 80% correct abstention (4/5 controls)
- 0% false abstention (0/25)
- 80% of answers citing a source path

The defensible claim is **not** "dense retrieval beat keyword search." It is
that the generation and abstention layer does work the baselines cannot,
while the retrieval layer does not currently justify its cost.

## Limitations

- n = 25 scorable tasks, single run, one corpus. Descriptive, not inferential.
- Ground truth is still DRAFT pending Aaditya's review. `rep-007` is the
  weakest item and is the task every arm missed.
- Comparing three arms against the agent is multiple comparisons; no
  correction applied.
- BM25 tokenization (camelCase splitting) was chosen before scoring but was
  not itself tuned or ablated.
- Corpus rebuild produced 635 chunks vs the indexed 637.

## Next

1. Implement hybrid (BM25 + dense) and re-run. Predicted 96%; `loc-008` and
   `com-002` are the tasks that must both flip.
2. Resolve `rep-007` with the corpus owner — retrieval failure or bad ground truth.
3. Expand controls from 5 to ~15 before quoting an abstention rate.
