# MASTER PROMPT: Determine the strongest research contribution that extends the Levy Lab digital pathology agent

## YOUR ROLE

You are acting as a research strategist and literature analyst. Your job is NOT
to build anything, and NOT to rubber-stamp a plan that already exists. Your job
is to determine, from evidence, what the strongest genuinely publishable
research contribution is for this project, and what it would actually take to
get there.

The product is defined by the program. The research question, the claim, the
experiment, and the evaluation are open, and that is what I am asking you to
determine.

## TARGET VENUE

**USCAP Annual Meeting, abstract submission.** United States and Canadian
Academy of Pathology.

Pull the current USCAP abstract submission guidelines yourself and treat them as
a hard filter on everything you recommend. Do NOT look up or consider the
deadline. Do establish, from the actual guidelines:

- The required structure and the exact length limit.
- Which submission category or subspecialty this work would go under, and
  whether computational, informatics, or digital pathology abstracts are
  accepted there at all. Confirm the category exists rather than assuming.
- Whether reporting results is mandatory, and what counts as results.
- Rules on prior publication, prior presentation, and originality.
- Any requirement about data, human subjects, or IRB statements.

Three things about this venue shape everything downstream, and you must design
around them rather than discovering them at the end:

1. **This is an abstract, not a paper.** It is short and structured. A framework
   contribution that needs several pages to become convincing does not fit. The
   contribution has to survive compression to a few hundred words.

2. **An abstract needs results that already exist.** Not a plan, not an
   architecture, not a demo. Every direction you propose must be judged on
   whether it can produce concrete reportable findings, and you must say plainly
   what the minimum result set is and what it depends on. Rank directions partly
   on how fast they yield a reportable result, without reference to calendar
   time. A direction that only pays off after a long dependency chain is weaker
   here regardless of how strong the eventual claim is.

3. **The audience is practising pathologists and pathology researchers, not an
   ML or systems audience.** The contribution has to be legible and meaningful
   to them. "We built an agent with tool calling and retrieval" is a systems
   result and will land badly. "Researchers could not reproduce X, and this
   changes that, measured this way" is a pathology result. Calibrate every
   claim, every metric, and every framing to that reader. Where the pathology
   significance is thin, say so.

Note also that a USCAP abstract and a later full manuscript are compatible
rather than competing, subject to the venue's own prior-publication rules, which
you should check. If a direction sets up both, say so, but do not let the
hypothetical paper justify a weak abstract.

All the other source material you need is embedded in this prompt below.

---

## AUTHORITY HIERARCHY: WHAT IS FIXED AND WHAT IS OPEN

Read this carefully. It is the difference between a useful answer and a useless
one. The two source documents below do NOT carry equal weight.

**TIER 1, AUTHORITATIVE AND FIXED.** The EDIT program project description,
written by the faculty mentor (Source Material A). This defines what the project
is and must remain. Everything you propose must sit inside it and serve it. Do
not propose a project that abandons it, reframes it into a different field, or
reduces it to a component of something else.

**TIER 2, INDICATIVE AND OPEN TO IMPROVEMENT.** The student pitch deck
(Source Material B). This was written by undergraduates at the start of the
project. It is real evidence of intent and it shows how the team currently
understands the work. It is NOT a specification of good research design. Its
three aims, its four metrics, its approach, and its framing of the gap are all
open to challenge and replacement if the literature supports something better.
Where it is methodologically weak, say so and propose better. Finding a sharper
focus than the deck's is an expected and desirable outcome.

**TIER 3, EVIDENCE ONLY.** Any existing implementation, prototype, prior
decision, or remark from a team member. Useful for what it proves about
feasibility. It constrains nothing on its own.

---

## THIS MUST EXTEND THE PROJECT, NOT REPLACE IT

This is a continuation of real work, not a fresh start. Two things follow, and
they pull in opposite directions on purpose. Hold both.

**Continuity is required.** Every direction you propose must be a genuine
extension of the project described in Tier 1. It must be reachable from where
the project already is. For each direction, state explicitly what existing work
it builds on and what it reuses. A direction that requires starting over, or
that is really a different project wearing this one's name, is out of scope no
matter how strong it looks in the abstract.

**How it extends is wide open.** Within that boundary, do not assume the current
implementation choices, aims, metrics, task design, or evaluation framing are
correct. Those are Tier 2 and Tier 3. Challenge all of them.

The test to apply to every direction: *could this credibly be presented as the
next stage of the project the program described, by the people already doing
it?* If yes, it is in scope. If it is only reachable by discarding the program's
intent, it is out.

---

## ANTI-ANCHORING RULES

I have already built a working prototype. You may be given that context. Treat
it as Tier 3.

- Do not treat a decision, metric, aim, task category, or architecture as
  settled because it exists or because someone mentioned it once.
- Do not preserve an approach to justify sunk work. If part of the existing work
  does not serve the strongest contribution, say what should be dropped and why.
  Dropping components is fine. Dropping the project is not.
- Do not let a passing remark from any person, mentor included, become a
  requirement. Weight input by whether it is a genuine constraint (data access,
  privacy, hardware, ethics, program mandate) or a preference.
- Construct at least two framings that differ substantially from the deck's
  current framing, and evaluate them on equal terms. No strawmen.
- If the strongest contribution requires substantially reframing what the paper
  claims, say so directly, while keeping the project itself intact.

Before your final recommendation, explicitly list which prior assumptions you
tested and which you rejected.

---

## THE TWO FIELDS THIS MUST SIT ACROSS

Any recommendation has to be substantive in both, not decorative in one:

1. **Agentic LLM systems**: tool use, retrieval, planning, code generation,
   grounding, verification, evaluation methodology for agents, and local or
   open-weight model deployment.
2. **Computational pathology and spatial biology**: H&E, spatial
   transcriptomics, cell typing, niche discovery, outcome association, and the
   real reproducibility problems in those workflows.

A contribution that is really an agents paper with pathology as a backdrop, or a
pathology paper with an LLM bolted on, is a failure mode. Flag it if you catch
yourself producing one.

Given the venue, the pathology side has to carry the significance and the agent
side has to carry the method. That is a difference of emphasis, not licence to
be shallow on either. If the pathology significance only works for an ML
audience, the direction is wrong for USCAP even if the engineering is good.

---

## HARD CONSTRAINTS

**Ignore deadlines entirely.** Do not look up when anything is due. If you
encounter a date in any source, disregard it. It must not shape scope,
ambition, or recommendations. If you catch yourself narrowing scope for time
reasons, stop and remove that reasoning.

**One stated safety constraint, and its boundary is open.** The program
description says, marked IMPORTANT, that agents should operate in controlled
environments and should not overwrite or modify original research data. The
first half of that is Tier 1 and holds. But note what it does and does not say.
It protects *original research data*. It does not say the agent may never write
or execute anything, and the deck's stricter "read-only" framing is a Tier 2
narrowing, not the program's wording. Where exactly the line sits, whether the
agent may write and run its own scripts, produce derived outputs, or propose
changes for human approval, is a design question this research should settle on
evidence rather than inherit. Note that the program description itself asks for
agents that "plan, execute, and interpret" experiments, which sits in tension
with a pure read-only reading. Resolve that tension explicitly.

**Deployment and privacy model: OPEN, determine it, do not assume it.** I have
NOT established that patient data must stay on lab-controlled hardware. The
program says "ideally open-source models" and the deck argues for local models,
but neither states a hard privacy requirement, and the team has separately
discussed no-retention APIs and hosted options such as Azure OpenAI. Treat the
deployment model as a question to answer, not a constraint to obey. Determine
what is actually required by the data governance around this kind of data, what
comparable published systems did, and what each option costs the research claim.
If the honest answer is that a fully local deployment is required, say so and
show why. If it is not required, say that too, because it widens the design
space considerably.

---

# STAGE 1: DEEP PRIOR ART

Map what already exists. Be exhaustive enough that nothing surfaces later and
invalidates the direction. Missing something here is the expensive failure.

Cover at minimum, and expand wherever the trail leads:

- Lab-personalized or institution-personalized LLM systems grounded in private
  code, data, and documents.
- Agentic and retrieval-augmented systems over scientific codebases, including
  repository-level question answering and code agents.
- LLM agents for bioinformatics and computational biology workflow planning,
  generation, and execution.
- AI systems in digital pathology and spatial omics, including those named in
  the source material and anything comparable.
- Reproducibility, provenance, and workflow-capture tooling in computational
  science, including non-LLM approaches that solve the same user problem.
- Privacy-constrained and on-premise LLM deployment in clinical and biomedical
  settings.
- Evaluation methodology for research assistants and agents: what benchmarks
  exist, what metrics are accepted, what reviewers have criticized.
- Human-in-the-loop evaluations of AI research assistants, especially how time
  saved, usefulness, and reproducibility have been measured credibly.

For each relevant system record: what it does, what it is grounded in, how it
was evaluated, what it explicitly does not do, and whether it is open.

**Validation checkpoint 1.** State what you searched, what you found, and where
coverage is thin. Separate what you verified from a primary source from what you
inferred. Do not proceed on a shaky base.

---

# STAGE 2: GAP ANALYSIS

- **Kill solved gaps.** If prior work addresses something, say so, cite it, and
  remove it. Be aggressive. One gap that survives a real search beats ten that
  were never checked.
- Distinguish a gap that is *unsolved* from one that is *unimportant* or
  *unpublishable*. Say which each is.
- For each surviving gap, say why it has not been filled. Hard problem, no data,
  no incentive, or nobody looked. That changes whether it is a good target.
- Identify blockers that could kill the project mid-flight: data access, PHI and
  IRB constraints, compute, needing human participants, needing ground truth
  that may not exist, and reproducibility of the evaluation itself.
- State explicitly whether the pitch deck's own claimed gap holds up against the
  literature. If it does not, say what the real gap is.

**Validation checkpoint 2.** For each surviving gap, give your confidence and
the specific evidence. Kill anything you cannot defend.

---

# STAGE 3: DIRECTIONS

Generate concrete research directions that extend the project and sit across
both fields.

For each direction give:

- The **claim**, in one falsifiable sentence.
- Why it is **novel** given Stage 1, named against the specific prior work it is
  distinguished from.
- **How it extends the existing project**, and what it reuses.
- The **experiment**: arms, baselines, task design, ground truth, and what is
  controlled for. Include the cheap non-LLM baseline a reviewer would demand,
  and state honestly whether the claim survives it.
- **Metrics**, defined precisely enough that they cannot drift, and the result
  that would falsify the claim.
- **What must be true** for this to be possible, and how to check that early and
  cheaply.
- **Failure modes**, including the most likely reviewer objection.
- Rough **effort and dependency** shape, with no reference to calendar time.

Produce several genuinely different directions, not variations on one theme.

Then rank them on strength of contribution, feasibility under the stated
constraints, and fit to the target venue.

**Validation checkpoint 3.** Adversarially attack your own top directions as a
skeptical reviewer would. Show the attack and the response. Keep only what
survives.

---

# STAGE 4: WHAT IT WOULD ACTUALLY TAKE

For the top recommendation, and briefly for the runner-up:

- Full scope of work, as dependencies rather than a schedule.
- What must be obtained from other people, and the specific question to ask each.
- What can be validated cheaply and early, before committing.
- The single biggest risk, and what would retire it.
- What existing work is reusable, and what should be dropped.

---

# OUTPUT FORMAT

1. **Executive summary.** The recommendation and the one-sentence claim, first.
2. **Landscape.** What exists, by theme, with sources.
3. **Gaps.** Surviving gaps with evidence, plus gaps you killed and why.
4. **Directions.** Full treatment, ranked.
5. **Adversarial review.** Attacks and what survived.
6. **Scope for the recommendation.**
7. **Draft abstract skeleton** for the top recommendation, in USCAP's required
   structure and within its length limit. Fill in what is already known, and
   mark clearly with [MISSING] every place where a result does not yet exist.
   Do not invent placeholder numbers. This skeleton is the honest test of
   whether the direction is submittable, and the [MISSING] list is the real
   work plan.
8. **Assumptions tested and rejected**, including the pitch deck's.
9. **Open questions.** What you could not resolve, and who can.

## STANDARDS

- Cite sources. Distinguish verified from inferred.
- State confidence where it matters. Say plainly when you do not know.
- Never invent numbers, results, or citations. A fabricated citation is worse
  than an admitted gap.
- Plain language. No padding.
- If the evidence points somewhere I clearly do not want to go, tell me anyway.

---
---

# SOURCE MATERIAL A (TIER 1, AUTHORITATIVE): EDIT program project description

From the EDIT program Project List and Pitch/Design Docs sheet, shared by Zarif
Azher in #edit-group4-2026 on June 7. Reproduced verbatim.

**Project Title:** AI Agents for Digital Pathology Research

**Faculty Mentor / Project Contributor:** Zarif Azher

**Description:**

> Utilize LLMs — ideally open-source models — to develop AI agents that can plan,
> execute, and interpret digital pathology experiments, and eventually entire
> research projects. Digital pathology and spatial biology workflows often
> require researchers to navigate complex combinations of H&E images, spatial
> transcriptomics data, single-cell annotations, model outputs, clinical
> metadata, statistical analyses, and visualization pipelines. This project would
> build AI agents that help researchers move from high-level biological questions
> to concrete, reproducible computational experiments. For example, a pathology
> research agent could help a lab member ask: "Which spatial niches are
> associated with recurrence in this cohort?" and then identify the relevant
> datasets, notebooks, code, metadata fields, statistical tests, prior results,
> and visualization scripts needed to answer the question. Agents could assist
> with experiment planning, cohort selection, preprocessing decisions, model
> evaluation, figure generation, statistical interpretation, and drafting result
> summaries. Over time, such systems could support increasingly complex
> workflows, including H&E image analysis, Xenium/Visium integration, cell
> typing, niche discovery, outcome association studies, interface/distance-to-
> tumor analyses, and manuscript-ready figure generation. A key goal is for these
> agents to personalize to the specific context of an individual lab. Rather than
> acting as generic coding assistants, they could learn and adopt lab-specific
> workflows, file structures, best practices, preferred statistical methods,
> naming conventions, quality-control standards, and interpretation norms. In the
> Levy Lab, for instance, agents could become familiar with existing spatial
> transcriptomics pipelines, common AnnData structures, model evaluation scripts,
> clinical outcome analyses, and figure-generation conventions. This would make
> the system more useful, trustworthy, and aligned with how real computational
> pathology research is actually conducted. The goal is not to replace
> researchers, but to create reliable, transparent research assistants that
> accelerate repetitive and technically complex workflows while keeping humans in
> control of scientific judgment. A publication from this project could describe a
> lab-personalized agent framework for computational pathology research, and
> include case studies showing how agents reduce time-to-analysis, improve
> reproducibility, and enable researchers to build on prior lab work more
> effectively.

**Dataset Description:**

> The Levy Lab's digital pathology and spatial biology infrastructure and data.
> IMPORTANT: Agents should operate in controlled environments and should not
> overwrite or modify original research data.

**Literature/Outreach:** "just to get started, please use Scholar Labs etc.
Reach out to Zarif"

---

# SOURCE MATERIAL B (TIER 2, INDICATIVE, STUDENT-AUTHORED): pitch deck

"A Lab-Personalized AI Agent for Reproducible Digital Pathology Research."
Owner varun.kalidindi99@gmail.com, shared in
#digital-pathology-agent-project-interest on June 22. Written by the student
team at the start of the project. Treat as intent, not as research design.

**Title slide.** A Lab-Personalized AI Agent for Reproducible Digital Pathology
Research. Varun Kalidindi, Avilash Angirekula, Nehan Mohammed. Faculty Mentor:
Zarif Azher.

**Introduction.** Modern projects combine many combinations of data types. These
workflows often live across HPC folders, Jupyter notebooks, scripts, figures,
and prior lab knowledge. As projects grow, it becomes harder to find, reproduce,
and reuse previous analyses. AI agents could help researchers turn broad research
questions into concrete, reproducible workflows. Diagram labels: H&E Images,
Spatial Transcriptomics, AI Research Agent, Notebooks/Scripts, Clinical Metadata.

**Why Should Researchers Care?** Makes the process of onboarding new students and
researchers smoother. Makes reusing previous code, datasets, and analysis
pipelines easier. Less time spent searching through old notebooks and HPC
folders. More reproducible research with clearer links between data, code,
figures, and results. Makes it easier to reproduce and build on previous
projects. Helps researchers focus more on scientific reasoning rather than
constructing their workflow.

**What is Currently Available.** AI is already being used for pathology image
analysis, biomarker discovery, and workflow automation. Modella AI Judith: an AI
Agent system for biomedical image analysis. Mahmood Lab: includes pathology
foundation models and computational pathology tools.

**The Gap.** There are fewer open-source systems designed around a lab's own
datasets, notebooks, HPC files, and reproducible workflows. Safe HPC integration.

**Aim 1, Build the Agent Framework.** Use open-source LLMs to create a
lab-personalized research agent. Connect the agent to our Levy Lab context (code,
notebooks, metadata, project files). I plan on doing this using our Discovery
Workspace. LLM options: Qwen, well known for its compatibility with other tools.
Llama, widely used for its general reasoning abilities. Mistral, works well with
local HPCs.

**Aim 2, Make Research Workflows Reproducible.** Help researchers identify
relevant datasets and files relevant to their research topic or question. Make it
clear what is being used and how it is being used. Basically, making the LLM ours
by making it know our lab.

**Aim 3, Evaluate Our Agent Through a Case Study.** Test the agent on a completed
research workflow. Compare the original human process to the agent-assisted
process. Measure accuracy, usefulness, reproducibility, and time saved.

**Approach.** Index Levy Lab materials from Discovery, including datasets,
scripts, files, and documentation. Research suitable LLM models (like Qwen,
Llama, Mistral). Ensure the model uses lab materials and not just model memory
(avoid creating a "chatbot"). Allow the agent to search through the given
materials and ensure original files are read-only (for safety of lab). Generate
workflow summaries and understand the capabilities of the Agent.

**How We Measure Success Throughout the Summer.** Use a completed research
project as a case study. Compare the human workflow process to the agent-assisted
process. Measure whether the agent correctly finds datasets, code, metadata,
preprocessing steps, and outputs. Evaluate accuracy, usefulness, and time saved.
Use results to support a demo, poster, open-source repo, and possible manuscript.

**Safety and Limitations.** Ensure read-only access to original lab data and
project files. A local/open-source LLM to protect sensitive lab context.
Comparison against a human's workflow process. Make sure this isn't just a
chatbot that "summarizes" projects/materials.

Can Do: search, read, summarize, suggest, run safe test code.
Can't Do: edit/delete original files, submit uncontrolled jobs, make final
scientific decisions.
