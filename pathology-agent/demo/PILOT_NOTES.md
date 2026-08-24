# Pilot: does the agent separate from keyword search on multi-file questions?

**These results are NOT reportable.** The corpus is synthetic and hand-written.
This exists to decide whether the multi-file hypothesis is worth spending
Discovery time on, and nothing else. No number produced here belongs in an
abstract, a paper, or a slide.

## The question

The earlier evaluation found BM25 keyword search tied the assistant, 0
discordant pairs, p = 1.0, and that was recorded as an honest negative result.
This pilot tests a different explanation: that the tie is an artifact of the
task set rather than a fact about the system.

Roughly a third of the protocol's 30 tasks are Locate tasks such as "where is
the QC notebook". The answer is usually in the filename, so any lexical search
wins by construction. The repository-QA literature has independently flagged
the same trap, noting that many benchmark questions are solvable without
consulting the code at all.

If that is what happened, the two arms should tie on single-file questions and
separate on questions whose answer spans several files.

## Two changes that make the question answerable

**Stratify.** Every task is now single_file, multi_file, or unrecorded. The
stratum is derived from the ground truth (a task is multi-file exactly when
answering it requires naming more than one file) rather than declared, so it
cannot drift. Pooling across strata is what hid the effect.

**Score the whole chain, not any file.** The old outcome counted a hit if the
arm surfaced *any* expected path. On a two-file question that lets an arm which
found half the answer score identically to one that found all of it, which is
exactly how a keyword baseline ties a system that reasoned across files. The new
outcome, `all_paths_identified`, requires every expected path.

Candidate budget rises with the number of correct answers, `max(3, n_expected)`,
because an arm cannot name four files from three slots. It is identical for both
arms.

## How the corpus was extended

The original 9-file corpus had almost no genuine multi-file structure: one
duplicated constant. Six files were added to create realistic multi-file chains:
a second cohort with its own config, a shared QC module, an interface analysis
script and its figure notebook, and a changelog.

Questions were written from the kinds of task the project description names
(cohort selection, preprocessing decisions, figure generation, interface and
distance-to-tumour analysis), deliberately not from known agent strengths.

Every ground-truth claim was verified programmatically against the corpus before
any run. All 15 checks passed.

## The rigging risk, stated plainly

**If you write multi-file questions that a keyword search structurally cannot
answer, of course the agent wins.** That is the obvious way to fake this result
and it must be guarded against, not hand-waved.

Three guards:

1. **The single-file stratum is the control.** If BM25 also collapses there, the
   corpus simply got harder and the multi-file result means nothing on its own.
   Measured before running: BM25 still gets 6 of 7 single-file questions at
   rank 1 on the extended corpus, so its lexical strength is intact.

2. **One known confound is recorded, not hidden.** Adding a second cohort broke
   BM25 on one single-file question: "where is the QC notebook for cohort A"
   now ranks `config/pipeline_cohortB.yaml` first. Naming the cohort does not
   help, because the tokenizer splits "cohort A" into two terms while the
   filename carries "cohorta" as one. There is a regression test asserting this
   so it stays visible.

3. **Both arms get identical tasks, corpus and candidate budget.** BM25 is given
   a fair shot, as the protocol requires, rather than being set up to fail.

## What would falsify the hypothesis

The agent failing to beat BM25 on whole-chain recovery within the multi_file
stratum. If that happens, the direction is dead and the finding is that the
original tie was real. That would be worth knowing before asking anyone for
cluster access.

## Files

- `demo/pilot_tasks.jsonl` - the frozen stratified task set, 19 tasks
- `demo/corpus/` - 15 files, synthetic
- `evaluation/analyze.py` - `task_stratum`, `chain_budget`,
  `compare_arms_by_stratum`, `stratum_rates`
