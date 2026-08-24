# Review findings — 2026-07-29

Three independent reviews were run: an adversarial methods/statistics referee, a
literature search testing the novelty claim, and a check of the target journal's
actual requirements. This records what they found and what was done about it.

---

## 1. The deadline is not a problem

**Submission deadline for the *BioData Mining* collection "Uses of Agentic AI in
Biodata Mining" is 27 April 2027.** Status: open for submissions. Confirmed on two
independent pages.

Guest editors: **Zeeshan Ahmed** (Rutgers), **Saman Zeeshan** (Univ. Missouri).
Editor-in-Chief: **Nicholas Tatonetti** (Cedars-Sinai).

This removes all time pressure and changes the strategy entirely: there is room to
do the evaluation properly rather than rushing a thin version for late August. The
EDIT program deliverable (paper + presentation + poster, ~late August) and the
journal submission are now **two separate deliverables on different timelines.**

## 2. Four verified bugs in the evaluation code — all fixed

The adversarial referee executed the code and reproduced each. **Every one biased
results in the project's favour**, which is the worst direction for an error.

| # | Bug | Effect | Status |
|---|---|---|---|
| 1 | `path_exists` matched on bare basename | With `src/utils.py` in the manifest, the invented path `totally/made/up/dir/utils.py` scored as **existing**. Lab corpora are full of `utils.py`, `README.md`, `config.yaml`, so hallucination rate was driven toward zero artifactually. | **Fixed** — strict path matching by default; basename leniency is opt-in and reportable only as a sensitivity analysis. |
| 2 | Empty retrieval excluded from the denominator | A retrieval that returned nothing scored as *not applicable* instead of a miss, so the worst failures vanished from the rate. | **Fixed** — `[]` is now distinguished from "no retrieval step", and counts as 0. |
| 3 | Duplicate task ids silently overwrote | With 3 participants, the paired test kept only the last-written one, while the aggregate counted all 3 as independent tasks (n=90 from 30 tasks). No `participant_id` existed. | **Fixed** — duplicates excluded from the paired test and reported; `participant_id` added; participant count surfaced with a pseudo-replication warning. |
| 4 | Infrastructure errors scored as model failures | An Ollama timeout produced no sources and was counted as a wrong answer. | **Fixed** — errors excluded from all rates and reported separately. |

Two further issues found and fixed:
- `_normalize` used `lstrip("./")`, which strips *characters*, silently rewriting
  `../../etc/x.py` into `etc/x.py` — on the primary metric's code path. Fixed, and
  paths containing a `..` segment are now rejected outright since they escape the
  corpus root and cannot be validated against a root-relative manifest.
- The cross-arm metric gave the agent five candidate files while a human named
  one — comparing recall@5 against recall@1. Fixed with an equal
  `CANDIDATE_BUDGET` for every arm, reporting hit@1 and hit@3 plus the mean number
  of candidates offered.

Added: task-level hallucination (a genuine Bernoulli trial per answer) as primary,
with the pooled citation-level rate demoted to secondary; a citation rate so the
metric can't be gamed by vagueness; and an explicit warning when fewer than 6
discordant pairs make `p<0.05` arithmetically unattainable.

**71 tests pass**, including a regression test for every bug above.

## 3. The novelty claim is refuted as written

The literature search found that **every individual property of the claim is
occupied by published work**, and four of five pairwise combinations too. Closest
prior work, in order of threat:

1. **Paper2Agent** (arXiv:2509.06917) — analyzes a paper *and its codebase*, builds
   an MCP server, checks that agents reproduce the original results. Occupies
   "personalized to a project's own code" + "evaluated by reproducing the work."
2. **GPT4DFCI-RAG** (Omar et al., *Lancet Digital Health* 2024,
   doi:10.1016/S2589-7500(24)00114-6) — RAG over the PathML computational-pathology
   codebase inside a private institutional deployment, evaluated for accuracy and
   hallucination. The nearest neighbour in this exact domain, and two years old.
3. **BRAD** (*Bioinformatics* 2025, doi:10.1093/bioinformatics/btaf159) —
   open-source, locally runnable biomedical agent framework with a RAG module.
4. **Nekrutenko** (bioRxiv 2026.05.13.724985) — open-weight models for agentic
   analysis in a typical biomedical lab. Two months old.
5. **Nowak et al.** (arXiv:2604.22768) — secure on-premise open-weight LLM
   deployment in radiology, with a prospective pilot. Kills any novelty claim for
   the deployment architecture.

**What is genuinely defensible instead** (stated conservatively):
- The **corpus** is unpublished working material — exploratory notebooks, one-off
  scripts, internal notes, inconsistent naming — not release-quality repositories
  or public documentation. That is a harder and apparently unaddressed retrieval
  setting. **This is the strongest honest claim.**
- The **task class** is provenance and navigation ("which notebook produced this?"),
  not analysis execution, which is what nearly the whole agent literature measures.
- The **evaluation is in situ**, with the original researchers as the answer key:
  lower external validity, higher ecological validity than a portable benchmark.
- A **zero-egress posture** over unpublished internal material.

**Commercial prior art is real and must be cited.** Modella AI's **Judith** exists
(vendor page retrieved), is a research-use agent for biomedical *image analysis*,
is in preview, spun out of the Mahmood Lab, and Modella AI has announced
acquisition by AstraZeneca. It has **no publication and no public evaluation**. It
is not prior art for our claim — closed-source, not verifiably local, operates on
imaging data rather than a lab's code and documentation — but a reviewer who finds
it unmentioned will assume we didn't look.

**Reusable evaluation prior art** — cite rather than presenting a bespoke design as
new: **CORE-Bench** (arXiv:2409.11363) for reproduction-from-code tasks,
**BiomniBench** (bioRxiv 2026.05.12.724604) for author-keyed process-level rubrics,
**ScienceAgentBench** (arXiv:2410.05080) for the expert-validation protocol, and
**RAGAs** (EACL 2024) for grounding metrics.

## 4. Two experiments that must be added

Both were flagged independently by the methods referee and the literature review,
which makes them the highest-confidence recommendations here.

**(a) Same model, no retrieval.** Holds model scale constant and varies only
grounding. This is the experiment that converts the central claim from a definition
into a causal one — and it is the real falsifier. Zero egress, zero approvals, runs
on the existing node.

**(b) A lexical baseline — `ripgrep` or BM25 over the identical corpus, no LLM.**
The first reviewer question will be "does this beat `grep`?" It is the cheapest
experiment in the study and its absence is the strongest available argument that
the work demonstrates nothing new.

The external frontier-model arm is a **straw man**: asked "where is the QC
notebook?", a model with no lab access cannot know, so its score is ~0 by
construction. Keep it only as a sanity check, not a hypothesis test.

## 5. Claims to drop

| Claim | Verdict |
|---|---|
| Reduced time-to-analysis | **Drop or redesign.** There is no timed human-plus-agent condition, so the construct isn't instrumented. Agent latency and human wall-clock are different quantities. |
| Improved reproducibility | **Drop or replace the instrument.** A rater who already knows the analysis judging "could this be re-run" measures recognition. The defensible version: have someone who has *not* seen the analysis actually attempt to reproduce 2–3 figures. |
| Better reuse of prior work | **Drop entirely.** No metric operationalizes it. |
| The success-threshold table | **Remove from the paper.** The numbers aren't literature-anchored; keeping them invites "you set the bar where you could clear it." Retain in the protocol as a dated pre-commitment. |
| "Agent framework" | **Rename.** If the system does retrieval-augmented QA without planning or tool use, calling it an agent framework is overclaiming and will contaminate a reviewer's reading of everything else. "Retrieval assistant" costs nothing and buys credibility. |

## 6. Journal requirements

**Article type: `Software` or `Methodology`.** Software has a dedicated
`Implementation` section and its spec explicitly permits a case study — but it
requires "broad utility" and "direct comparison with available related software,"
which a deliberately lab-specific tool may fail. **Methodology is the safer
fallback** and reuses the standard Background/Methods/Results/Discussion/Conclusions
structure.

Concrete requirements: structured abstract **≤350 words**; **3–10 keywords**;
**no** main-text word, figure, table or reference limits; **Vancouver** references
with all URLs in the reference list (not inline) with access dates; all seven
**Declarations** headings present, each completed or marked "Not applicable."

**An archived DOI-bearing release is required** (Zenodo recommended for GitHub),
plus a link to the current version. License must be named; no specific license is
mandated. Peer review is **transparent** — reviewer reports publish alongside the
article. APC is **£2090/$2790/€2290**; waiver requests must be filed **at
submission** and cannot be made later. AI-generated images are prohibited. LLM use
must be documented in Methods. LLMs cannot be authors.

**Ethics needs attention now.** BMC states retrospective ethics approval "usually
cannot be obtained," so the IRB determination should be settled **before** further
evaluation runs — including whether timing human participants in the human arm
needs its own determination. Get it in writing with the committee's name, even if
the outcome is an exemption.

## 7. The strongest honest claim this design can support

Per the referee, if everything goes well and the fixes hold:

> On a frozen, pre-registered task set derived from one completed project in one
> academic pathology lab, a locally-hosted open-weight model with retrieval over
> the project directory surfaced the correct file among its top three candidates in
> X% of locate/reproduce tasks, versus Y% for the identical model without retrieval
> and Z% for a lexical search baseline. It cited nonexistent paths in A% of
> answers and correctly declined on B of N control tasks whose answers were never
> written down. We release the harness, task schema, and all raw logs. We do not
> claim time savings, improved reproducibility, generalization beyond this lab, or
> that grounding outweighs model scale.

What carries that paragraph is the **ablation**, the **lexical baseline**, the
**abstention/calibration result**, and the **released artifacts** — not the human
arm and not the frontier-model arm.

## 8. Still blocking

1. **A completed analysis with recoverable ground truth must be confirmed to
   exist.** Without it there is no retrospective study, only a demo. Only Dr. Levy
   can answer this.
2. **IRB determination**, in writing, before further evaluation runs.
3. **Rewrite the gap statement** using the corpus/evaluation framing above.
4. Decide **Software vs Methodology**, and whether the system is honestly an
   "agent" or a "retrieval assistant."
5. Every citation must be **opened and read** before it enters the manuscript. One
   reference in an earlier draft of `PROVENANCE.md` was mischaracterized because it
   was copied from an internal planning document rather than read.
