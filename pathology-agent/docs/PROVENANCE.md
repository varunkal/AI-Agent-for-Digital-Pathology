# Provenance of every factual claim

Written because this work is intended for publication. Each claim in
`DESIGN_DOC.md`, `EVALUATION_PROTOCOL.md` and `INTEGRATION.md` is listed with its
source and how strongly it is verified, so nothing enters a manuscript on the
strength of an assumption.

**Verification levels**
- **DIRECT** — read the primary artifact (source file, Slack message, git object).
- **SECOND-HAND** — quoted from a document read via an automated Drive sweep, not
  re-opened by hand. Accurate as far as it goes; re-check before quoting in print.
- **UNVERIFIED** — asserted with no evidence gathered. **Must be resolved or
  removed before submission.**

Snapshot date: 2026-07-29. Upstream repo state: `varunkal/AI-Agent-for-Digital-Pathology` @ `ac31d22`.

---

## Technical claims about the system

| Claim | Source | Level |
|---|---|---|
| LLM is Qwen3-Coder (~18GB), served by Ollama | repo `README.md`; `startup.sh` sets `OPENAI_MODEL="qwen3-coder"` | DIRECT |
| Agent framework is qwen-code v0.19.4 | repo `README.md` | DIRECT |
| Runs on Discovery HPC, V100 GPU node | repo `README.md`; `startup.sh` header comment | DIRECT |
| Ollama exposes an OpenAI-compatible API at `http://localhost:11434/v1` | `startup.sh` lines 9–11 | DIRECT |
| Vector store is ChromaDB, collection `levy_lab` | `rag/lab_rag.py` L22–23 | DIRECT |
| Embedding model `nomic-embed-text`; chat model `qwen3-coder` | `rag/lab_rag.py` L24–25 | DIRECT |
| `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `TOP_K=5` | `rag/lab_rag.py` L26–28 | DIRECT |
| Chunk metadata keys are `source`, `start_char`, `filename` | `rag/lab_rag.py` L116–122 | DIRECT |
| `query()` returns only the answer string, discarding retrieved metadata | `rag/lab_rag.py` L217–262 | DIRECT |
| `query()`'s prompt instructs "Always cite which file(s) your answer comes from" | `rag/lab_rag.py`, prompt in `query()` | DIRECT |
| Re-indexing deletes the existing collection | `rag/lab_rag.py`, `delete_collection` in `index_directory` | DIRECT |
| Embeddings are computed one Ollama call per chunk | `rag/lab_rag.py`, embed loop inside the `BATCH_SIZE` batching | DIRECT |
| Repo contains a broken self-referencing gitlink, no `.gitmodules` | `git ls-files -s` on a fresh clone: `160000 5db94ade… AI-Agent-for-Digital-Pathology` | DIRECT |
| Notebooks are indexed by extracting cell source (+ up to 500 chars of text output) | `rag/lab_rag.py` `read_notebook()` | DIRECT |
| CSV/TSV files are truncated to the first 50 lines when indexed | `rag/lab_rag.py` `read_file()` | DIRECT |
| Agent can write and execute files (exceeds the stated read-only constraint) | Planning doc Day 3 log: agent wrote, chmod'd and ran `hello_lab.py`; `hello_lab.py` present in repo | SECOND-HAND (log) + DIRECT (file) |
| Qwen2.5-Coder was tried and rejected for emitting JSON instead of calling tools | Planning doc Day 3 log | SECOND-HAND |

**Correction on the record:** I initially suspected `chunk_text()` could loop
forever when `rfind` finds no newline. Traced against the source — it cannot.
`rfind("\n", CHUNK_SIZE // 2)` searches from index 400, so a hit advances `start`
by ≥300 and a miss by 700. **Not a bug; do not report it as one.**

## Instructions and constraints

| Claim | Source | Level |
|---|---|---|
| "Please be careful about using agents modifying existing file structure… Please make sure safeguards are in place" — Dr. Levy, 7/10 | Slack `#digital-pathology-agent-project-interest`, 2026-07-10 12:30 | DIRECT |
| "we are working on a large data archiving project so a lot of data may disappear from the cluster" — Dr. Levy | Slack, same channel, 2026-06-25 17:46 | DIRECT |
| Project folders required on the cluster for IRB compliance | Slack `#edit-group4-2026`, Dr. Levy, 2026-07-03 | DIRECT |
| Progress slides requested for the weekly sync | Slack `#edit-group4-2026`, Zarif, 2026-07-23 20:52 | DIRECT |
| Weekly sync is Thursdays 5:30 PM PT | `#edit-group4-2026` canvas "Important Links and Materials" | DIRECT |
| "let's aim to present the Slack bot by next week" (Zarif, relayed) | Slack DM Varun → Avilash, 2026-07-24 | DIRECT (as a relayed statement — Varun's paraphrase, not Zarif's words) |
| "work on case studies, continue pushing along on the agentic work" (Zarif, relayed) | Slack DM Varun → Avilash, 2026-07-24 | DIRECT (relayed) |
| RAG "finished and tested, it works"; needs connecting to the LLM | Slack DM Varun → Avilash, 2026-07-24 | DIRECT (as Varun's self-report — **not independently verified**) |
| Design docs were due week 3 and shared in-channel | Drive "Weekly Meetings" doc, entries 6/18 and 7/2 | SECOND-HAND |
| Advanced Track deliverable = research paper + presentation + poster | Drive folder names of the 2024 end-of-summer upload form | SECOND-HAND (inferred from form structure, not a stated rule) |
| "Agents should operate in controlled environments and should not overwrite or modify original research data" | Project List 2026, row 24, Dataset Description | SECOND-HAND |

## Case study and venue

| Claim | Source | Level |
|---|---|---|
| ColoCare Recurrence G4X is a candidate case study matching the motivating question | Project List 2026 row 18 | SECOND-HAND |
| A *completed* ColoCare analysis with recoverable ground truth exists | — | **UNVERIFIED — blocking.** A retrospective study is impossible without it. Ask Dr. Levy. |
| Target venue: *BioData Mining* (Springer/BMC), collection "Uses of Agentic AI in Biodata Mining" | Slack link unfurl of the URL Dr. Levy posted 2026-07-28, showing that title and description; journal confirmed as BioData Mining (ISSN 1756-0381) via web search | DIRECT (title/journal) |
| Submission deadline for that collection | — | **UNVERIFIED.** Page is behind Springer authentication. Someone must open it. |
| Submission deadline **27 April 2027**, collection open for submissions | Collection page + journal collections index, retrieved 2026-07-29 | DIRECT |
| Guest editors: Zeeshan Ahmed (Rutgers), Saman Zeeshan (Univ. Missouri); EiC Nicholas Tatonetti | Collection page + editorial board page | DIRECT |
| **Modella AI and its product "Judith" are real**; Judith is a research-use agent for biomedical *image analysis*, in preview, waitlist-gated, spun out of the Mahmood Lab; Modella AI announces acquisition by AstraZeneca | Vendor pages modella.ai/judith and modella.ai/az-acquisition, retrieved 2026-07-29 | DIRECT |
| Judith has **no peer-reviewed publication or public evaluation**; deployment model and weights undisclosed | Searched arXiv, bioRxiv, web — nothing found | DIRECT (negative finding) |
| Judith is *not* prior art for our specific claim (closed-source, not verifiably local, operates on imaging data rather than a lab's code/doc corpus) | Reasoned from the above | Reasoned — **must still be cited and distinguished explicitly** |
| Novelty claim as originally drafted | Literature search completed 2026-07-29 | **REFUTED AS WRITTEN.** Every individual property is occupied by published work. Must be softened — see `REVIEW_FINDINGS.md`. |

### Correction to an earlier entry in this file

An earlier version of this document attributed a metrics vocabulary ("extraction
accuracy, hallucination rates, inference speed, computational cost, robustness
across institutions") to Nature Communications `s41467-024-53190-9`. **That was
wrong, and the error was mine.** Those metrics come from the *Levy Lab's own
project-list description* of a different proposed project (row 16, "Benchmark
Generative AI Pathology Report Extraction") — not from the cited paper.

The DOI itself is real but is a different work: Kefeli, Berkowitz, Acitores
Cortina, Tsang & Tatonetti, "Generalizable and automated classification of TNM
stage from pathology reports with external validation," *Nat Commun* 2024;15:8916.
It is a fine-tuned Clinical-BigBird **encoder**, not a generative LLM, and uses no
RAG. It remains worth citing — but for the argument that smaller institution-local
models suit sensitive healthcare data, **not** as a local-LLM-agent precedent.

For the local/privacy-preserving generative-LLM precedent, the correct citation is
Wiest et al., "Privacy-preserving large language models for structured medical
information retrieval," *npj Digital Medicine* 2024,
doi:10.1038/s41746-024-01233-2.

**Lesson recorded deliberately:** a DOI copied out of an internal planning
document is not a verified citation. Every reference must be opened and read
before it enters the manuscript.

## Statistical and methodological choices

| Choice | Justification | Level |
|---|---|---|
| Wilson score interval for proportions | Standard; well-behaved at small n and near 0/1, deterministic. Verified in tests to bracket the point estimate and stay in [0,1] at extremes. | DIRECT |
| Exact McNemar for paired binary outcomes | Standard for paired designs; exact rather than chi-square because discordant counts will be small. Hand-verified against closed form: (b=0,c=5)→0.0625, (b=1,c=4)→0.375, (b=3,c=3)→capped at 1.0. | DIRECT |
| `file_identified` as the cross-arm primary metric | Top-k needs a retrieval step, which the human and generic arms lack; comparing them on top-k would not be like-for-like. | Reasoned, documented in protocol §4 |
| Top-k computed over rank-ordered chunks, not deduplicated files | With `TOP_K=5`, chunks collapse to fewer files, so a deduplicated "top-5" silently means "retrieved at all." Demonstrated empirically and locked with a regression test. | DIRECT |
| Success thresholds (80% / 70% / 10% / 60%) | **Proposed anchors only — not derived from literature.** No comparable benchmark exists to calibrate against. Flagged in the protocol. | UNVERIFIED as norms; deliberate pre-commitment |
| Abstention detected by keyword list | Transparent and reproducible, unlike an LLM judge. Documented as a heuristic; a hand-checked sample is required. Known failure mode: an answer that says "no information about X, but here is Y" will be scored as abstained. | DIRECT (limitation stated) |
| Path matching falls back to basename | Models often cite a basename. Makes hallucination **conservative** and retrieval **generous**; both directions documented. | DIRECT |

## Claims deliberately NOT made

- **No results.** Nothing has been run against real lab data. Every number produced
  so far comes from synthetic fixtures explicitly labelled as such.
- **No performance claim** for the agent. The template task set carries no ground
  truth and `analyze.py` exits with an error rather than scoring it.
- **No claim that the safety module is a sandbox.** It is a guardrail for code that
  routes access through it; it cannot contain a process that calls `open()`
  directly or shells out. Stated in `safety.py`'s docstring.

## Must be resolved before submission

1. **Literature search** to support or soften the novelty claim. *(blocking)*
2. **Confirm a completed case-study analysis exists** with recoverable ground
   truth. *(blocking — the study design depends on it)*
3. **Springer collection deadline.**
4. **Verify Modella AI / Judith** independently, or drop the comparison.
5. **Mentor sign-off on thresholds** before any data collection.
6. **Resolve read-only vs. write-capable policy** for the agent.
7. **Written approval before any external-API (arm B) query.**
8. Re-open the SECOND-HAND sources by hand before quoting them in the manuscript.
