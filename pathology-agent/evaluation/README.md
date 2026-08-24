# Evaluation harness

Implements `docs/EVALUATION_PROTOCOL.md`. Produces the numbers that become the
paper's Results section.

**Pure standard library** — no numpy, scipy, or pandas. Runs on a bare Python 3.9+,
including a Discovery login node, and a reviewer can rerun it trivially.

## Files

| File | What it does |
|---|---|
| `tasks.py` | Task schema, JSONL loading, validation. Run directly to lint a task set. |
| `tasks.template.jsonl` | 30-task template. **Not scorable as-is** — ground truth is deliberately blank. |
| `run_eval.py` | Runs a task set through one arm, appends a JSONL run log. Resumable. |
| `analyze.py` | Computes every protocol metric, with confidence intervals and paired tests. |

## The three arms

| Arm | How it runs |
|---|---|
| `agent` | Automated. Calls `rag/lab_query.answer_question()`. Needs Ollama + a populated index (Discovery). |
| `human` | `--arm manual --arm-label human`, transcribed as the participant works. |
| `generic` | `--arm manual --arm-label generic`. **Run by a person in a browser**, not by this code — see below. |

### Why there's no automated external-API arm
Arm B compares against a generic model with no lab context, which means an
external service. `run_eval.py` intentionally does **not** implement that call.
Sending lab content off institutional infrastructure is a data-egress decision
that needs the PI's explicit written approval, and the project's constraints
forbid patient data leaving. Automating it would make the wrong thing easy to do
by accident. A human runs those queries on de-identified phrasings and transcribes
the results. **Do not add an API client here until Dr. Levy has signed off.**

## Workflow

**1. Freeze a manifest at index time.** Paths move (the lab is archiving data), so
capture what existed when the index was built:
```bash
python analyze.py --make-manifest /path/to/project > file_manifest.txt
```

**2. Build and validate the task set.**
```bash
cp tasks.template.jsonl tasks.jsonl
# edit: real questions, real expected_paths, real ground_truth_source
python tasks.py tasks.jsonl
```
Validation reports how many tasks are scorable. Placeholders — missing
`expected_paths` or `ground_truth_source` — are excluded from every metric, so a
half-finished task set produces *fewer* numbers rather than wrong ones.

**3. Freeze it.** Commit `tasks.jsonl` and `file_manifest.txt` before running any
arm, so thresholds can't be set after seeing results.

**4. Check the pipeline without touching the cluster.**
```bash
python run_eval.py --tasks tasks.jsonl --arm dryrun --out runs/dryrun.jsonl
```
Dry-run output is synthetic and flagged `"synthetic": true`. It validates plumbing
only and must never be reported.

**5. Run the arms.**
```bash
# On Discovery, after ./startup.sh
python run_eval.py --tasks tasks.jsonl --arm agent  --out runs/agent.jsonl

# Human and generic, transcribed
python run_eval.py --tasks tasks.jsonl --arm manual --arm-label human   --out runs/human.jsonl
python run_eval.py --tasks tasks.jsonl --arm manual --arm-label generic --out runs/generic.jsonl
```
Interrupted runs resume — already-recorded task ids are skipped.

**6. Score.**
```bash
python analyze.py --tasks tasks.jsonl \
                  --runs runs/agent.jsonl runs/generic.jsonl runs/human.jsonl \
                  --manifest file_manifest.txt \
                  --json results.json
```

## Metrics

| Metric | Definition | Needs |
|---|---|---|
| **`file_identified_rate`** | **Primary.** The correct file was put in front of the user — retrieved sources (agent) or paths named (human/generic). The only metric defined identically in every arm, so cross-arm comparisons use it. | `expected_paths` |
| `top1_accuracy` / `top5_accuracy` | Agent-only diagnostic. Expected file is the source of the top-1 / any top-5 retrieved **chunk**. Chunk-level and rank-ordered, *not* over deduplicated files. | `chunks` in the log |
| `mean_unique_sources` | How far 5 chunks collapse into distinct files — makes the dedup effect visible | — |
| `path_hallucination_rate` | Fraction of paths cited in prose that don't exist in the manifest | `--manifest` |
| `correct_abstention_rate` | On `undocumented` tasks, fraction where the system declined | undocumented tasks |
| `false_abstention_rate` | On answerable tasks, fraction where it declined anyway (over-abstaining is also a failure) | — |
| `latency_s` | mean / median / range | — |

**Why top-k is chunk-level.** `lab_rag.TOP_K = 5` retrieves five *chunks*, which
usually come from fewer than five distinct files. Scoring "top-5" over the
deduplicated file list would silently turn a rank-5 cutoff into "was the file
retrieved at all." So top-k is computed over rank-ordered chunk sources, and
reported as *not applicable* for arms with no retrieval step rather than computed
from something else. k > 5 is unmeasurable without raising `TOP_K`.

Proportions carry **95% Wilson score intervals** (well-behaved at small n and near
0/1, and deterministic). Arm comparisons use an **exact McNemar test** on paired
per-task outcomes — exact rather than chi-square because the discordant count will
be small. Comparing the agent to more than one arm is **multiple comparisons** and
no correction is applied; report accordingly.

`path_hallucination_rate` is the most valuable metric here: fully objective, no
rater needed, and directly answers "can we trust what it says?" Two caveats — it
is a **citation-level** rate pooled across tasks (answers citing many files weigh
more), and citations within one answer aren't independent, so its interval is
optimistic. Basename fallback matching makes the count **conservative**: it
under-reports hallucination rather than over-reporting it.

## Reading the output honestly

- Placeholder exclusions are printed to stderr. If most tasks are placeholders,
  the numbers describe a handful of tasks — say so.
- With n≈30 and few participants this is **descriptive**, not powered for
  inference. Report intervals, not bare point estimates (protocol §6).
- Retrieval metrics are only meaningful for the `agent` arm; manual arms have no
  retrieval step, so `sources` there is what the responder pointed at.
- A null or negative result is publishable. Honest measurement of what the agent
  can't do is a stronger contribution than an unsupported success claim.
