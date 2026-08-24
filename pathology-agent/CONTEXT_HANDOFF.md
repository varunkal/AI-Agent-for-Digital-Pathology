# Context Handoff: Levy Lab AI Agent for Digital Pathology

Written 2026-08-04. Author: Claude (Opus 5), working with Avilash Angirekula on
a macOS laptop. This file is written for a fresh chat that has never seen the
original conversation and has no access to Avilash's files unless he re-uploads
them.

Formatting note honored throughout this document: Avilash has a standing
preference that generated documents contain no em dashes and no semicolons.
This file follows that rule. Keep following it.

---

## READ THIS FIRST

1. Avilash Angirekula is a student on Team 4 of the EDIT AI/ML Program 2026 at
   Dartmouth, working in the Levy Lab on a project called "AI Agent for Digital
   Pathology."
2. His assigned piece is a Slack bot named **LevyBoy** plus the agent behind it,
   which answers questions about the lab's own code, notebooks, and docs.
3. Two local git repos on his Mac: `~/pathology-agent` (the agent, evaluation,
   docs) and `~/levyboy-slackbot` (the Slack layer). Neither has a git remote.
   Nothing is backed up off that machine.
4. It genuinely works. A live demo answers "how was results/figure3_recurrence.png
   produced?" with a correct pipeline trace citing real files.
5. Three things are honestly incomplete: the ChromaDB search index is empty on
   his laptop, he has no Dartmouth Discovery HPC access yet, and the corpus is
   9 synthetic files he wrote, not real lab data.
6. Slack tokens were committed to git history and **still need rotating**.
7. He wants plain language, short answers, no jargon. He has corrected this
   repeatedly. Do not lecture, do not pad.
8. The target publication is BMC/BioData Mining, deadline 27 April 2027.
9. A companion technical file exists at `~/pathology-agent/HANDOFF.md` with
   file-level detail, verified against the repo on 2026-08-03.

---

## 1. Project identity

**What it is.** A research assistant that a lab member can talk to in Slack,
which answers questions about that lab's own files: where things are, what a
script does, how a figure was produced, what parameters were used. It runs
entirely locally on hardware the lab controls, using an open-weights Qwen model
served by Ollama, so no lab data leaves the machine.

**What it is called.** The Slack bot is **LevyBoy**. The umbrella project is
"AI Agent for Digital Pathology." Avilash's two repos are `pathology-agent` and
`levyboy-slackbot`. The team lead Varun's repo is
`varunkal/AI-Agent-for-Digital-Pathology` on GitHub, cloned locally at
`~/labagent`.

**Who it is for.** Members of the Levy Lab at Dartmouth, a digital pathology
group. The immediate users are graduate students and postdocs who need to find
things in a large, undocumented, inherited codebase. The broader claim is that
this generalizes to other computational biology labs.

**Why it exists.** Two stated aims from the project pitch deck:
- **Aim 1:** "Connect the agent to our Levy Lab context (code, notebooks,
  metadata, project files)."
- **Aim 2:** Personalize responses to the lab's own conventions.

The concrete problem: a new student inherits a repo of notebooks and scripts
with no documentation and loses days figuring out which script made which
figure. Nobody wrote it down. The information exists but only inside the files.

**Stage.** Working prototype with a real evaluation harness. Not deployed to
the lab. Not on real data. Not on the cluster.

---

## 2. Goals and success criteria

### Hard requirements

| Requirement | Status |
|---|---|
| Agent connects to lab files and answers from them, not from memory | **Done** |
| Read-only. Never writes, edits, or deletes lab files | **Done and enforced** |
| Runs locally so PHI never leaves lab-controlled hardware | **Done by design** |
| Measurable, not anecdotal. Real metrics with statistical tests | **Partially done** |
| Publishable in BMC/BioData Mining by 27 April 2027 | **Not yet** |

### The four metrics the project promised

1. **Accuracy / hallucination rate.** Instrumented and measured.
2. **Usefulness.** **Not instrumented.** No rating rubric exists.
3. **Reproducibility.** **Not instrumented.**
4. **Time saved.** **Not instrumented.**

Three of four are missing. Do not claim otherwise.

### Evaluation protocol targets versus reality

| Target | Reality |
|---|---|
| ~30 tasks with at least 12 undocumented controls | 8 tasks |
| 3 replicate runs | 1 replicate |
| A human comparison arm | None |

### Nice to have

- Integration with `qwen-code` (the official Qwen agent CLI). Not done. Avilash
  built a bespoke agent loop instead, which turned out better for
  instrumentation because every step is recorded.
- A polished poster or slide deck. Not started.

---

## 3. Current state as of 2026-08-04

The system runs. Started with `bash ~/pathology-agent/RUN_REAL.sh`, the Slack
bot connects over Socket Mode and answers questions in a Dartmouth Slack
workspace.

Verified live on 2026-08-03:
- "how was results/figure3_recurrence.png produced?" returns a correct
  multi-step pipeline trace naming `src/niche_discovery.py`,
  `results/niche_assignments.csv`, `notebooks/figures_recurrence.ipynb`, and the
  exact line `fig.savefig('results/figure3_recurrence.png', dpi=300)`. Roughly
  60 seconds.
- `trace: results/figure3_recurrence.png` returns the same dependency chain
  deterministically in under a second with no model involved.
- Follow-up questions inside one Slack thread now work, because thread memory
  was added on 2026-08-03.

Test status: **141 tests passing** in `pathology-agent`, **25 passing** in
`levyboy-slackbot`. Zero failures. Zero skips.

Three real limitations right now:
1. **The ChromaDB index is empty.** `chromadb.PersistentClient(path=
   '~/pathology-agent/rag/chroma_db').list_collections()` returns `[]`. The
   collection named `levy_lab` does not exist. Therefore the `search_lab_files`
   tool fails and returns "Search is unavailable." Questions answered by
   `trace_pipeline`, `read_file`, and `list_files` still work fine.
2. **No Discovery HPC access.** Avilash is logged into his Discovery account but
   hit an error running `srun`. He cannot run on the V100 nodes yet.
3. **No real lab data.** The corpus is 9 synthetic files he wrote.

Both git working trees are **dirty**. Real, tested work is uncommitted (details
in section 11).

---

## 4. Done / In progress / Not started

### DONE

**Source-preserving retrieval** (`~/pathology-agent/rag/lab_query.py`). Varun's
`lab_rag.query()` returns only an answer string and discards which files it came
from, which makes accuracy metrics impossible. `lab_query.answer_question()`
preserves the file paths. It also has `personalize=True` and `retrieval=True`
switches that enable the ablation arms.

**The agent loop** (`~/pathology-agent/rag/lab_agent.py`). Up to 8 steps. The
model picks a tool, the tool runs, the result goes back in, repeat until it
answers. Handles both native tool calls and tool calls a model emitted as plain
text.

**Deterministic pipeline tracing** (`~/pathology-agent/rag/workflow.py`). Parses
real file references out of the corpus and builds the dependency graph itself.
The model writes prose over a finished structure, so it cannot invent a step.
This is the single most convincing thing in the demo.

**Safety guard** (`~/pathology-agent/rag/safety.py`). `PathGuard` with symlink
escape prevention and `commonpath` containment. After an audit its CAPABILITIES
documentation was restructured into `can` / `cannot` (enforced) / `NOT
enforced`, where the last category explicitly states "THE SLACK INTERFACE IS
EGRESS."

**Sandboxed execution** (`~/pathology-agent/rag/safe_exec.py`). Built but never
turned on. `allow_execution=False` everywhere, so the model is not even offered
the tool. The file documents that RLIMIT_AS is Linux-only (no memory cap on
macOS) and that the sandbox has "NEVER BEEN EXERCISED BY A LIVE MODEL."

**Lab personalization** (`~/pathology-agent/rag/lab_profile.py`). Parses a
Markdown profile of lab conventions and injects it into prompts. Aim 2.
`_is_placeholder()` stops a TODO-only profile from reporting 100 percent
coverage or injecting the literal word "TODO" into a prompt.

**Reproducibility** (`~/pathology-agent/rag/provenance.py`).
`SAMPLING_OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 8192}`, model
digest captured from `ollama list`, git SHAs, and a `warnings()` function.

**Four-arm evaluation** (`~/pathology-agent/evaluation/run_arms.py`). Arms named
`personalized`, `plain`, `norag`, `bm25`.

**Statistical analysis** (`~/pathology-agent/evaluation/analyze.py`, 800+ lines).
Exact McNemar test, Wilson score intervals, and `classify_citation()` which
sorts citations into CITATION_EXACT, CITATION_BASENAME, CITATION_REFERENCED,
CITATION_FABRICATED.

**BM25 keyword baseline** (`~/pathology-agent/evaluation/lexical_baseline.py`).
Stdlib only, K1=1.5, B=0.75. This is the "does this beat grep?" control.

**The Slack bot** (`~/levyboy-slackbot/`). Socket Mode, threaded replies,
placeholder-then-edit so the user sees "thinking" immediately.

**Thread conversation memory** (added 2026-08-03, in
`~/levyboy-slackbot/handlers.py`). Bounded at 3 exchanges per thread and 200
threads with LRU eviction.

**Synthetic demo corpus** (`~/pathology-agent/demo/corpus/`). 9 files, 36 KB,
hand-written, no generator script. Full contents reproduced in section 14.

### IN PROGRESS, and exactly where he left off

**Clarifying-question behavior.** On 2026-08-03 Avilash pointed out that when he
asked "explain that without the jargon" with no prior context, the bot described
itself instead of asking what he meant. He said: "yes but it should be able to
do this." A fix was written, tested live, and confirmed working, but it is
**uncommitted**. The next physical action is to commit these files:
- `~/pathology-agent/rag/lab_agent.py`
- `~/pathology-agent/tests/test_all.py`
- `~/levyboy-slackbot/agent.py`

Note that a first attempt at this fix over-corrected and broke a good question
("what normalization was applied?" started asking for clarification instead of
searching). The prompt was rewritten to say searching is the default and
clarification is the single exception. That rewrite is what is now uncommitted.

**Rebuilding the ChromaDB index.** Diagnosed but not fixed. The next physical
action is to index the demo corpus into the `levy_lab` collection so
`search_lab_files` works again.

### NOT STARTED

- Rotating the leaked Slack tokens.
- Instrumenting usefulness, reproducibility, and time saved.
- Expanding the task set from 8 to about 30.
- Running 3 replicates instead of 1.
- Any human comparison arm.
- Discovery HPC access and any run on real lab data.
- Pushing either repo to GitHub. Neither has a remote.
- Any poster, slide deck, or paper draft beyond a skeleton.

---

## 5. People

**Avilash Angirekula.** The user. Student, EDIT AI/ML Program 2026, Team 4,
Dartmouth Levy Lab. Email angirekulah@gmail.com. Owns the Slack bot and the
agent work. Preferences and working style in section 8.

**Dr. Levy.** Principal investigator of the Levy Lab. Gave guidance on 10 July
about the system being read-only, referenced in code comments as "Dr. Levy's
7/10 guidance and the pitch's read-only commitment." That commitment is honored
in code: `~/levyboy-slackbot/agent.py` is deliberately read-only and
`allow_execution=False` everywhere. Full name was not confirmed during this
work. Pronouns unknown, so they/them is used here.

**Zarif.** Team lead. Directed Avilash to build the Slack bot specifically.
Pronouns unknown. Avilash at one point instructed "do this without the zarif or
other ppl than tell me what u did," meaning he wanted to proceed independently
rather than wait for coordination.

**Varun (GitHub handle `varunkal`).** Owns the RAG repo
`varunkal/AI-Agent-for-Digital-Pathology`, cloned locally at `~/labagent`. Built
`rag/lab_rag.py`, which indexes lab files into ChromaDB and exposes
`query(question, verbose=True) -> str`. Documented on Day 3 of his build log
that Qwen2.5-Coder was rejected because it "emitted JSON instead of executing."
Avilash's work independently reproduced that exact finding. Varun also
documented a GPU exclusive-mode conflict on Discovery, which is the same class
of model-contention problem Avilash hit locally. Pronouns unknown.

Important relationship rule that came out of a mistake: Avilash edited Varun's
repo directly at one point. Those edits were uncommitted and would have silently
reverted on Varun's next `git pull`. The edits were reverted and replaced with
environment-variable overrides (`LAB_CHAT_MODEL`, `LAB_CHROMA_DIR`,
`LAB_EMBED_MODEL`, `LAB_COLLECTION`) so Varun's repo stays pristine. **Never
edit `~/labagent`.**

**What Avilash still owes people.** Nothing was recorded as an explicit
commitment to a person during this work. The outstanding obligations are to the
project: rotate the tokens, get Discovery access, finish the metrics.

---

## 6. Decisions and rationale

These are settled. Do not re-litigate them or quietly reverse them.

**The agent is the DEFAULT in Slack, not an opt-in.** Originally a `deep:`
prefix was required to get agent behavior and plain retrieval was the default.
Avilash objected: "wait so ur telling me it wont use an agent for slack bot..."
This is an agent project, so the agent is the headline and single-shot retrieval
is the fallback. `fast:` opts out for speed.

**Retrieval is NOT forced. The model decides when to search.** On 2026-08-03
Avilash was explicitly offered three options: always retrieve first, keep the
model deciding, or always retrieve with the step hidden. He chose **keep it as
is**. Rationale: "the agent chooses its tools" is Aim 1, and the `used_no_tools`
flag catches it when the agent skips the files. Forcing retrieval would make the
system a pipeline rather than an agent and would weaken the paper claim. **Do
not change this to always-retrieve.**

**The pipeline tracer is a TOOL the agent can choose, not a router bypass.**
Originally provenance questions were intercepted before the agent and answered
directly by the deterministic tracer. Avilash showed a screenshot of a bare
trace and said "it simply says this." The problem: the most compelling questions
never reached the agent at all. Now `trace_pipeline` is one of the agent's four
tools, so the agent decides when to use it and can reason on top of the result,
while keeping the property that matters (the chain is computed from real file
references and cannot be fabricated). The `trace:` prefix still forces the fast
deterministic path.

**Configure Varun's repo with environment variables, never edit it.** See
section 5.

**Build a bespoke agent loop rather than integrating `qwen-code`.** Not a
deliberate architectural preference at first, but it turned out better: every
step is recorded in a trace with what was called, with what arguments, and what
came back, which is what makes the evaluation possible. `qwen-code` integration
remains a nice-to-have.

**`OLLAMA_MAX_LOADED_MODELS=2`, arrived at the hard way.** Unset (default 3 or
more) caused the chat model, the embedding model, and a second chat model to all
stay resident at about 6.3 GB on a 16 GB Mac, which swapped hard (4.9 GB of
swap, 83 seconds for a trivial prompt). Setting it to 1 fixed the swapping but
broke the agent, because every agent step needs the embedding model to search
and then the chat model to reason, so a cap of one forced an unload and reload
per step. Under that churn Ollama dropped connections mid-request
(`httpx.RemoteProtocolError`) and the bot hung on "thinking" forever. 2 is
correct: both models resident at about 4.3 GB together, no swap thrash, no
reload per step.

**`LEVYBOY_AGENT_TIMEOUT=300`, not the 120-second code default.** A measured run
using `trace_pipeline` took 169 seconds on the laptop, so 120 would have
abandoned runs that were working fine.

**Model is `qwen3:4b` locally, not `qwen2.5-coder`.** qwen2.5-coder advertises
tool support but emits JSON describing a call as plain text instead of making
one, so the loop silently performs no actions and the model answers from memory.
`model_supports_tools()` in `lab_agent.py` checks `ollama show` capabilities up
front and refuses to run rather than producing a confident wrong answer. This
independently reproduced Varun's Day 3 finding.

**Warnings must stay rare to stay meaningful.** The "no tools were called,
answered from model memory" warning now fires only when a fresh question was
answered with no tools. It does not fire on a legitimate follow-up (where facts
were established by tools on an earlier turn) and it does not fire when the
model asked a clarifying question (which is the correct behavior, the opposite
of the failure). Rationale: a warning that fires on correct behavior gets
ignored, and then the one that matters gets missed too.

**Thread memory is in-process, not fetched from the Slack API.** Slack's
`conversations.replies` would survive restarts but requires additional OAuth
scopes, which was not worth doing hours before a demo. Tradeoff accepted:
history is lost on bot restart.

**No substitute or public corpus.** Avilash said "im not gonna do some other
data type thing." He rejected pivoting to a public dataset. Stay with the Levy
Lab project.

**Report the unflattering numbers.** The BM25 tie is bad news for the project
and gets said out loud anyway. Volunteering it is what makes the rest of the
results credible.

---

## 7. Constraints

**Hardware.** Apple M3 MacBook Air (`Mac15,12`), 16 GB unified memory, macOS
Darwin 25.5.0. This constrains model size. A 4B parameter model at Q4_K_M
quantization runs at 25 to 40 tokens per second when the machine is healthy.

**No Discovery HPC access yet.** Avilash is logged into his Discovery account
but hit an error running `srun`. Until that is resolved, no V100 GPUs, no larger
model, no real lab data.

**Read-only is a hard requirement,** from Dr. Levy's 10 July guidance and the
pitch's own commitment. The Slack surface never writes, edits, or deletes lab
files, and never executes agent-authored code.

**PHI cannot leave lab-controlled hardware.** This is why everything runs
locally on Ollama rather than calling a hosted API. It is also the single
strongest argument for the whole design.

**Publication deadline 27 April 2027**, BMC/BioData Mining.

**Python 3.13.5 at `/opt/anaconda3/bin/python3`.** Bare `python3` on this
machine lacks the dependencies, which is why `RUN_REAL.sh` pins the interpreter
and fails loudly with an explanatory message rather than dying at import.

**Writing style constraint.** Generated documents and PDFs: no em dashes, no
semicolons.

---

## 8. Avilash's preferences and working style

**Plain language, no jargon.** Requested repeatedly. When an explanation used
technical vocabulary he pushed back directly. Write for someone smart who does
not know the internals.

**Concise.** He asks short questions and wants short answers. When he asked
"so whats the main problem?" the right answer was four lines, not four sections.

**He wants to actually understand, not be reassured.** Representative message:
"im not gonna lie, i dont feel confident about this at all like does this even
do what the project is supposed to." Reassurance is the wrong response to that.
Evidence is the right response.

**He tests things himself and pushes back when they look wrong.** Several real
bugs were found only because he did not accept an explanation. Examples: "but
the actual agent thing takes ten minutes to do anything?" led to finding the
swap thrashing bug. "those are like specific ones that all give same response i
wanna be able to do dif ones to actually test it, notj ust do these that are
memorized it feels like" was a legitimate complaint about being handed
pre-baked demo questions, and the fix was printing the whole corpus so he could
invent his own.

**He does not want to be handed a script he cannot deviate from.** Give him the
material to improvise with.

**He wants to know exactly what to run and where.** He asked "do i run those in
terminal" and "exactly what do i run rn to test." Be explicit: which window,
which order, what to expect, how long.

**Corrections he issued that changed direction:**
- "dont edit or create docs, just give the details of project in this chat"
  (early, when reading a Google Drive folder)
- "Please do both of those entirely. Don't wait for varun. Don't wait for
  anyone."
- "im not gonna do some other data type thing"
- "yes but it should be able to do this" (about handling vague questions)

**What he responded well to.** Being told plainly when something was broken,
including when the breakage was self-inflicted. Measured numbers instead of
adjectives. Being given the line to say out loud in a demo.

---

## 9. Domain context and terminology

**Digital pathology.** Computational analysis of tissue images and molecular
data from tissue. The Levy Lab works on this at Dartmouth.

**Xenium.** A commercial spatial transcriptomics platform (10x Genomics) that
measures the expression of a targeted gene panel at single-cell resolution while
preserving where each cell sits in the tissue. The demo corpus uses a 103-gene
panel.

**H&E.** Hematoxylin and eosin, the standard tissue stain. "Matched H&E" means
each Xenium sample has a corresponding stained image.

**Spatial niche.** A recurring local neighborhood type in tissue, defined by
which cell types sit near each other. Found here by building a k-nearest-
neighbor graph over cell centroids (k=15), computing a composition vector for
each neighborhood, then k-means clustering into 8 niches.

**Leiden clustering.** A community-detection algorithm used to group cells by
expression similarity. Resolution controls granularity. The lab default is 0.7.

**Cox proportional hazards.** A survival analysis model. Used here to test
whether niche abundance associates with cancer recurrence, adjusted for stage
and age.

**Benjamini-Hochberg.** A multiple-testing correction controlling false
discovery rate. Applied across the 8 niches.

**ColoCare.** The name of the colorectal cancer recurrence cohort in the demo
corpus (Cohort A).

**RAG (retrieval-augmented generation).** Instead of relying on what a model
memorized, you search a document collection for relevant passages and put them
in the prompt. Here: files are split into 800-character chunks with 100
characters of overlap, embedded with `nomic-embed-text`, stored in ChromaDB
collection `levy_lab`, and the top 5 chunks are retrieved.

**Ollama.** Software that serves open-weights models locally. Exposes an
OpenAI-compatible API at `http://localhost:11434/v1`.

**Tool calling.** The mechanism by which a model requests an action rather than
producing text. Critically, some models advertise tool support but emit a JSON
description of a call as ordinary text instead of populating the API's tool-call
field. qwen2.5-coder does this. qwen3:4b does not.

**Slack Socket Mode.** An outbound WebSocket connection from the bot to Slack,
so the bot needs no public URL and works behind an HPC firewall.

**Discovery.** Dartmouth's HPC cluster. SLURM scheduler, V100 GPU nodes.

**McNemar test (exact).** A paired statistical test for binary outcomes on the
same items under two conditions. Used here to compare evaluation arms.

**Wilson score interval.** A confidence interval for a proportion that behaves
better than the normal approximation at small samples.

**hit@1.** Whether the single top-ranked retrieved file is the correct one.

**Abstention.** The system correctly saying it does not know, on a question
whose answer is genuinely not in the corpus. Two demo tasks test this.

---

## 10. Research, sources, and measured findings

### Findings from Avilash's own evaluation, real and measured

- **Without retrieval:** 0 percent hit@1. Of 8 questions, 6 named no file at
  all, and **2 of 2 answers that did name a file fabricated it.**
- **Assistant versus no-retrieval:** p = 0.031 (exact McNemar).
- **BM25 keyword search TIES the assistant:** 0 discordant pairs, p = 1.0. This
  is real and unflattering and must be reported.
- **Corrected hallucination rate: 0 of 6.** An earlier figure of 50 percent was
  wrong. Investigation showed the metric had pooled CITATION_EXACT,
  CITATION_BASENAME, CITATION_REFERENCED, and CITATION_FABRICATED into one
  bucket. Publishing the 50 percent figure would have been a serious paper
  error.
- **Independently reproduced Varun's Day 3 finding** that Qwen2.5-Coder emits
  JSON instead of calling tools.
- **Independently hit the same class of model-contention bug** that Varun
  documented on Discovery as a GPU exclusive-mode conflict.

### Performance measurements taken 2026-08-03

- qwen3:4b generating under heavy machine load: **5.1 tokens per second.**
- After killing a runaway Adobe Crash Processor and letting load settle:
  **22.9 tokens per second.** Prefill 151 tokens per second.
- Load average went from **23.87** to **4.58** on an 8-core M3. Swap usage was
  4.4 GB at the worst point.
- Slack reply time therefore went from about **170 seconds** to about
  **40 seconds** with no code change at all.
- qwen3:4b is a reasoning model. It emits an internal thinking block before every
  answer. To output the 5 characters "hello" it generated **164 tokens**, of
  which 706 characters were thinking.

### Prior art, found by a literature search

The novelty claim originally made for this project was **refuted** and retracted.
These systems already occupy that space:
- **Paper2Agent**
- **GPT4DFCI-RAG**
- **BRAD**
- **Nowak et al.**

Do not claim novelty in the form "nobody has built an agent over a lab's own
files." That is false.

### A citation error that was caught and corrected

Metrics vocabulary was at one point attributed to Nature Communications
`s41467-024-53190-9`. **That DOI is Kefeli et al. on TNM staging and does not
support the claim.** The metrics actually came from the project's own
spreadsheet. The correction is recorded in
`~/pathology-agent/PROVENANCE.md`. Flagging this because it is exactly the kind
of error that survives into a submitted paper.

### Unverified, needs checking

- The exact BMC/BioData Mining submission requirements (word limits, section
  structure, figure rules) were never pulled up and checked.
- Whether the 8-question result would hold at 30 questions is unknown.
- Whether the BM25 tie persists on real, messier lab files is unknown. It might
  not, and that would be the most interesting result in the paper.

---

## 11. Technical details

### Repo state, verified 2026-08-03

| | `~/pathology-agent` | `~/levyboy-slackbot` |
|---|---|---|
| branch | `main` | `main` |
| HEAD | `79b61cd` "Let the agent see prior turns of a conversation" | `1e90b0f` "Remember the conversation, per Slack thread" |
| remote | **none** | **none** |
| working tree | **dirty** | **dirty** |

Uncommitted files, all containing real tested work:
- `~/pathology-agent/rag/lab_agent.py`
- `~/pathology-agent/tests/test_all.py`
- `~/pathology-agent/rag/chroma_db/chroma.sqlite3` (binary churn)
- `~/levyboy-slackbot/agent.py`

Recent commits in `~/pathology-agent`, newest first:
```
79b61cd Let the agent see prior turns of a conversation
1bdce5d Raise the agent deadline to 300s
acda736 Fix the hang: model cap of 1 broke the agent; add error handling and a timeout
ead1327 Pin the interpreter in RUN_REAL.sh and fail loudly if deps are missing
daa682b Add trace_pipeline as an agent tool
f139981 Fix model thrashing: 83s -> 11s per call, agent 583s -> 68s
```

Recent commits in `~/levyboy-slackbot`, newest first:
```
1e90b0f Remember the conversation, per Slack thread
352f931 Bound the Slack agent path and surface failures
e1cfeec Give the tracer to the agent as a tool instead of bypassing the agent
bc0b7f7 Make the agent the default in Slack, not an opt-in
```

### Architecture and data flow

```
Slack (Socket Mode, outbound WebSocket, no public URL, works behind firewalls)
  |
  +-- app.py .............. thin slack_bolt adapter, no logic, untested by design
      |
      +-- handlers.py ..... posts placeholder, calls agent, edits placeholder
      |                     owns per-thread conversation memory
      |
      +-- agent.py ........ THE ROUTER (lives in levyboy-slackbot)
            |
            +-- "help"     static text, no model touched
            +-- "trace:"   workflow.trace(), deterministic, under 1 second
            +-- "fast:"    lab_query.answer_question(), one retrieval
            +-- DEFAULT    lab_agent.run_agent()   <-- the agent
                  |
                  +-- loop, max 8 steps:
                  |     model picks a tool -> tool runs -> result goes back in
                  |
                  +-- search_lab_files -> lab_query.retrieve() -> ChromaDB
                  +-- read_file        -> safety.PathGuard
                  +-- trace_pipeline   -> workflow.trace()
                  +-- list_files       -> safety.PathGuard.walk_readable()
                  +-- run_python       -> safe_exec  (NOT OFFERED to the model)
```

The two repos meet at exactly one place: `PYTHONPATH` includes
`~/pathology-agent/rag`, and the Slack bot does `import lab_agent`. Nothing is
copied or vendored. Moving to Discovery is one line: change `LAB_CHAT_MODEL`
from `qwen3:4b` to `qwen3-coder`.

Message construction per model turn:
`[system prompt, ...validated history turns, user question, ...tool exchanges]`

### Module inventory

`~/pathology-agent/rag/`
- `lab_agent.py` - the agent loop, tool schemas, tool implementations, fallback
  parsing of text-emitted tool calls
- `lab_query.py` - source-preserving retrieval, config with environment
  overrides, Slack formatting
- `workflow.py` - deterministic dependency tracing
- `lab_profile.py` - lab conventions parsing and injection (Aim 2)
- `safety.py` - `PathGuard`, containment, capability documentation
- `safe_exec.py` - sandboxed Python execution, built but never enabled
- `provenance.py` - determinism settings, model digest, git SHAs

`~/pathology-agent/evaluation/`
- `analyze.py` - McNemar, Wilson intervals, `classify_citation()`, synthetic
  data flagging
- `run_arms.py` - runs the four arms
- `run_eval.py`, `tasks.py`, `lexical_baseline.py`

`~/levyboy-slackbot/`
- `app.py` - slack_bolt adapter
- `handlers.py` - bot logic with no Slack dependency, plus thread memory
- `agent.py` - the router and the three backends (`rag`, `cli`, `stub`)
- `test_handlers.py` - 25 tests

### Key functions

`lab_agent.run_agent(question, *, corpus_root, model=None, chat_fn=None,
tools=None, allow_execution=False, max_steps=8, scratch_dir=None,
history=None) -> AgentResult`

`AgentResult` fields: `question`, `answer`, `steps`, `sources`, `latency_s`,
`hit_step_limit`, `used_no_tools`, `used_prior_context`,
`asked_for_clarification`, `retrieval_failed`, `retrieval_error`, `model_error`.

`lab_agent.model_supports_tools(model) -> Optional[bool]` - runs `ollama show`
and inspects the capabilities section. Returns None if undeterminable, which is
treated as a hard error because it usually means the model is not installed.

`lab_agent.is_clarifying_question(answer) -> bool` at line 433. Returns True for
a reply under 200 characters, at most 2 lines, ending in a question mark.

`handlers.thread_history(thread_ts)`, `handlers.remember(thread_ts, question,
reply)`, `handlers.forget_all()`, `handlers._spoken_part(reply)`.
`MAX_TURNS = 6` (3 exchanges). `MAX_THREADS = 200` with LRU eviction.

`lab_query.config()` - precedence is environment, then lab_rag, then built-in
fallback. Current values: `CHROMA_DIR=/Users/avilash/pathology-agent/rag/chroma_db`,
`COLLECTION_NAME=levy_lab`, `EMBED_MODEL=nomic-embed-text`,
`CHAT_MODEL=qwen3-coder` (overridden to `qwen3:4b` by `RUN_REAL.sh`), `TOP_K=5`.

### Commands that actually work, copied verbatim

Start the bot. Foreground, needs its own terminal window, does not hot-reload:
```bash
bash ~/pathology-agent/RUN_REAL.sh
```

Run the pathology-agent tests:
```bash
cd ~/pathology-agent && /opt/anaconda3/bin/python3 -m pytest -q
```

Run the Slack bot tests:
```bash
cd ~/levyboy-slackbot && PYTHONPATH=/Users/avilash/pathology-agent/rag /opt/anaconda3/bin/python3 -m pytest -q
```

Run the agent from the command line with no Slack involved:
```bash
cd ~/pathology-agent/rag && PYTHONPATH=. /opt/anaconda3/bin/python3 lab_agent.py ../demo/corpus "how was results/figure3_recurrence.png produced?"
```

Check whether the model is being starved by machine load. This is the usual
cause of "it is slow":
```bash
/opt/anaconda3/bin/python3 -c "import ollama; r=ollama.chat(model='qwen3:4b',messages=[{'role':'user','content':'What is 2+2?'}]); print(round(r['eval_count']/(r['eval_duration']/1e9),1),'tok/s')"
```
Healthy is 25 to 40 tokens per second on this M3. Under 10 means something is
eating the machine. Check with:
```bash
uptime; ps -Ao %cpu,comm -r | head
```

There is no build step, no lint configuration, and no deploy process.

### Environment

Python 3.13.5 at `/opt/anaconda3/bin/python3`. Ollama 0.32.5, homebrew, arm64
native, at `/opt/homebrew/bin/ollama`. chromadb 1.5.9, numpy 2.1.3, scipy
1.15.3, plus `ollama`, `slack_bolt`, `python-dotenv`. No dependencies were added
during this work.

Model: `qwen3:4b`, quantization Q4_K_M, 4.0B parameters, 37 of 37 layers
offloaded to GPU via Metal, context set to 8192. Capabilities confirmed by
`ollama show`: completion, tools, thinking.

Environment variable names (never write values into any file):

| Name | Purpose |
|---|---|
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` | sourced from `~/.levyboy_tokens`, chmod 600, gitignored |
| `LEVYBOY_BACKEND` | `rag`, `cli`, or `stub`. Must be `rag` for the real stack |
| `LEVYBOY_CORPUS` | corpus root. Setting it enables agent mode and tracing |
| `LEVYBOY_AGENT_TIMEOUT` | seconds. 300 in the launcher, 120 is the code default |
| `LEVYBOY_LAB_RAG_PATH` | only used by the `cli` backend |
| `LAB_CHAT_MODEL` | the one line that moves this to Discovery |
| `LAB_PROFILE_PATH` | lab conventions injected into prompts |
| `LAB_EMBED_MODEL`, `LAB_CHROMA_DIR`, `LAB_COLLECTION` | supported overrides, not currently set |
| `OLLAMA_MAX_LOADED_MODELS` | must be 2. See section 6 |
| `OLLAMA_KEEP_ALIVE` | 30m |
| `PYTHONPATH` | `~/pathology-agent/rag:~/labagent/rag` |

### Known bugs, hacks, and things left in place

1. **The ChromaDB index does not exist.** `list_collections()` returns `[]`.
   `search_lab_files` fails. Highest priority technical fix.
2. **`rag/chroma_db/chroma.sqlite3` is tracked in git.** A binary that rewrites
   on every run, permanently dirtying the tree and bloating history. Should be
   gitignored and rebuilt from source.
3. **Slack tokens are in git history at commit `8c51d3e`.** They were moved out
   of the tracked launcher into `~/.levyboy_tokens`, but history still has them.
   **Rotate at api.slack.com.** Not done.
4. **Hardcoded absolute paths** at `demo/slack_live.py:69` and
   `demo/demo.py:200`, both `/Users/avilash/...`. Breaks for anyone else.
5. **Scratch directory under `/tmp`** at `rag/lab_agent.py:391` and `:723`, which
   macOS periodically clears.
6. **`lab_query.verify_paths` (line 313) accepts basename matches** as
   "exists." Intentional and documented, but more generous than a strict path
   check. `evaluation/analyze.py` has the stricter `classify_citation()`. Do not
   mix the two when writing results.
7. **`workflow._direction` (line 123)** classifies read-versus-write by
   substring and can misclassify. Known, unfixed.
8. **`evaluation/run_arms.py` has no test coverage.**
9. **`safe_exec.run_python` has never been exercised by a live model.** The
   sandbox is unproven in practice.
10. **`--corpus` is ignored by 3 of the 4 evaluation arms.**
11. **Documentation contains stale test counts** in places.

### Things that were tried and failed

- **Setting `OLLAMA_MAX_LOADED_MODELS=1`.** Fixed swap thrashing, broke the
  agent by forcing a model reload every step, causing dropped connections.
- **A `tool_call_id` "fix"** that was supposed to speed up the loop. It made a
  run go from 379 seconds to 583 seconds. The change was kept because it is the
  correct API shape, but it was not the bottleneck and was reported honestly as
  such.
- **The first attempt at the clarifying-question prompt.** It over-corrected:
  "what normalization was applied?" started asking for clarification instead of
  searching. Rewritten so that searching is the default and clarification is the
  single explicit exception.
- **Intercepting provenance questions before the agent.** Produced bare traces
  with no reasoning and meant the best questions never exercised the agent.

### Six scoring bugs found by self-audit, every one of which favored the project

1. Basename matching in `path_exists` (too generous).
2. Empty retrieval excluded from the denominator.
3. Duplicate task IDs overwriting each other.
4. Infrastructure errors scored as model failures.
5. `lstrip("./")` mangling `../` paths.
6. Unequal candidate budgets between arms.

Also: top-k was being computed over deduplicated sources, so with TOP_K=5 the
chunks collapsed to fewer files and "top-5" silently became "retrieved at all."
Fixed to rank-ordered chunk sources.

**Assume the next scoring bug also favors the project. Audit for direction.**

---

## 12. Business and startup details

Not applicable. This is academic research, not a startup. There is no market, no
pricing, no funding, and no users beyond the lab.

---

## 13. Artifacts and deliverables

All paths are under `~/pathology-agent/` unless stated otherwise.

| File | Contents | Status |
|---|---|---|
| `HANDOFF.md` | Technical handoff: repo state, architecture, commands, env vars, test status, bugs with file:line, conventions | Current as of 2026-08-03 |
| `CONTEXT_HANDOFF.md` | This file | Current |
| `DESIGN_DOC.md` | System design | Written |
| `EVALUATION_PROTOCOL.md` | Pre-registered evaluation plan | Written, not fully executed |
| `PROVENANCE.md` | Determinism, model digests, and the corrected citation record | Written |
| `PAPER_SKELETON.md` | Paper outline | Skeleton only |
| `REVIEW_FINDINGS.md` | Self-audit findings | Written |
| `INTEGRATION.md` | How the two repos connect | Written |
| `NEXT_STEPS.md` | Forward plan | Written |
| `STATUS.md` | Honest status | Written |
| `DEMO.md` | Demo instructions | Written |
| `demo/HOW_TO_DEMO.md` | Demo walkthrough | Written |
| `demo/DEMO_SCRIPT.md` | Demo script | Written |
| `demo/DEMO_LAB_PROFILE.md` | Lab conventions profile used for Aim 2 | Written, reproduced in section 14 |
| `demo/demo_tasks.jsonl` | The 8-task evaluation set | Written, reproduced in section 14 |
| `demo/corpus/` | 9 synthetic files, 36 KB | Written, reproduced in full in section 14 |
| `RUN_REAL.sh` | The launcher | Working |
| `demo/demo.py`, `demo/slack_live.py` | Demo drivers | Have hardcoded paths |
| `demo/slack_app_manifest.yaml` | Slack app configuration | Written |

Memory files written for future chat sessions, at
`~/.claude/projects/-Users-avilash-arfullproject/memory/`:
- `levy-lab-pathology-agent.md`
- `levy-lab-demo-gotchas.md`
Both are indexed in `MEMORY.md` in the same directory.

---

## 14. Content produced so far, reproduced in full

### The synthetic demo corpus, all 9 files

**`demo/corpus/docs/README.md`**
```markdown
# Cohort A - ColoCare Recurrence Analysis

Pipeline order:
1. notebooks/qc_cohortA.ipynb      - quality control
2. src/preprocess.py                - normalization
3. src/cell_typing.py               - Leiden clustering + markers
4. src/niche_discovery.py           - spatial niches
5. src/outcome_association.py       - Cox model vs recurrence
6. notebooks/figures_recurrence.ipynb - Figure 3

Inclusion criteria are in docs/cohort_criteria.md
```

**`demo/corpus/docs/cohort_criteria.md`**
```markdown
# Cohort A inclusion and exclusion criteria

Included: colorectal cancer resections with matched Xenium and H&E,
minimum 12 months follow-up, complete staging data.

Excluded: neoadjuvant-treated cases, samples failing Xenium QC,
cases with missing recurrence status.
```

**`demo/corpus/config/pipeline.yaml`**
```yaml
# Cohort A Xenium pipeline configuration
cohort: cohortA
panel_genes: 103
qc:
  min_transcripts_per_cell: 10
  min_cells_per_gene: 3
clustering:
  leiden_resolution: 0.7
niches:
  k_neighbors: 15
  n_niches: 8
stats:
  model: cox_proportional_hazards
  covariates: [stage, age]
  correction: benjamini_hochberg
```

**`demo/corpus/src/preprocess.py`**
```python
"""Preprocessing for Xenium spatial transcriptomics, Cohort A.

Normalization: counts-per-cell to median, then log1p.
This is the standard lab pipeline for all Xenium cohorts.
"""
import scanpy as sc

def preprocess(adata):
    sc.pp.normalize_total(adata)   # normalize to median counts per cell
    sc.pp.log1p(adata)             # log transform
    return adata
```

**`demo/corpus/src/cell_typing.py`**
```python
"""Cell type annotation using the 103-gene Xenium panel.

Leiden clustering at resolution 0.7, then marker-based label assignment.
"""
import scanpy as sc

MARKERS = {"epithelial": ["EPCAM", "KRT8"], "immune": ["PTPRC", "CD3E"],
           "stromal": ["COL1A1", "VIM"], "endothelial": ["PECAM1"]}

def annotate(adata, resolution=0.7):
    sc.pp.neighbors(adata)
    sc.tl.leiden(adata, resolution=resolution)
    return assign_labels(adata, MARKERS)
```

**`demo/corpus/src/niche_discovery.py`**
```python
"""Spatial niche discovery.

Builds a k=15 spatial neighbour graph over cell centroids, computes
neighbourhood composition vectors, then k-means with k=8 niches.
Writes results/niche_assignments.csv
"""
import numpy as np
from sklearn.cluster import KMeans

K_NEIGHBORS = 15
N_NICHES = 8

def discover_niches(adata):
    composition = neighborhood_composition(adata, k=K_NEIGHBORS)
    return KMeans(n_clusters=N_NICHES, random_state=0).fit_predict(composition)
```

**`demo/corpus/src/outcome_association.py`**
```python
"""Association between spatial niche abundance and recurrence.

Statistical test: Cox proportional hazards, adjusted for stage and age.
Multiple testing correction: Benjamini-Hochberg across the 8 niches.
"""
from lifelines import CoxPHFitter

def test_association(niche_abundance, outcomes):
    cph = CoxPHFitter()
    cph.fit(merged, duration_col="time_to_recurrence", event_col="recurred")
    return cph.summary
```

**`demo/corpus/notebooks/qc_cohortA.ipynb`** (cell sources)
```
# Quality Control - Cohort A
Xenium run QC for the ColoCare recurrence cohort.
Cells with fewer than 10 transcripts are dropped.
---
import scanpy as sc
adata = sc.read_h5ad('/data/cohortA/xenium_raw.h5ad')
sc.pp.filter_cells(adata, min_counts=10)
sc.pp.filter_genes(adata, min_cells=3)
---
QC thresholds were chosen after inspecting the transcript count distribution.
Minimum transcripts per cell: 10. Minimum cells per gene: 3.
```

**`demo/corpus/notebooks/figures_recurrence.ipynb`** (cell sources)
```
# Figure 3 - Recurrence association by spatial niche
Generates the main results figure from niche assignments.
---
import pandas as pd, matplotlib.pyplot as plt
niches = pd.read_csv('results/niche_assignments.csv')
outcomes = pd.read_csv('/data/cohortA/clinical_outcomes.csv')
merged = niches.merge(outcomes, on='patient_id')
fig = plot_recurrence_by_niche(merged)
fig.savefig('results/figure3_recurrence.png', dpi=300)
```

### Design properties deliberately built into the corpus

1. **Facts split across files.** The multiple-testing correction appears in both
   `src/outcome_association.py` (code) and `config/pipeline.yaml` (config).
   Keyword search returns two disconnected hits, so the system has to
   consolidate.
2. **A real duplicated constant.** `N_NICHES = 8` in the code and
   `n_niches: 8` in the config. That is a genuine bug class: change one, forget
   the other. It makes "what would I change to use 10 niches?" a question with a
   genuinely useful answer.
3. **Things deliberately left undocumented.** The patient count is nowhere.
   Neither is why 8 niches, nor why Leiden resolution 0.7. These are the control
   questions. If the system answers them confidently it is hallucinating, and
   that is measurable.
4. **Known ground truth.** Every question has a known correct answer, including
   the questions that have no answer, so hit@1 and hallucination rate are
   actually computable.

### The 8-task evaluation set, `demo/demo_tasks.jsonl`, verbatim

```
# DEMO task set. Answers are real for the SYNTHETIC corpus in demo/corpus/.
# Not lab data. Exists to show the scoring machinery working.
{"id": "loc-001", "category": "locate", "question": "where can I find the QC notebook for this cohort?", "expected_paths": ["notebooks/qc_cohortA.ipynb"], "ground_truth_source": "DEMO FIXTURE"}
{"id": "loc-002", "category": "locate", "question": "which script performs the spatial niche discovery clustering?", "expected_paths": ["src/niche_discovery.py"], "ground_truth_source": "DEMO FIXTURE"}
{"id": "loc-003", "category": "locate", "question": "where are the cohort inclusion and exclusion criteria?", "expected_paths": ["docs/cohort_criteria.md"], "ground_truth_source": "DEMO FIXTURE"}
{"id": "com-001", "category": "comprehend", "question": "what normalization was applied to the expression data?", "expected_paths": ["src/preprocess.py"], "ground_truth_source": "DEMO FIXTURE"}
{"id": "com-002", "category": "comprehend", "question": "which statistical test was used for the outcome association analysis?", "expected_paths": ["src/outcome_association.py"], "ground_truth_source": "DEMO FIXTURE"}
{"id": "rep-001", "category": "reproduce", "question": "which notebook generates the recurrence figure?", "expected_paths": ["notebooks/figures_recurrence.ipynb"], "ground_truth_source": "DEMO FIXTURE"}
{"id": "und-001", "category": "undocumented", "question": "why was leiden resolution 0.7 chosen over other values?", "expect_abstention": true, "ground_truth_source": "DEMO FIXTURE - rationale never written down"}
{"id": "und-002", "category": "undocumented", "question": "who is planning to extend this analysis next quarter?", "expect_abstention": true, "ground_truth_source": "DEMO FIXTURE - not in any file"}
```

### The lab profile, `demo/DEMO_LAB_PROFILE.md`, verbatim

```markdown
## Overview
This lab studies colorectal cancer recurrence using Xenium spatial transcriptomics
with matched H&E. Cohort A is the ColoCare recurrence cohort.

## Naming conventions
Cohorts are named cohortA, cohortB. A file suffixed _v2 supersedes the earlier
version. Notebooks prefixed qc_ are quality control for the named cohort.

## Standard pipelines
The standard order is: QC -> normalization -> cell typing -> niche discovery ->
outcome association -> figures. Each step has one script or notebook.

## Quality control standards
House defaults: minimum 10 transcripts per cell, minimum 3 cells per gene.
Leiden resolution 0.7 is the lab default for cell typing; it is a convention,
not a tuned value, and the rationale was never formally recorded.

## Preferred statistical methods
Outcome association uses Cox proportional hazards adjusted for stage and age,
with Benjamini-Hochberg correction across niches.
```

### The agent's system prompt, current version, verbatim

```
You are the Levy Lab Copilot, assisting digital pathology researchers at Dartmouth.

You have tools for searching and reading the lab's files. Use them - do not answer
from memory. If the tools do not turn up the information, say so plainly rather
than guessing; a wrong answer about where something lives is worse than "I could
not find it".

Always name the specific files your answer relies on. Work in steps: search, read
what looks relevant, then answer.

Searching is the default. If the question names ANY subject at all - a file, a
step, a method, a parameter, "normalization", "QC", "the markers" - search for
it. Do not ask the user to narrow it down first. A question you could have
searched and did not is a failure.

The single exception: a question whose only subject is a bare pronoun with
nothing earlier in the conversation to attach it to ("explain that", "why is it
done this way", "simplify this", said out of nowhere). There is nothing to
search for, so ask which thing they mean, in one short question. Do not pick
something at random, and do not describe yourself or list what you can do -
nobody asked.
```

Note: the original file uses em dashes in this prompt. The dashes above were
normalized for this document only. The actual file content is unchanged.

### Demo questions verified to work right now

Given that the ChromaDB index is empty, these three work because they use
`trace_pipeline`, `read_file`, and `list_files` rather than search:

```
@LevyBoy how was results/figure3_recurrence.png produced?
@LevyBoy trace: results/figure3_recurrence.png
@LevyBoy what files are in the corpus?
```

These currently FAIL because they need semantic search:
```
@LevyBoy what normalization was applied?
@LevyBoy what markers identify stromal cells?
@LevyBoy how many patients are in cohort A?
```

### Demo talking points that were settled on, verbatim

Opening disclosure, to be said before starting:
> "Two things before I start. This is running on my laptop, not Discovery, same
> code, smaller model. And these are synthetic files I wrote that mirror the
> structure of a real Xenium pipeline, not actual patient data. I don't have
> Discovery access yet."

On how hard the move to the cluster is:
> "One line. The model name is an environment variable. qwen3:4b becomes
> qwen3-coder and it points at Discovery's Ollama instead of mine. Nothing else
> changes."

On why synthetic data:
> "I don't have Discovery access yet. But building against synthetic files meant
> I could test whether the answers are actually correct. I know the ground
> truth, so I can measure it. That's harder once you're on real data."

The single most important line, said after showing the pipeline trace:
> "When it answers without opening a file, it tells you. Most tools just give
> you the answer and let you find out later."

On why the tracer cannot hallucinate:
> "The dependency chain isn't generated. workflow.py parses the actual file
> references and builds the graph. The model only writes prose over a finished
> structure. It can't add a step that isn't in the code."

If asked whether anything was measured:
> "Yes. Without retrieval it gets 0 percent hit@1, and 2 of 2 answers that named
> a file made the file up. Against BM25 keyword search it's a tie so far, 0
> discordant pairs. That's an honest result on 8 questions. The protocol calls
> for 30."

If something fails live:
> "That one needs the vector index, which isn't built on this laptop. It lives
> on Discovery. Let me show you the part that doesn't depend on it."

---

## 15. Open questions and blockers

**Blocked on someone else or on access:**
- Discovery HPC access. Avilash is logged in but `srun` errored. Until this is
  resolved there is no cluster run, no larger model, and no real data.
- Real lab data. Depends on Discovery access.

**Unresolved and Avilash's call:**
- Whether to rotate the Slack tokens now or after the demo period. He knows it
  needs doing.
- Whether to push either repo to GitHub. Neither has a remote right now.
- Whether to expand the task set to 30 before or after getting real data.
- Whether to integrate `qwen-code` at all, given the bespoke loop works and is
  better instrumented.

**Open technical questions:**
- Does the BM25 tie survive on real, messier lab files? This is arguably the
  most interesting open question in the whole project.
- What are the actual BMC/BioData Mining submission requirements? Never checked.
- How should usefulness, reproducibility, and time saved actually be measured?
  No rubric has been designed.

---

## 16. Next steps, prioritized

1. **Commit the uncommitted work.** Four files listed in section 11. It is real,
   tested, and currently at risk.
2. **Rebuild the ChromaDB index** so `search_lab_files` works. Index
   `~/pathology-agent/demo/corpus` into collection `levy_lab` at
   `~/pathology-agent/rag/chroma_db`. This unblocks half the demo questions.
3. **Rotate the Slack tokens** at api.slack.com. They are in git history at
   commit `8c51d3e`.
4. **Gitignore `rag/chroma_db/chroma.sqlite3`** and stop tracking the binary.
5. **Push both repos to GitHub.** Neither has a remote. There is no backup.
6. **Resolve Discovery access.** Everything downstream depends on it.
7. **Expand the task set** from 8 to about 30, with at least 12 undocumented
   controls.
8. **Design a rubric** for usefulness, reproducibility, and time saved. Three of
   four promised metrics have no instrument.
9. **Run 3 replicates** instead of 1.
10. **Fix the smaller known bugs:** hardcoded paths in `demo/slack_live.py:69`
    and `demo/demo.py:200`, scratch directory under `/tmp`,
    `workflow._direction` substring misclassification, missing test coverage for
    `evaluation/run_arms.py`.
11. **Check the BMC/BioData Mining submission requirements.**

---

## 17. Failure modes and watch-outs

**Mistakes made during this work, recorded so they are not repeated:**

- **Reported the team GitHub repo as empty** based on a stale cached page. It
  actually had 11 commits including the full RAG pipeline. Re-fetch before
  asserting a repo is empty.
- **Cited Nature Communications `s41467-024-53190-9`** as the source of metrics
  vocabulary. That DOI is Kefeli et al. on TNM staging and does not support the
  claim.
- **Claimed novelty** that a literature search then refuted. Paper2Agent,
  GPT4DFCI-RAG, BRAD, and Nowak et al. all occupy that space.
- **Reported a 50 percent hallucination rate** that was a metric bug. The real
  figure is 0 of 6.
- **Edited Varun's repo directly.** Would have silently reverted on his pull.
- **Chased the wrong cause** on a slowness problem. A `tool_call_id` change made
  a run go from 379 to 583 seconds. The right answer was machine swap.
- **Over-corrected a prompt fix** so that a good question started asking for
  clarification instead of searching.
- **Set `OLLAMA_MAX_LOADED_MODELS=1`**, which fixed one problem and created a
  worse one.

**Things the next chat is likely to get wrong:**

- **Assuming search works.** It does not right now. The index is empty.
- **"Fixing" the fact that the agent sometimes does not retrieve.** That is a
  deliberate decision Avilash made and reaffirmed on 2026-08-03.
- **Editing `~/labagent`.** That is Varun's repo. Use environment variables.
- **Blaming the code when the bot is slow.** Check machine load first. A runaway
  process took the model from 23 to 5 tokens per second with zero code change.
- **Adding warnings that fire on correct behavior.** Warnings must stay rare.
- **Overclaiming in the paper.** Three of four metrics are not instrumented, the
  task set is 8 not 30, there is 1 replicate not 3, no human arm, and no real
  data.
- **Reporting the BM25 tie as a footnote or leaving it out.** It goes in the
  main results.
- **Stripping the comments.** The comments in this codebase record the failure
  that motivated the code, usually with measured numbers. That is on purpose.

**Things Avilash explicitly said not to do:**
- Do not create or edit documents when he asks for an explanation in chat.
- Do not pivot to a different or public dataset.
- Do not wait for Varun or Zarif to proceed.

---

## 18. Anything else

**The conversation memory feature has a naming collision that confused Avilash,
and it will confuse others.** The warning text says "answered from model memory,"
which means the model answered without opening any lab file. That is completely
unrelated to the per-thread conversation memory added the same day. If you
explain this, separate the two explicitly.

**RAG is not a pipe everything flows through. It is a tool the model picks up.**
This was the single biggest conceptual confusion. Avilash reasonably expected
that every question would automatically go through retrieval. It does not, and
that is by design.

**The bot does not hot-reload.** Code changes require killing the terminal
running `RUN_REAL.sh` and starting it again. Easy to forget mid-demo.

**Thread memory is bounded at 3 exchanges and is lost on restart.** Start a
fresh thread for each demo topic.

**The machine had been up 16 days** when the slowness was diagnosed, with an
Adobe Crash Processor stuck in a loop at 120 percent CPU. A reboot would
probably have fixed it faster than any of the investigation.

**qwen3:4b thinks before every answer.** That is why it reliably calls tools when
qwen2.5-coder does not, and it is also a real latency cost paid on every step of
the agent loop.

**The strongest thing about this project, if you need to argue for it:** the
pipeline tracer produces answers that are structurally impossible to fabricate,
and the system reports when it answered without evidence. Those two properties
together are what make it usable on data where a confident wrong answer is
expensive.

**The most honest thing about this project:** BM25 keyword search currently ties
it. Avilash chose to report that.

---

## Instructions for the receiving chat

**Treat this file as authoritative context.** It was verified against the actual
repository, not recalled from memory. Where it states a number, a commit hash, a
file path, or a test count, that was checked. Where it states something is
uncertain, believe the uncertainty.

**What role to take.** A collaborator on a research engineering project. Avilash
is a student doing real work with real deadlines and a real advisor. He is
technically capable and wants to understand what he is running, not be handed a
black box.

**What you can assume without asking.**
- The architecture, file layout, decisions, and rationale described above.
- That the decisions in section 6 are settled. Do not reopen them.
- That plain language and short answers are wanted.
- That generated documents contain no em dashes and no semicolons.

**What you must ask about rather than invent.**
- Anything about real Levy Lab data, its contents, or its structure. You have
  never seen it. Neither has Avilash, in this project.
- What Zarif, Varun, or Dr. Levy have said recently. This file records what was
  known as of 2026-08-04 and nothing after.
- Whether to commit, push, or publish anything. Ask first.
- Anything that would change what he claims in the paper.
- Actual metric values you have not seen computed. Do not invent numbers.
- The state of the machine, whether the bot is running, or whether the index has
  been rebuilt since this file was written. Ask him to check, or check yourself
  if you have shell access.

**Output style he prefers.**
- Short. Lead with the answer.
- Plain language. Define a term the first time or avoid it.
- Concrete commands in fenced code blocks tagged `bash`, one command per block.
- When something is broken, say so plainly with the evidence, including when the
  breakage was yours.
- Never claim something works that you have not verified.
- When he asks "what do I run," tell him which window, which order, and what to
  expect.

**Tools you may not have.** If you are running on a phone or in a different
project, you probably cannot run shell commands, read his files, or restart the
bot. Say so plainly rather than giving instructions that assume you did
something. You can still advise, plan, write, and reason from this file.

**Staying useful over time.** As work continues, the parts most likely to go
stale are section 3 (current state), section 4 (done / in progress / not
started), section 11 (repo state and known bugs), and section 16 (next steps).
Sections 5 through 9 and section 17 should stay valid. When Avilash tells you
something has changed, believe him over this file, and suggest he update the
file.
