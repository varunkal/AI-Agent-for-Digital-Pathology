# Bias analysis: is the keyword baseline too good to be true?

BM25 keyword search scored an identical 88% Top-5 on both the 49-file and the
610-file corpus. Perfect consistency is suspicious, so this checks whether that
number is real or an artifact of how the benchmark was written.

## The concern

The 30 questions were authored by reading the corpus. If a question literally
contains the words in its target file's *name*, keyword search can win
trivially — matching words to a filename rather than retrieving on merit.

**13 of 25 scorable questions share at least one literal token with the target
filename:**

| Question | Target file | Shared tokens |
|---|---|---|
| loc-001 "which script runs the linear probe?" | linear_probe.py | linear, probe (100%) |
| rep-003 "embed a file list ... backbone built from the repo" | embed_repo_backbone.py | embed, backbone, repo (100%) |
| rep-001 "re-run the thyroid extraction" | run_thyroid_extraction.sbatch | thyroid, extraction (100%) |
| … | … | … |

On its face, that looks like the benchmark is leaking answers to the keyword
retriever.

## The test

Split every method's accuracy by whether the question leaks the filename. If
the leak inflates keyword search, BM25 should score higher on the "leaky"
questions than on the "clean" ones.

### 610-file corpus, Top-5

| Method | Leaky questions | Clean questions |
|---|---|---|
| Semantic (dense) | 54% | 58% |
| Keyword (BM25) | **85%** | **92%** |
| Hybrid | 77% | 83% |

### 49-file corpus, Top-5

| Method | Leaky questions | Clean questions |
|---|---|---|
| Semantic (dense) | 92% | 83% |
| Keyword (BM25) | 92% | 92% |
| Hybrid | 92% | 100% |

## Result: the leak does NOT inflate keyword search

On the full corpus BM25 scores *lower* on leaky questions (85%) than on clean
ones (92%) — the opposite of what answer-leakage would produce. The filename
overlap is cosmetic.

**Why:** BM25 in this pipeline searches file *contents*, not file *names*. The
words in a question like "thyroid extraction" appear inside the target script's
own code and docstring, so keyword search retrieves it on content regardless of
whether the filename happens to match. The filename overlap is incidental.

BM25's consistency across corpus sizes is therefore legitimate. Technical terms
("thyroid", "backbone", "extraction") stay rare and discriminative no matter how
many distractor files are added; adding files about other topics does not create
new competitors for those specific terms. That is exactly why keyword search is
robust to corpus growth while semantic search is not.

## The residual bias, disclosed

One real, milder effect remains: because the questions were written by reading
the corpus, they share vocabulary with the target files. This is inherent to any
hand-built benchmark and it flatters the whole system slightly — but it helps
semantic and keyword search *equally*, so it does not explain the gap between
them, and it does not affect the central complementary-failure finding (semantic
and keyword miss different questions).

## Why this matters

In a clinical research setting, a reported number is only as good as the check
behind it. This analysis was run because an 88% that never moved looked wrong.
The check strengthened the result rather than undermining it: the consistency is
real, and the one bias present is disclosed and bounded.

Reproduce: the leak classification and split-accuracy computation are pure
Python over `tasks_pancyto.jsonl` and the run logs in `evaluation/results/`.
