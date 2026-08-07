# Evaluation Protocol — Retrospective Case Study

**A Lab-Personalized AI Agent for Reproducible Digital Pathology Research**
EDIT AI/ML 2026 · Team 4 · Aim 3

> This is the protocol that turns the build into a research result. It should be
> **pre-registered** — agreed with mentors and frozen *before* data collection —
> so success thresholds aren't set after seeing outcomes.
> **[CONFIRM]** marks decisions needed from Zarif / Dr. Levy.

---

## 1. Research question

> Can an AI agent built from open-source LLMs, indexed over a lab's own notebooks,
> scripts, and HPC file structures, accurately assist researchers in identifying
> workflows, recreating past analyses, and producing organized research summaries
> — and does lab-specific grounding outperform a general-purpose assistant?

**Primary hypothesis (H1).** The lab-personalized agent achieves higher retrieval
accuracy on lab-specific tasks than a generic frontier LLM without lab context.

**Secondary hypotheses.**
- **H2:** Agent-assisted researchers complete tasks faster than unaided ones.
- **H3:** Agent-produced workflow summaries are rated as reproducible by blinded
  raters at a higher rate than unaided reconstructions.
- **H4 (falsifier).** The agent fails on tasks requiring undocumented knowledge.
  We expect this and will report it — it bounds the honest claim.

## 2. Design

**Retrospective case study on a completed lab project**, with three arms
evaluated on an identical task set.

| Arm | Description | Purpose |
|---|---|---|
| **A. Unaided human** | Lab member with normal access (filesystem, Slack, Git) but no agent | Human baseline |
| **B. Generic LLM** | Frontier chat model, no lab indexing; may be pasted file listings but has no retrieval over lab content | Tests whether *lab grounding* matters vs. raw model capability |
| **C. Lab-personalized agent** | Our system: Qwen3-Coder + ChromaDB index over the project directory | The intervention |

This three-arm structure is what makes H1 testable. A two-arm design (human vs.
ours) would confound "having an assistant" with "having a *lab-grounded*
assistant" — the actual claim.

**Case study subject.** Proposed: **ColoCare Recurrence G4X** (spatial
transcriptomics, colorectal cancer, linked recurrence outcomes). It matches the
motivating question in the project description almost verbatim.
**[CONFIRM: (a) is this the right project? (b) is there a *completed* analysis with
a known-correct answer trail? A retrospective study requires ground truth to
exist. If not available, fall back to a project the team can fully reconstruct.]**

## 3. Task set

Target **n = 30 tasks**, stratified across four categories. Tasks are written by
someone with access to the completed project, then **validated by a lab member
who did not write them** to confirm each has an unambiguous correct answer.

| # | Category | n | Example | Primary metric |
|---|---|---|---|---|
| 1 | **Locate** | 10 | "Where is the QC notebook for this cohort?" | Top-5 retrieval accuracy |
| 2 | **Comprehend** | 8 | "What preprocessing was applied to the H&E images?" | Rated correctness |
| 3 | **Reproduce** | 7 | "What steps would regenerate Figure 3?" | Reproducibility rating |
| 4 | **Undocumented (control)** | 5 | Questions whose answers were never written down | Expected failure — calibration |

Category 4 is deliberate. It measures whether the agent **correctly declines**
rather than hallucinating, and it prevents us from overclaiming. An agent that
confidently invents an answer here is worse than one that says "not found."

**Ground truth.** For each task, record: the correct file path(s), the correct
short answer, and the provenance of that answer (who confirmed it, when). Store
as `evaluation/tasks.jsonl`, one object per task, committed to the repo.
**Freeze the task set before running any arm.**

## 4. Metrics

Definitions are fixed here so they can't drift. Metric vocabulary is aligned with
the lab's existing local-LLM benchmarking work (accuracy, hallucination rate,
inference speed, computational cost, robustness).

**Primary, comparable across all arms**
- `file_identified_rate`: the correct file was **put in front of the user** — for
  the agent, the source list shown in its reply; for a human or an external
  model, the paths they named.

  This, not top-k, is what cross-arm comparisons (H1) are tested on. Top-k
  requires a retrieval step, which arms A and B do not have, so comparing the
  agent's top-k against a human's is not a like-for-like comparison. Using
  `file_identified` keeps the primary hypothesis testable with one definition
  that means the same thing everywhere.

**Retrieval diagnostics (agent arm only)**
- `top1_accuracy` / `top5_accuracy`: the correct file is the source of the
  top-ranked retrieved **chunk** / of any of the top-5 retrieved chunks.

  Deliberately computed over rank-ordered *chunks*, not over the deduplicated
  file list. With `TOP_K = 5`, five chunks commonly collapse to two or three
  distinct files, so a "top-5" window over unique files would quietly mean "was
  the file retrieved at all" while still carrying a rank-5 label. `analyze.py`
  also reports `mean_unique_sources` so the size of that collapse is visible.

  **Ceiling:** `lab_rag.TOP_K = 5`, so k > 5 is unmeasurable without changing the
  retrieval depth. State that rather than implying recall was measured deeper.

**Grounding**
- `path_hallucination_rate`: fraction of file paths cited in prose that **do not
  exist** in the frozen manifest. Automatically checkable, no rater needed — the
  most objective metric here, and the one to report most prominently.

  Two honest caveats: it is a **citation-level** rate pooled across tasks, so an
  answer citing many files carries more weight than one citing a single file; and
  citations within a single answer are not independent, so the confidence interval
  is optimistic. Path matching also falls back to basename, which makes the count
  **conservative** — it under-reports hallucination rather than over-reporting it.

**Answer quality** (blinded human rating, 3-point scale: correct / partially
correct / incorrect)
- `correctness`: is the answer factually right?
- `usefulness`: would this have saved you time? (1–5 Likert)
- `reproducibility`: could you re-run the analysis from this answer alone? (yes /
  partially / no)

**Efficiency**
- `time_to_answer`: wall-clock seconds from task start to the participant
  recording an answer (arms A and C).
- `inference_latency`: agent-side seconds per query (arm C) — separates model
  cost from human cost.

**Appropriate refusal** (category 4 only)
- `correct_abstention_rate`: fraction of undocumented-answer tasks where the
  system said it could not find the answer instead of fabricating one.

**Cost / feasibility** (reported, not hypothesis-tested)
- Peak GPU memory, index size on disk, indexing wall-clock time, model size.
  These support the "runs on institutional hardware" claim.

## 5. Procedure

1. **Index.** Run `python lab_rag.py index <project_dir>` on Discovery. Record the
   index timestamp, file count, chunk count, and a directory listing snapshot.
   (The lab's archiving effort means paths shift — the snapshot is what makes the
   result reproducible later.)
2. **Freeze** the task set and the index. No changes after this point.
3. **Run arm C** (agent): submit all 30 tasks; log question, retrieved chunks,
   cited paths, answer text, and latency to `evaluation/runs/agent.jsonl`.
4. **Run arm B** (generic LLM): same 30 tasks, same phrasing, no lab index.
5. **Run arm A** (human): participants attempt tasks with normal tooling, timed.
   **[CONFIRM: how many participants can we realistically recruit? Even n=2–3 lab
   members is enough to report descriptively; be honest that it is not powered
   for inference.]**
6. **Rate.** Blinded raters score arm outputs with arm labels stripped and order
   randomized. **[CONFIRM: who rates? Ideally a lab member not on this team.]**
7. **Analyze** per §6.

**Randomization & blinding.** Task order randomized per participant (fixed seed,
recorded). Raters blinded to arm. Full blinding of arm A is impossible (the human
knows whether they used a tool) — state this as a limitation.

## 6. Analysis plan

- Primary: compare `file_identified_rate` between arms B and C (exact McNemar on
  paired per-task outcomes, since all arms see identical tasks). Not top-k — see
  §4 for why that would not be like-for-like.
- **Multiple comparisons:** testing the agent against both arm A and arm B means
  two tests. No correction is applied in `analyze.py`; either apply one when
  reporting, or state plainly that the p-values are uncorrected and descriptive.
- Secondary: `time_to_answer` A vs. C (paired test or Wilcoxon signed-rank given
  small n); rating distributions by arm.
- Report **effect sizes and confidence intervals**, not just p-values. With
  n=30 tasks and few participants, this study is descriptive; say so plainly
  rather than implying it is powered.
- Report per-category breakdowns — an agent strong on Locate and weak on
  Reproduce is a more informative (and more credible) result than a single
  headline number.

## 7. Pre-registered success criteria

Mirrors the design doc. Agreed **before** data collection:

| Metric | Threshold |
|---|---|
| Correct file identified (arm C) | ≥ 80% |
| Top-5 chunk retrieval (arm C) | ≥ 80% |
| Answer correctness (arm C, rated) | ≥ 70% |
| Path hallucination rate (arm C) | ≤ 10% |
| Correct abstention (category 4) | ≥ 60% |
| Arm C vs. arm B on `file_identified` | C > B |
| Time-to-answer, arm C vs. arm A | Reduction |

**These numbers are proposed anchors, not derived from prior literature.** No
comparable lab-personalized-agent benchmark exists to calibrate against, so treat
them as a pre-commitment device rather than an established bar, and say so in the
paper. Mentors should sign off before data collection.

**A null or negative result is still publishable** and will be reported as such.
The framing "we built a lab-personalized agent and measured honestly what it can
and cannot do" is a stronger contribution than an unsupported success claim.

## 8. Threats to validity

- **Task-authoring bias.** Whoever writes the tasks knows the agent — mitigated
  by independent validation of each task.
- **Index-timing confound.** Files may move during the study; the frozen snapshot
  and timestamps address this.
- **Small n.** Limits inference; reported descriptively.
- **Single case study.** Limits generalization; claim demonstration only.
- **Rater familiarity.** A rater who knows the project may over-credit vague
  answers; the written rubric mitigates this.
- **Arm B fairness.** The generic LLM must be given a genuinely fair shot (a
  reasonable prompt and any non-sensitive context a researcher could legitimately
  paste) or the comparison is a straw man. Document exactly what it received.
- **Data privacy in arm B.** ⚠️ **No patient data, identifiable content, or
  restricted lab files may be sent to an external API.** Arm B must run only on
  de-identified or synthetic task phrasings. **[CONFIRM this with Dr. Levy before
  running arm B at all — it is the one part of this protocol that touches
  external services.]**

## 9. Artifacts to produce

- `evaluation/tasks.jsonl` — frozen task set with ground truth
- `evaluation/runs/{agent,generic,human}.jsonl` — raw per-task logs
- `evaluation/ratings.csv` — blinded ratings
- `evaluation/analyze.py` — computes every metric above from the logs
- `evaluation/README.md` — how to reproduce the whole evaluation

Committing these makes the paper's results independently checkable, which is the
single most credible thing a short paper can do.

## 10. Mapping to the paper

Per the team's own framing — *"framework + process + case study + repo"*:

| Paper section | Source |
|---|---|
| Introduction / Gap | Design doc: privacy constraint, Modella/Judith prior art |
| Methods | Design doc §Approach + §3–5 here |
| Results | §4 metrics, per-category breakdown, cost table |
| Discussion | §7 vs. actual, §8 threats, category-4 failures |
| Limitations | Design doc §Limitations + §8 |

Prior EDIT Advanced Track papers run ~1,400 words with a concise Results section
— this protocol produces more than enough substance for that format.

---

## Immediate next actions

1. **[Blocking]** Confirm the case-study project and that a completed analysis
   with recoverable ground truth exists.
2. **[Blocking]** Get Discovery access + the project folder path to index.
3. Draft the 30 tasks; have a non-author validate them.
4. Get mentor sign-off on §7 thresholds **before** running anything.
5. Resolve the read-only vs. write-capable question in the design doc.
6. Confirm the *BioData Mining* collection deadline.
