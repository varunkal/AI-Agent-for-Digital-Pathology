# Paper skeleton

**Working title:** A Lab-Personalized, Locally-Hosted LLM Agent for Reproducible
Digital Pathology Research

Target: *BioData Mining* (Springer/BMC), collection **"Uses of Agentic AI in
Biodata Mining"** — shared by Dr. Levy 2026-07-28.
**[DEADLINE UNVERIFIED — page is behind Springer authentication.]**

## How to read this document

Three kinds of marker, used consistently:

| Marker | Meaning |
|---|---|
| **[WRITABLE NOW]** | Can be written truthfully today from verified facts. Draft text is provided. |
| **[NEEDS DATA]** | Cannot be written until the evaluation runs. Structure and table shells only — **no numbers, no placeholder results.** |
| **[NEEDS DECISION]** | A human must decide or confirm. Named where possible. |

Nothing in this skeleton asserts a result. Every factual claim traces to
`PROVENANCE.md`. Where a claim is unverified, it says so inline rather than being
smoothed over.

---

## Authorship and contributions — [NEEDS DECISION]

Repo README currently lists: Varun Kalidindi (Developer), Nehan Mohammed,
Avilash Angirekula (Developer), Zarif Azher (Faculty Mentor). Joshua Levy is the
PI. **The author list, order, and corresponding author are not ours to assume —
Zarif and Dr. Levy decide.**

BMC applies ICMJE criteria, which require *all* of: substantial contribution to
conception/design or data acquisition/analysis; drafting or critical revision;
final approval; and accountability. A per-author contribution statement is
mandatory. **[Agent is checking the exact BMC wording.]**

---

## Abstract — structured, ~250–350 words

BMC abstracts are typically **Background / Methods / Results / Conclusions**.
**[Exact limit being checked.]**

**Background.** [WRITABLE NOW] Digital pathology and spatial biology workflows
span H&E whole-slide images, spatial transcriptomics, cell-type annotations,
clinical metadata, statistical analyses and figure pipelines. In practice these
artifacts are distributed across HPC directories, notebooks and scripts, and some
decisions exist only in the memory of whoever ran the analysis, making completed
work costly to reproduce or extend. Commercial LLM assistants are poorly suited to
this setting because clinical data cannot leave institutional infrastructure.

**Methods.** [WRITABLE NOW] We built a lab-personalized research assistant that
runs entirely on institutional hardware: an open-weight Qwen3-Coder model served
by Ollama on a GPU node of Dartmouth's Discovery cluster, with retrieval-augmented
generation over the laboratory's own notebooks, scripts and documentation indexed
into a local ChromaDB vector store. Researcher access is through a Slack interface
that is read-only by construction. We specify a pre-registered retrospective
evaluation on a completed laboratory project, comparing an unaided researcher, a
general-purpose model without laboratory context, and the lab-grounded agent
across N tasks in four categories, including a control category whose answers were
never documented.

**Results.** [NEEDS DATA] One or two sentences: the primary comparison, the
hallucination rate, and the abstention behaviour on undocumented controls.

**Conclusions.** [NEEDS DATA — must follow from the results, not precede them.]
Note the resource figure (model size, peak memory) here if it supports the
"deployable on institutional hardware" point.

**Keywords:** retrieval-augmented generation; large language models; agentic AI;
digital pathology; spatial transcriptomics; reproducibility; privacy-preserving
computing; research software.

---

## 1. Background

**1.1 The reproducibility and reuse problem in computational pathology.**
[WRITABLE NOW] Artifacts scattered across HPC paths, notebooks, and undocumented
decisions; cost falls on new lab members and on anyone extending prior work.
*Needs 3–5 supporting citations on reproducibility in computational biology —
**[NEEDS DECISION: literature agent is gathering candidates].***

**1.2 Why commercial assistants don't fit.** [WRITABLE NOW] The lab works with
identifiable human tissue data under IRB. Sending lab content to an external API
is a data-egress decision, not a convenience trade-off. This is a hard constraint
that shapes the entire design, and it is the reason for local hosting.
*Supportable from the project's own stated constraint that agents must not send
data off institutional infrastructure (PROVENANCE.md).*

**1.3 Prior work.** [NEEDS DATA from the literature agent] Group into:
(i) agentic AI for scientific/biomedical discovery; (ii) RAG over code, notebooks
and institutional knowledge; (iii) LLM agents in digital pathology and spatial
biology; (iv) locally-hosted / privacy-preserving LLM deployment in clinical
settings; (v) evaluation frameworks and benchmarks for research-assistant agents.

**1.4 Gap and contribution.**
> ⚠️ **[BLOCKING]** The draft gap statement — *"we are not aware of an
> open-source, locally-hosted agent personalized to an individual lab's file
> structures and evaluated against real human effort"* — **is not currently
> supported by any literature search.** An unsupported priority claim is the single
> most likely cause of rejection. It must be either substantiated or softened to a
> positioning statement before submission. The literature agent is testing it now.

Contributions, stated conservatively and only as far as the evidence goes:
1. A locally-hosted, lab-personalized RAG assistant for computational pathology,
   released open-source.
2. A read-only safety design responsive to an explicit PI constraint, with the
   guardrail implemented and unit-tested rather than merely stated as policy.
3. A pre-registered evaluation protocol including an **undocumented-answer control
   category**, which measures fabrication directly instead of assuming grounding.
4. [NEEDS DATA] Empirical findings from a retrospective case study.

---

## 2. Methods

This is the section that can be written most completely today. Everything below is
verified against the source (see `PROVENANCE.md`).

**2.1 System architecture.** [WRITABLE NOW]
- Model: **Qwen3-Coder** (~18 GB), open weights, served locally by **Ollama**.
- Ollama exposes an OpenAI-compatible endpoint at `http://localhost:11434/v1`;
  all inference is on-node.
- Agent framework: **qwen-code v0.19.4**, permission-gated.
- Hardware: a **V100 GPU node** on Dartmouth's **Discovery** HPC cluster.
- Environment: Python 3.11, conda environment `labagent`.
- *Model-selection note worth reporting because it is a genuine practical finding:*
  Qwen2.5-Coder was evaluated first and rejected — it emitted tool calls as JSON
  text rather than executing them. Qwen3-Coder supports native tool calling. This
  is useful to anyone replicating the setup.

**2.2 Corpus construction and indexing.** [WRITABLE NOW]
- Indexable extensions: `.py .ipynb .md .txt .sh .yaml .yml .json .csv .tsv .r .R
  .cfg .conf .toml`. Hidden directories, `__pycache__`, `node_modules`, `.git` and
  `.ipynb_checkpoints` are skipped.
- Notebooks: markdown and code cell sources extracted, plus text outputs truncated
  to 500 characters per cell.
- CSV/TSV: first 50 lines only (header plus sample), to capture schema without
  ingesting data.
- Chunking: 800 characters with 100-character overlap, preferentially broken at a
  newline in the second half of the window. Each chunk is prefixed with its
  relative path and carries `source`, `start_char`, `filename` metadata.
- Embeddings: **nomic-embed-text** via Ollama. Store: **ChromaDB**, cosine space,
  collection `levy_lab`.
- **State honestly:** re-indexing replaces the collection, so the current
  implementation holds one project scope at a time.
- **State honestly:** embeddings are computed one request per chunk, which bounds
  indexing throughput.

**2.3 Retrieval and generation.** [WRITABLE NOW]
- Top-K = 5 chunks by cosine similarity over the question embedding.
- Retrieved chunks are concatenated with `Source: <path>` headers into the prompt.
- The prompt constrains the model to the provided context, instructs it to say so
  when the context is insufficient, and asks it to cite the files it used.
  **Reproduce the prompt verbatim in a supplementary figure — the prompt is part
  of the method.**
- A source-preserving query path returns the ranked chunk provenance alongside the
  answer, which is what makes retrieval measurable at all.

**2.4 Researcher interface.** [WRITABLE NOW]
- Slack bot using **Socket Mode** — an outbound WebSocket — so the service runs
  behind the HPC firewall with no public endpoint. Worth one sentence: this is the
  design detail that makes deployment beside the model feasible.
- Replies are threaded and list the retrieved file paths, so every answer is
  checkable against the filesystem.

**2.5 Safety design.** [WRITABLE NOW]
- Motivated by an explicit PI instruction to prevent agents modifying existing file
  structure, and by the project requirement that original research data must not
  be overwritten or modified.
- Implemented: an allowlist of readable roots; symlink resolution *before*
  containment checks (a prefix check on unresolved paths is trivially escapable);
  `commonpath`-based containment so a sibling directory sharing a name prefix is
  not treated as inside; refusal of protected components (`.git`, `.env`, SSH
  keys); and confinement of any write to a designated scratch directory.
- The researcher-facing Slack surface performs retrieval and generation only — no
  writes, no execution of model-authored code.
- **State the limitation plainly:** this is a guardrail for code that routes access
  through it, not an OS-level sandbox. It does not contain a process that calls
  `open()` directly or shells out. Overstating this would be the kind of security
  claim reviewers punish.

**2.6 Evaluation design.** [WRITABLE NOW as a protocol; results are [NEEDS DATA]]
- Retrospective case study on a **completed** laboratory project.
  **[NEEDS DECISION — BLOCKING: candidate is the ColoCare recurrence spatial
  transcriptomics cohort, but whether a completed analysis with recoverable ground
  truth exists is unconfirmed. Ask Dr. Levy. If none exists the design must
  change.]**
- Three arms: (A) unaided researcher; (B) general-purpose model without lab
  context; (C) the lab-grounded agent.
- Task set: N tasks across **locate**, **comprehend**, **reproduce**, and
  **undocumented** (control). Target 10/8/7/5. Ground truth confirmed by a person
  with lab access; tasks validated by someone who did not author them; the set is
  frozen before any arm runs.
- **Arm B is executed manually** on de-identified task phrasings — no automated
  external API path exists, by design. **[NEEDS DECISION: written PI approval
  required before any external query.]**

**2.7 Metrics.** [WRITABLE NOW]
- **Primary, cross-arm:** *correct file identified* — whether the correct file was
  put in front of the user (retrieved sources for arm C; files named for A and B).
  Justify explicitly: top-k requires a retrieval step that arms A and B do not
  have, so a top-k comparison would not be like-for-like.
- **Retrieval diagnostics (arm C only):** top-1 and top-5 over **rank-ordered
  chunks**, not deduplicated files. Justify: with K=5, chunks commonly collapse to
  fewer distinct files, so a deduplicated "top-5" silently becomes "retrieved at
  all." Report mean unique files per query so the collapse is visible. k>5 is not
  measurable at K=5.
- **Grounding:** path-hallucination rate — cited paths absent from a frozen file
  manifest. Fully automatic. Disclose that it is citation-level and pooled
  (answers citing more files weigh more), that within-answer citations are not
  independent (so the interval is optimistic), and that basename fallback matching
  makes it conservative.
- **Abstention:** correct abstention on undocumented controls, and false
  abstention on answerable tasks. Disclose the keyword heuristic and its failure
  mode ("no information about X, but here is Y" scores as abstention), and report
  agreement with a hand-checked sample.
- **Efficiency:** wall-clock time to answer; agent inference latency separately.
- **Cost/feasibility:** model size, peak GPU memory, index size, indexing time.

**2.8 Statistical analysis.** [WRITABLE NOW]
- Paired per-task outcomes; **exact McNemar** for arm comparisons (exact rather
  than chi-square given small discordant counts).
- **Wilson score intervals** for proportions.
- Effect sizes and intervals reported; the study is **descriptive** and not powered
  for inference at this N — state that rather than implying otherwise.
- Comparing arm C against both A and B is multiple comparisons; either correct or
  declare the p-values uncorrected.
- Analysis code released; all metrics computed by a single script from the raw
  logs.

**2.9 Reproducibility artifacts.** [WRITABLE NOW]
Frozen task set with ground-truth provenance, frozen file manifest and index
timestamp, per-task run logs for every arm, blinded ratings, and the analysis
script. **[NEEDS DECISION: archive a tagged release with a DOI — agent is checking
whether the journal requires this.]**

---

## 3. Results — [NEEDS DATA]

Structure and table shells only. **Do not draft prose here before data exists.**

- **3.1 Corpus and index characteristics.** Files indexed by type, chunks, index
  size, indexing wall-clock, peak memory.
- **3.2 Primary comparison.** Correct-file-identified rate per arm with 95% CIs;
  paired McNemar for C vs B and C vs A.
- **3.3 Retrieval diagnostics (arm C).** Top-1/top-5, mean unique files per query.
- **3.4 Grounding.** Path-hallucination rate; a short qualitative account of what
  hallucinated citations looked like.
- **3.5 Abstention on undocumented controls.** Correct and false abstention;
  heuristic-vs-human agreement.
- **3.6 Efficiency.** Time to answer by arm; agent latency distribution.
- **3.7 Per-category breakdown.** Expect the interesting result here — strong on
  *locate*, weaker on *reproduce* is a more credible and more informative finding
  than a single headline number.

**Table shells**
- Table 1 — Corpus and index characteristics.
- Table 2 — Metrics by arm, with 95% CIs.
- Table 3 — Per-category performance, arm C.
- Table 4 — Pre-registered thresholds vs. observed.

**Figure shells**
- Fig 1 — System architecture (model, index, interfaces, safety boundary).
- Fig 2 — Evaluation design: three arms over one frozen task set.
- Fig 3 — Metrics by arm with intervals.
- Fig 4 — Per-category breakdown.
- Fig 5 (supplementary) — The verbatim prompt.
- Fig 6 (optional) — An annotated real interaction with its cited sources.

---

## 4. Discussion — [NEEDS DATA for the specifics; framing WRITABLE NOW]

- **4.1 What the results do and do not support.** Tie back to the pre-registered
  thresholds. If a threshold was missed, say so first.
- **4.2 Undocumented knowledge is a hard ceiling.** [WRITABLE NOW] An agent
  indexing written artifacts cannot recover rationale that was never written down.
  The control category makes this measurable rather than hypothetical. This is a
  genuine contribution to how such systems should be evaluated, and it is worth
  stating even if the rest of the results are modest.
- **4.3 Local hosting as a design constraint, not a compromise.** [WRITABLE NOW]
  Discuss the resource envelope and what it implies for other institutions.
- **4.4 Guardrails as code rather than policy.** [WRITABLE NOW] With the sandbox
  limitation stated honestly.
- **4.5 Comparison to prior work.** [NEEDS DATA from literature agent.]

## 5. Limitations — [WRITABLE NOW]

Write these before the results, so they are not shaped by the outcome:
single lab and single case study (demonstration, not generalization); small N,
descriptive not powered; one-project index scope; per-chunk embedding throughput;
keyword-based abstention detection; conservative hallucination accounting;
arm A cannot be blinded; arm B's fairness depends on the prompt it was given;
an 18 GB local model will not match frontier reasoning — the hypothesis is that
grounding compensates on lab-specific tasks, and **if it does not, that is a
publishable negative result**; and file paths may move during the study, which the
frozen manifest mitigates but does not eliminate.

## 6. Conclusions — [NEEDS DATA]

Must follow from results. No forward-looking claims dressed as findings.

---

## Declarations — [NEEDS DECISION / agent checking exact requirements]

- **Ethics approval and consent to participate.** Requires care: the agent indexes
  files in a lab handling de-identified human tissue data, though the manuscript
  reports no patient data. If human participants are timed in arm A, that may
  itself need a determination. **Ask Dr. Levy — do not draft this ourselves.**
- **Consent for publication** — likely not applicable; confirm.
- **Availability of data and materials** — code repository; state explicitly that
  lab data cannot be shared and why.
- **Competing interests**, **Funding**, **Authors' contributions**,
  **Acknowledgements**.

---

## Honest assessment of publication readiness

**Ready now:** the entire Methods section, the safety design, the evaluation
protocol, the limitations, and the reproducibility artifacts. That is a real
methods contribution and it is defensible today.

**Blocking:** (1) no data has been collected; (2) the case study subject is
unconfirmed; (3) the novelty claim is unsupported.

**The honest framing if time runs short:** this is a *software and methods* paper
with a small pilot evaluation — not a large empirical study. That framing is
truthful, fits the journal, and is achievable. Overstating it as a comparative
study of agent performance is not.
