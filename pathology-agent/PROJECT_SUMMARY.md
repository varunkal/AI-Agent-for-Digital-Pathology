# What this project is, and where it actually stands

## What the EDIT program asked for

From Zarif's project description, which is the authoritative brief:

> Use LLMs, ideally open-source, to build AI agents that can plan, execute and
> interpret digital pathology experiments. Help researchers move from a
> high-level biological question to a concrete, reproducible computational
> experiment. For example, a researcher asks "which spatial niches are
> associated with recurrence in this cohort?" and the agent identifies the
> relevant datasets, notebooks, code, metadata fields, statistical tests, prior
> results and visualization scripts.
>
> A key goal is that the agent personalises to one specific lab: its workflows,
> file structures, naming conventions, preferred statistical methods and QC
> standards. Not a generic coding assistant.
>
> The goal is not to replace researchers. It is a reliable, transparent research
> assistant that speeds up repetitive, technically complex work while humans keep
> scientific judgement.
>
> Agents must operate in controlled environments and must not overwrite or
> modify original research data.

The intended output is a publication describing the framework plus case studies
showing reduced time-to-analysis and improved reproducibility.

## What has actually been built

**A research assistant that lives in Slack.**

Someone asks a question in plain English. The assistant decides for itself what
to look at, opens the lab's real files, and answers. There are no commands to
learn.

It handles the full range of what people actually ask:
- where something lives
- how a particular figure was produced
- what a script does
- follow-ups in the same conversation ("explain that more simply")
- general background questions
- questions whose answer was never written down

**Three things make it more than a chatbot:**

1. **Every answer says where it came from.** The list of files is counted from
   what the system actually opened, not from what the model claims. If it
   answered without opening anything, it says so. You can always tell whether an
   answer is checkable.

2. **Pipeline tracing cannot be faked.** For "how was this figure made", the
   chain of scripts is computed by reading the real file references. The model
   only writes prose over a finished structure. It cannot invent a step that is
   not in the code.

3. **It runs entirely on local hardware** using an open-weight model. No lab data
   leaves the machine.

**Read-only, as required.** It never writes, edits or deletes lab files. Code
execution exists in the codebase but is switched off and is not even offered to
the model.

**Plus a real evaluation harness.** A frozen set of questions with known correct
answers, run through the agent and through a plain keyword-search baseline,
scored automatically with proper statistics.

195 automated tests. Verified working in a live Slack workspace.

## How that maps to the brief

| What the brief asked for | Status |
|---|---|
| Open-source LLM | Done. qwen3:4b, local |
| Agent connected to the lab's code, notebooks and files | Done |
| Identify relevant datasets, notebooks, code, scripts | Done |
| Transparent and reliable | Done. Sources on every answer |
| Read-only, never modifies original data | Done and enforced |
| Personalise to the lab's conventions | Partly. Conventions can be injected into prompts, not learned |
| Plan, execute and interpret experiments | Not built |
| Cohort selection, preprocessing decisions, figure generation | Not built |
| Case study on a completed real project | Not started. Needs cluster access |
| Measure reduced time-to-analysis and reproducibility | Not measured |

**The honest gap:** the brief describes an agent that runs experiments. What
exists is an agent that understands and explains work that already happened.
That is a real and useful subset, and it is where the measurable research
question turned out to be, but it is a subset.

## What has been measured, and what it showed

Everything so far is on a synthetic file corpus written in-house, clearly
labelled as such. No real lab data has been touched.

The original claim was that an agent finds things better than plain keyword
search. **That was tested properly and it is not true.** On questions whose
answers span several files, the agent and keyword search tied exactly.

One thing did separate. On questions whose answer was never recorded anywhere,
the agent said "that is not written down" three times out of four. Keyword
search cannot do this at all: it always returns its top-ranked files whether or
not any of them are relevant.

## Where it is going

The research claim shifts from "it finds things better" to **"it knows when it
does not know."**

In a lab, a confident wrong answer about how a figure was produced is worse than
no answer, because someone will write it into a paper. That is a real problem,
it is specific to research settings, and it is the thing this system visibly
does.

The next test compares the agent against a plain language model with no file
access, on questions whose answers genuinely do not exist. Keyword search is the
wrong comparison for this because it cannot refuse by construction.

## What is blocking it

Two things, neither of which is code:

1. **Discovery access.**
2. **A completed lab project, and the person who ran it**, who can confirm what
   actually produced a given result and confirm what was never written down.
   Without a human to establish ground truth there is no case study.

Almost nothing else needs building. The comparison arm already exists in the
harness and needs a few hours of wiring. The questions themselves have to be
written against real files, so that work is blocked behind the access, not the
other way round.
