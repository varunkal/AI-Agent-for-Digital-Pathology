# A Lab-Personalized AI Agent for Reproducible Digital Pathology Research

**EDIT AI/ML Program 2026 — Advanced Track — Team 4 Design Document**

Varun Kalidindi, Avilash Angirekula, Nehan Mohamed
Faculty Mentor: Zarif Azher · PI: Joshua Levy

> Status: DRAFT for mentor review. Sections marked **[CONFIRM]** need a decision
> from Zarif or Dr. Levy before this is final. Follows the EDIT design-doc
> structure (Scientific Premise → Motivation → Aims → Approach → Limitations →
> References) used by prior cohorts.

---

## Scientific Premise

A locally-hosted, open-source LLM agent that is indexed over a specific lab's own
files, code, and documentation can assist researchers in locating, interpreting,
and reproducing prior computational pathology analyses more accurately and more
quickly than either an unaided researcher or a general-purpose commercial
assistant that lacks lab context.

Digital pathology and spatial biology workflows span H&E whole-slide images,
spatial transcriptomics, single-cell annotations, model outputs, clinical
metadata, statistical analyses, and visualization pipelines. In practice these
artifacts are distributed across HPC directories, Jupyter notebooks, scripts, and
undocumented decisions held only by whoever ran the analysis. The result is that
completed work is difficult to reproduce and expensive to build on. We
hypothesize that lab-specific grounding — not model scale — is the dominant
factor in an agent's usefulness for this task, and that a ~18GB open-weight model
running entirely on institutional hardware is sufficient to demonstrate it.

## Motivation

- **Reproducibility.** Reconstructing a finished analysis currently requires
  locating the dataset, the preprocessing notebook, the model configuration, and
  the figure-generation script — often across several directories and authors.
- **Onboarding cost.** New students spend substantial early effort discovering
  where things live rather than doing scientific reasoning.
- **Operational overhead.** Much of the work surrounding an analysis (finding
  files, converting formats, rerunning scripts, regenerating figures) is tactical
  rather than intellectual, and is the kind of task a trained lab assistant could
  absorb.
- **Privacy is a hard constraint, not a preference.** The lab works with
  identifiable human tissue data under IRB. Commercial API-based agents raise
  data-egress concerns that rule them out for this setting. A local deployment
  removes the question entirely.

## The Gap

Existing agentic systems for biomedical image analysis (e.g. Modella AI's
*Judith*) expose a shell, planner, and chatbot, but are platform-hosted and
generic. Coding agents (Cursor, Claude Code, Codex) are general-purpose and have
no knowledge of a particular lab's datasets, naming conventions, or analysis
norms. **[CONFIRM: cite Modella/Judith properly — need a URL or paper.]**

> ⚠️ **The original gap statement here has been RETRACTED.** It claimed we were
> not aware of an open-source, locally-hosted, lab-personalized agent evaluated
> against human effort. A literature search (2026-07-29) **refuted that as
> written**: every individual property is occupied by published work, and most
> pairwise combinations too. See `REVIEW_FINDINGS.md` §3 for the specific prior
> work. Do not reinstate it.

Open-weight LLMs can now run entirely inside an institution, and agentic
frameworks for biomedical research are proliferating. Existing systems, however,
are grounded in one of three corpora: the public literature (BRAD; GPT4DFCI-RAG),
public tool documentation and release-quality repositories accompanying published
papers (Paper2Agent; PathML-RAG), or curated benchmark task sets (CORE-Bench;
ScienceAgentBench; BixBench; BiomniBench). Their evaluations correspondingly
measure performance on public or benchmark artifacts.

To our knowledge, no published system has been grounded in the *working, largely
unpublished* artifacts of a single laboratory — its exploratory notebooks, ad hoc
scripts, internal notes, and undocumented directory conventions — and evaluated in
situ on the provenance and navigation questions that arise when that laboratory's
own members try to reuse or reproduce a completed project.

**Commercial prior art, stated explicitly.** Modella AI's *Judith* (spun out of the
Mahmood Lab; Modella AI has announced acquisition by AstraZeneca) is a research-use
agent for biomedical **image analysis**, currently in preview. It is closed-source,
its deployment model and weights are undisclosed, and it has no publication or
public evaluation. It operates on imaging data rather than a laboratory's code and
documentation corpus, so it is not prior art for the present claim — but it is real
and must be acknowledged rather than omitted.

**What we do not claim:** novelty in the architecture. Ollama plus a vector store
plus an open-weight coder model is commodity plumbing, and the on-premise clinical
deployment pattern is already published (Nowak et al. 2026). The contribution is
the corpus, the task class, and the evaluation setting.

## Aims and Goals

**Aim 1 — Build the agent framework.**
Use open-source LLMs to create a lab-personalized research agent connected to
Levy Lab context (code, notebooks, metadata, project files) on Dartmouth's
Discovery HPC.

**Aim 2 — Make research workflows discoverable and reproducible.**
Help researchers identify the datasets, scripts, and files relevant to a
question, and make explicit what is being used and how — ensuring answers are
grounded in retrieved lab materials rather than model memory.

**Aim 3 — Evaluate the agent against human effort via a retrospective case
study.** Take a completed lab project, reconstruct the human workflow, and
compare human, generic-LLM, and lab-personalized-agent performance on the same
tasks. Full protocol in [EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md).

## Approach

### Data

The proving ground is the Levy Lab's own research infrastructure on Discovery,
not an external benchmark dataset. Two categories:

1. **Agent corpus (what gets indexed):** lab notebooks, Python scripts, README
   and documentation files, configuration files, and metadata within a scoped
   project directory.
2. **Case-study subject:** one completed lab project used as the evaluation
   target. **Proposed: ColoCare Recurrence G4X** — single-cell spatial
   transcriptomics from colorectal cancer patients with linked recurrence
   outcomes, including cell-level expression, spatial coordinates, cell-type
   annotations, and clinical metadata. It matches the motivating question in the
   project description ("which spatial niches are associated with recurrence in
   this cohort?") almost verbatim. **[CONFIRM with Dr. Levy — is this the right
   case study, and is a *completed* analysis available to compare against?]**

**Data handling.** Per program guidance, all analysis code, intermediate files,
and results live in the team's designated project folder on Discovery. No patient
data leaves institutional infrastructure at any point.

### Data Utilization

Files in the scoped directory are read, chunked, embedded, and stored in a
persistent vector index. At query time the agent embeds the question, retrieves
the top-K most similar chunks, and conditions generation on that retrieved
context. Original files are opened **read-only**; the index is a derived
artifact stored separately.

### Model

| Component | Choice | Rationale |
|---|---|---|
| LLM | **Qwen3-Coder** (~18GB) via Ollama | Native tool-calling support. Qwen2.5-Coder was tried first and rejected: it emitted JSON instead of executing actions. |
| Agent framework | **qwen-code v0.19.4** | Open-source, runs locally, permission-gated actions. Chosen over openclaud, Codex, Tabby, LocalAgentLaboratory. |
| Embeddings | **nomic-embed-text** via Ollama | Local; no external calls. |
| Vector store | **ChromaDB** (collection `levy_lab`) | Persistent, local, no server dependency. |
| Runtime | Ollama on Discovery HPC, V100 GPU node | All compute institutional. |
| Environment | Python 3.11 / conda env `labagent` | |

Ollama exposes an OpenAI-compatible endpoint at `http://localhost:11434/v1`,
which keeps the interface standard while all inference stays on-node.

### Preprocessing

Indexable file types are read to text (including `.ipynb` notebooks, where cell
source is extracted), split into overlapping chunks, and embedded. Chunk size and
overlap are configured in `rag/lab_rag.py`. Non-text and binary artifacts (WSIs,
`.h5ad`, images) are indexed by path and metadata only, not content.

### Interfaces

Two access surfaces over the same retrieval core:

1. **CLI** — `python lab_rag.py {index|query|chat}` for developers on Discovery.
2. **Slack bot ("LevyBoy")** — the researcher-facing surface, so lab members can
   ask questions where they already work (`@LevyBoy, where can I find this
   file?`). Uses Slack Socket Mode (an outbound WebSocket), which is what makes
   it deployable from behind the HPC firewall with no public endpoint. The bot is
   deliberately **read-only**: it performs retrieval and generation only, and
   never writes files or executes agent-authored code.

### Evaluation

Pre-registered success criteria, following EDIT design-doc convention of
committing to a bar up front. The agent is considered successful if, on the
held-out task set defined in the evaluation protocol:

- **Retrieval:** ≥80% top-5 retrieval accuracy — the correct file appears in the
  top 5 retrieved chunks for "where is X" tasks.
- **Answer correctness:** ≥70% of answers rated correct-and-useful by a blinded
  lab-member rater.
- **Grounding:** ≥90% of file paths cited by the agent actually exist
  (i.e. ≤10% path-hallucination rate).
- **Efficiency:** statistically significant reduction in time-to-answer versus
  the unaided-human baseline.
- **Comparative:** outperforms the generic-LLM baseline (no lab context) on
  retrieval accuracy — this is the test of the central hypothesis that lab
  personalization, not model scale, is what matters.

**[CONFIRM: these thresholds are proposed, not agreed. Mentors should sign off
before we collect data, so the bar isn't set after seeing results.]**

## Safety and Guardrails

Dr. Levy's explicit guidance (7/10): *"Please be careful about using agents
modifying existing file structure... Please make sure safeguards are in place."*
The project description likewise states agents "should not overwrite or modify
original research data."

| The agent **can** | The agent **cannot** |
|---|---|
| Search, read, and summarize lab files | Edit or delete original lab files |
| Suggest workflows and next steps | Submit uncontrolled HPC jobs |
| Run sandboxed test code (CLI surface only) | Make final scientific decisions |
| Cite file paths and provenance | Send any data off institutional infrastructure |

**Open issue to resolve.** The current qwen-code build *can* write and execute
files — that capability is how `hello_lab.py` was produced on Day 3. This exceeds
the read-only constraint stated in the project description. We need an explicit,
documented decision: either (a) restrict the researcher-facing surface to
read-only while keeping write/execute for developer use in a scratch directory,
or (b) sandbox writes to a designated scratch path only. **[CONFIRM — this
should be settled before the agent touches any real project directory. The Slack
bot is already read-only by design; the CLI is not.]**

Additional measures: the index is built over a scoped directory rather than the
whole filesystem; original files are opened read-only; and the lab is running a
large data-archiving effort, so indexed paths may go stale and must be
re-validated rather than assumed.

## Limitations

- **Single-lab, single-case-study scope.** Results may not generalize to other
  labs or domains. We claim demonstration, not generalization.
- **Small task set.** A realistic n (tens of tasks, not hundreds) limits
  statistical power; effects will be reported with uncertainty, not as precise
  point estimates.
- **Rater subjectivity.** "Useful" is partly a judgment call; mitigated by a
  written rubric and blinded rating.
- **Retrieval ceiling.** The agent cannot answer from undocumented knowledge that
  exists only in a researcher's head and was never written down — an important
  negative result in itself.
- **Model scale.** An 18GB local model will underperform frontier models on raw
  reasoning; the hypothesis is that grounding compensates for this on lab-specific
  tasks. If it does not, that is a publishable negative finding.
- **Data churn.** Ongoing archiving means files may move mid-study; index
  timestamps must be recorded.

## Deliverables

Per Advanced Track requirements: **research paper (.doc/.docx), slide
presentation, and poster**, plus an open-source repository
(`varunkal/AI-Agent-for-Digital-Pathology`) and a working demo. A prior cohort's
symposium also included a recorded video component.

Candidate venue: *BioData Mining* (Springer/BMC) collection **"Uses of Agentic AI
in Biodata Mining,"** shared by Dr. Levy on 7/28.
**[CONFIRM: submission deadline — the collection page is behind Springer auth and
we could not read it. Someone needs to open the link and record the date.]**

## References

**[TO COMPLETE — this section is a stub and must be filled before submission.
Needed: Modella AI / Judith; qwen-code; Qwen3-Coder; ChromaDB; RAG (Lewis et al.
2020); prior EDIT RAG-for-pathology-reports work; Azher et al. on OTLS/3D spatial
transcriptomics (proceedings.mlr.press/v259/azher25a.html); ColoCare cohort
references (PMID 30523039; Nat Commun s41467-020-17083-x); and the local-LLM
pathology-extraction benchmarking work (Nat Commun s41467-024-53190-9), which
supplies a comparable metrics vocabulary: extraction accuracy, hallucination
rate, inference speed, computational cost, cross-institution robustness.]**
