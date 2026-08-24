# Retrieval evaluation: PanCyto corpus

First evaluation of the agent against a real lab project rather than our own
files. Run 2026-08-24.

## Setup

| | |
|---|---|
| Corpus | `projects/PanCyto` (Aaditya Panchal), used with his permission |
| Indexed | `scripts/`, `configs/`, `notebooks/` only |
| Excluded | `corpus/`, `eval/`, `runs/`, `compare*/`, `test_slides/`, `extraction/`, `third_party/` |
| Size | 49 files, 637 chunks |
| Index build time | 46s |
| Node | `gv01`, Tesla V100 32GB |
| Model | Qwen3-Coder 30.5B (Q4_K_M, 18.6GB) via Ollama |
| Tasks | 30 (`evaluation/tasks_pancyto.jsonl`) |
| Raw records | `evaluation/results/pancyto_agent_2026-08-24.jsonl` |

Exclusions were not incidental. `eval/train_files.txt` and
`eval/eval_holdout_slides.txt` are slide-ID lists, and `.txt` is in the
indexer's default extension set. `compare*/` filenames (`469506_RGB.png`) look
like accession numbers, and `chunk_text()` stamps the file path into every
chunk, so paths enter the vector store alongside contents. A post-index check
confirmed nothing outside the three permitted folders was stored.

## Results

```
Hit@3 (capped)         92.0%   23/25    95% CI 75-98%
Hit@1 (capped)         52.0%   13/25    95% CI 34-70%
Top-5 retrieval        92.0%   23/25    (chunk level)
Top-1 retrieval        64.0%   16/25
Answers citing a path  80.0%   24/30
Correct abstention     80.0%    4/5     95% CI 38-96%
False abstention        0.0%    0/25    95% CI 0-13%
Latency                median 14.0s, mean 17.6s, range 13.2-115.7s

By category:
  locate        n=10   hit@3   90.0%
  comprehend    n=8    hit@3  100.0%
  reproduce     n=7    hit@3   85.7%
```

The 115.7s latency outlier is the first query of the session, consistent with
the ~77s cold-start model load documented in `performance-findings.md`. Median
latency reflects steady state.

## The three failures

### 1 & 2. Retrieval misses, both from the same cause

**`set_rgb_stats.py` not retrieved** for "where do we measure per-channel mean
and standard deviation on the training crops?" Returned `build_eval_set.py`,
`audit_crops.py`, `finetune_smoke.sbatch`.

**`run_cervical_extraction_yolo.sbatch` not retrieved** for "how do I run the
cervical extraction with YOLO as a batch job?" Returned
`run_thyroid_extraction.sbatch` and other extraction scripts.

The second miss is diagnostic: retrieval found the correct *kind* of file, an
sbatch extraction runner, but the wrong **specimen type**. Dense embedding
search matches meaning, and "cervical" and "thyroid" are near neighbours in
that space. Likewise "per-channel mean and standard deviation" is semantically
adjacent to any statistics code, while the target file is named for the exact
tokens "rgb" and "stats".

Both failures would be resolved by hybrid retrieval (BM25 keyword search
combined with dense vectors). This was hypothesised before the run; it now has
supporting evidence.

### 3. Over-claim on a control question

Asked "what funding source supported this project?", the system answered:

> The project was supported by the funding source "qdp-alpha". This is
> indicated in the `finetune_smoke.sbatch` script where the
> `#SBATCH --account=qdp-alpha` line specifies the account associated with the
> funding source.

Nothing was invented: `--account=qdp-alpha` is genuinely present in that file.
The failure is over-interpretation, treating a SLURM billing account as a
funding source, stated without hedging and with a citation that checks out.

This is a harder failure mode to detect than fabrication, because the standard
defence (does the cited file exist, does it contain the quoted text) passes.

## Correction applied to the scoring

The initial run reported 60% correct abstention (3/5). Reading the five control
answers showed four were genuine refusals. `und-004` was misclassified.

Cause: the abstention marker list in `lab_query.py` contains
`"does not contain information"` but not the plural `"do not contain
information"`. The model wrote "do not contain information about the source
hospital". A grammar-agreement gap, not a semantic one.

Repair: added the plural forms of markers already present. Verified that no
answerable task changed classification.

An earlier, broader repair attempt was **rejected**. Adding `"does not
specify"` reclassified two *answerable* comprehend tasks as refusals, because
the model hedges before answering:

> "The provided context does not specify the macro-F1 score of the frozen
> pretrained baseline. The files mention that the frozen baseline used ImageNet
> statistics and achieved a score of **0.775**"

That answer contains a refusal phrase and the correct answer. String-matched
abstention detection is unreliable in both directions and should be treated as
an approximation. With n=5 controls, the classification here was done by
reading each answer.

Separately, this hedging is worth noting as its own behaviour: the system
sometimes disclaims knowledge it demonstrably has.

## Ground-truth verification

Because the ground truth was drafted by reading the corpus rather than by its
author, it was checked before the numbers were reported. Scripts are in
`evaluation/` so any claim below can be re-run.

**Machine-checked, passed:**

| Check | Script | Result |
|---|---|---|
| Every `comprehend` value exists in its claimed file | `verify_comprehend.py` | 8/8 pass |
| No `undocumented` control has an answer in the corpus | `verify_controls.py` | 5/5 clean |

The control check searches the **stored chunk text**, i.e. exactly what
retrieval can see, not the files on disk. That matters: a naive `grep` over
`scripts/` also matches `__pycache__/` and `.ipynb_checkpoints/`, which the
indexer skips and the model can never retrieve. Patterns searched included
consent, journal, submitted to, patient age, demographic, hospital, Hitchcock,
DHMC, medical center, institution, NIH, NSF, R01, P30, U01, grant, funding,
funded by, supported by, award.

**Two gray areas, disclosed rather than hidden:**

1. The string "Dartmouth" does occur once in the indexed text, in a comment
   about the cluster's `/etc/bashrc` handling of an unbound variable. It is
   unrelated to specimen provenance and the model did not use it, but
   `und-004` ("which hospital did the specimens come from?") is therefore not
   perfectly uncontaminated.
2. Scoring `und-005` as an over-claim is a judgement. The model reported the
   funding source as `qdp-alpha`, taken from a `#SBATCH --account` line. A
   SLURM billing account is not a funding source, but it is arguably adjacent
   to one. A reviewer could contest this call.

**Not machine-checkable, pending human review:**

The 10 `locate` and 7 `reproduce` answers rest on reading each script's
docstring. No program can confirm that a file does what a question asks.
`evaluation/gt_review_sheet.txt` pairs every claim with the file's own opening
lines for confirmation; regenerate it with `make_review_sheet.py`. `rep-007` is
the weakest item and is flagged in the task file as name-based only.

## Limitations

- **Five controls is too few.** The abstention interval (38-96%) establishes
  that over-claiming occurs, not how often.
- **Ground truth is DRAFT.** `comprehend` values were read from the files;
  `locate` answers derive from each script's docstring. Aaditya has offered to
  review. `rep-007` is name-based only and flagged as such in the task file.
- **Path hallucination not computed.** `analyze.py` needs `--manifest`; not
  supplied on this run.
- **Single run, one corpus, no repetition.** Descriptive, not inferential.
- **Corpus is code and config only.** Performance on notebooks with rich
  outputs, or on prose documentation, is untested.

## Next

1. Expand controls from 5 to ~15 so the abstention rate has a usable interval.
2. Add hybrid (BM25 + dense) retrieval and re-run. Both misses predict it helps;
   this is a testable claim.
3. Supply `--manifest` to obtain the path-hallucination rate.
4. Have the corpus owner confirm the `locate` ground truth.
5. Repeat on a second lab project to test whether results transfer.
