# Pilot results: the multi-file hypothesis did not hold

**Synthetic corpus. Not reportable. Do not put any number here in an abstract.**

Run on the 15-file synthetic corpus, 19 frozen tasks, both arms identical
corpus and task set, qwen3:4b locally. Raw records in `pilot_bm25.jsonl` and
`pilot_agent.jsonl`, scored output in `pilot_results.txt`.

## What was being tested

That the earlier BM25 tie was an artifact of a task set weighted toward
single-file lookup, and that the two arms would separate on questions whose
answer spans several files.

## What happened

**Whole-chain recovery (every required file named):**

| stratum | BM25 | agent |
|---|---|---|
| single_file | 7/7 (100%) | 7/7 (100%) |
| multi_file | **3/8 (38%)** | **3/8 (38%)** |

Exact tie. Four discordant pairs, two in each direction, p = 1.0. Not even a
directional signal.

**Any-file hit (the old outcome):**

| stratum | BM25 | agent |
|---|---|---|
| single_file | 7/7 | 7/7 |
| multi_file | 6/8 (75%) | **8/8 (100%)** |

Two discordant, both favouring the agent, p = 0.5.

**Abstention on questions with no recorded answer:** agent 3/4, BM25 0/4.

## Reading it honestly

**The hypothesis failed.** The agent does not recover complete file chains
better than keyword search, on a corpus that was deliberately built to contain
such chains. This was the pre-registered falsifier and it fired.

**The one real difference is weaker than it looks.** The agent surfaced at least
one correct file on every multi-file question where BM25 missed two. So it is
more reliable at finding *something* relevant, and no better at finding
*everything*. On a reproducibility claim, finding something is not the point.

**The abstention gap is close to definitional, not empirical.** BM25 has no
mechanism for declining: it returns its top-ranked files whatever is asked, and
only abstains when literally nothing matches, which on a 15-file corpus is
almost never. Scoring 0/4 was structurally guaranteed. The meaningful comparison
for abstention is against an ungrounded language model, which is the `norag` arm
that already exists and was not run here.

**Everything is underpowered.** Eight multi-file tasks. Exact McNemar cannot
reach p < 0.05 below six discordant pairs, and no stratum got there. This
distinguishes nothing, and the analyzer says so via `significance_attainable`.

## What this changes

The recommended direction was retrospective provenance recovery, on the
reasoning that multi-file chains are where an agent earns its place. **This
pilot does not support spending cluster time on that claim.** It cost a few
hours instead of finding out after getting Discovery access and a lab member's
time, which is exactly what a pilot is for.

The axis where the agent visibly differs is calibration: knowing when the answer
is not recorded. That was ranked second and should probably move up, but it has
to be tested against an ungrounded model rather than against a keyword baseline
that cannot abstain by construction.

## Before anyone reruns this

Two bugs invalidated the first attempt and both are now guarded:

1. **A stale vector index.** Six files were added and ChromaDB was never
   rebuilt, so BM25 read fifteen files and the agent's search saw nine. The
   agent correctly reported that indexed-nowhere files "do not exist" and the
   comparison was meaningless. `lab_query.index_drift()` now detects this and
   the runner aborts on it.
2. **The abstention detector did not recognise the phrasing its own prompt asks
   for**, scoring three genuine abstentions as three hallucinations.

A third issue was a scoring rule, not a bug in the system: whole-chain recovery
was being scored against a truncated candidate list, which punished the agent
for answering a "what is the chain" question with the correct six-step pipeline
in narrative order. Now untruncated, with precision reported instead.

## Caveats that would matter if this were real

- Synthetic corpus, hand-written by someone who knew what was being tested.
- The corpus extension degraded BM25 on one single-file question for reasons
  unrelated to the hypothesis (cohort A/B lexical ambiguity). Recorded in
  `PILOT_NOTES.md` and covered by a regression test.
- One replicate. Temperature 0 and a fixed seed, but no repeat runs.
- Ground truth written by the same person who wrote the questions.
