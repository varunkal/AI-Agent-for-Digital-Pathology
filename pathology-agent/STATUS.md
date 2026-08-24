# Avilash — Complete Work Summary

*Digital Pathology Agent Project · 29 July 2026*

**4,600 lines across 22 files. 80 automated tests, all passing. 9 saved versions.**

Nothing has been pushed to GitHub yet. **Nothing in Varun's code was edited** —
everything here is new files that sit alongside his and call into them, so there is
no collision with his current work.

---

# PART 1 — The Slack bot

A bot for the lab's Slack. Mention it in a channel or send it a direct message, and
it replies inside a thread with an answer plus the list of files that answer came
from.

**What it does, exactly:**
- Notices when it's spoken to (channel mention or DM)
- Strips out the "@LevyBoy" part so the question is clean
- Posts "thinking…" immediately, then edits that into the real answer
- Replies in a thread so channels stay tidy
- Lists the source files underneath the answer
- Ignores its own messages so it never talks to itself in a loop
- Gives a friendly prompt if you mention it with no question
- Keeps running if something breaks, and reports the error in the thread

**Why it can run on the lab's computer at all:** the lab's cluster can't accept
incoming web traffic. The bot dials *out* to Slack instead, so it works from behind
the firewall with no public web address. That's the design detail that makes it
deployable next to the model.

**Three modes it can run in:** fake answers (works anywhere, for demos), connected
to the real search on the cluster, or connected through a command line. Switching
between them is one setting.

**Tested:** 9 automated checks, plus a demo that runs every scenario — channel
mention, mention inside an existing thread, direct message, its own message being
correctly ignored, and an empty mention.

**Still needs:** Slack keys from an admin, and cluster access to run it beside the
model.

*Files: 536 lines across 6 files.*

---

# PART 2 — Search that reports its sources

**The problem:** Varun's search produces an answer but discards the record of which
files it read. That information exists inside his code and gets printed to the
screen, but it isn't handed back to whoever asked. Without it, you cannot measure
accuracy — you can't check whether the right file was found, or whether the AI
invented a file that doesn't exist.

**What I built:** a version that keeps the file list. It uses the exact same
settings as his (same collection, same model, same number of results — I checked
each one against his source code, and there's a test that fails if they ever drift
apart).

It also works out:
- Which files the answer *named* in its text
- Whether those files actually exist
- Whether the answer was a genuine "I don't know" rather than a guess
- How long it took

**Why it's a separate file:** Varun is actively editing his file right now. Adding
to it would have caused a conflict. Nothing of his changes.

*File: 340 lines.*

---

# PART 3 — Safety limits

Dr. Levy asked on 10 July for safeguards so agents can't modify lab files. The
project description says the same. But that was a written intention — no code
enforced it.

**Now enforced:**
- Reads only from folders on an approved list
- **Can't be fooled by shortcuts.** A shortcut placed inside an approved folder but
  pointing outside it is detected and refused. This is the failure that would
  otherwise let the agent reach real patient data.
- A folder named `data-backup` is correctly treated as *outside* a folder named
  `data`, despite the similar name
- Blocks `.git`, password files, and SSH keys
- Any writing is confined to one scratch folder, and a strictly read-only mode
  refuses all writing

**Stated honestly in the code:** this is a guardrail, not a sealed box. It
constrains code that goes through it. It can't stop a program that deliberately
goes around it. Overstating that would be exactly the kind of security claim that
gets punished in review.

*File: 178 lines.*

---

# PART 4 — The evaluation system

This is the part that turns the project into a paper. It's the largest piece of
work here.

## What it measures

- **Did it find the right file?** — capped so every method gets the same number of
  guesses, otherwise the AI's five suggestions would be unfairly compared against a
  human's one
- **Did it cite files that don't exist?** — fully automatic, no human judgement
  needed. The single most convincing number in the paper.
- **Did it admit when something wasn't written down?** — instead of inventing an
  answer
- **Did it refuse when it shouldn't have?** — over-refusing is also a failure
- **How long did it take**, and how many candidate files it offered

Every percentage comes with a range showing how uncertain it is, and comparisons
use a proper paired statistical test.

## Three safeguards built in

1. **Fake results are impossible.** The 30-question template ships with the correct
   answers deliberately blank. The system refuses to produce any score until a
   person with lab access fills them in — it exits with an error rather than
   printing numbers.
2. **Control questions.** Five of the thirty have answers that were *never written
   down anywhere*. The correct behaviour is to say "I don't know." This directly
   measures whether the AI makes things up, and it's what stops us overclaiming.
3. **No automatic connection to outside AI services.** The comparison against a
   general-purpose AI needs an external service. I deliberately did *not* build
   that connection — sending lab content outside needs Dr. Levy's written approval,
   and automating it would make the wrong thing easy to do by accident. A person
   runs those queries and types in the results.

## What's in it

- A question format with correct answers and a record of who confirmed each one
- A checker that flags any question missing its answer
- A runner that works through the questions and records everything, and can resume
  if interrupted
- The scoring engine
- A practice mode that tests the whole pipeline with fake data, clearly labelled so
  it can never be mistaken for real results

*Files: 1,204 lines across 4 files, plus the 30-question template.*

---

# PART 5 — Written documents

| Document | What it is |
|---|---|
| **Design document** | The one our team never wrote — it was due in week 3, and other teams shared theirs on 2–3 July. Follows the same format previous cohorts used. |
| **Evaluation plan** | Exactly how the experiment runs, what's measured, what counts as success, and what could go wrong. |
| **Paper skeleton** | Full structure. The methods section is already written from verified facts. Results contains **no numbers** — just empty tables — because no data exists yet. |
| **Source record** | Every factual claim, where it came from, and how solidly it's verified. Includes a correction to a citation I got wrong. |
| **Review findings** | Everything the three outside reviews found. |
| **Handover notes** | How to fold this into Varun's repo, and the bugs to tell him about. |

*Total: 1,277 lines across 6 documents.*

---

# PART 6 — What outside review found

I ran three independent reviews **before collecting any data** — a hostile
methods/statistics referee, a literature search, and a check of the journal's
actual rules.

## Six bugs in my own scoring code — all now fixed

**Every one made results look better than they really were.** That's the worst
direction for an error. Each now has a test so it can't come back.

1. **The made-up-file check matched on filename only.** With `src/utils.py` in the
   lab, an invented path like `made/up/folder/utils.py` counted as real. Lab folders
   are full of `utils.py` and `README.md`, so this would have pushed the
   "invented files" rate toward zero artificially.
2. **A search returning nothing was scored "not applicable"** instead of a failure —
   so the worst failures vanished from the results.
3. **Duplicate entries silently deleted people.** With three participants, the
   comparison kept only the last one, while the totals still counted all three as
   separate questions.
4. **Crashes were counted as wrong answers.** A timeout is not the AI being wrong.
5. **A path-handling flaw** rewrote `../../etc/file.py` into `etc/file.py`, turning
   a path that escaped the lab folder into an apparently valid one.
6. **The comparison was unfair** — the AI got five guesses, a human got one.

## The novelty claim doesn't hold

A literature search **refuted it**. Published work already covers it:
**Paper2Agent** (indexes a paper's own code and checks reproduction),
**Dana-Farber's pathology RAG system** (same field, two years old), and
**on-premise LLM work in radiology**.

Rewritten around what does look unaddressed: grounding in a lab's **messy
unpublished files** rather than polished public repositories, and answering "where
did this come from" rather than running analyses.

## Other findings

- **Modella AI's "Judith" is real** — I'd flagged it unverified. It exists, came out
  of the Mahmood Lab, and Modella AI has been acquired by AstraZeneca. We should
  cite it.
- **I cited a paper wrongly.** I'd copied a reference out of the lab's project
  spreadsheet without reading it. It's a different paper than I described.
  Corrected, with the lesson written down.
- **Journal deadline is 27 April 2027**, not August. Editor-in-Chief is Nicholas
  Tatonetti at Cedars-Sinai.
- **Two experiments reviewers will demand:** the same model *without* search (the
  real test of whether grounding helps), and a plain keyword-search comparison. Both
  run on our own hardware with no outside calls.
- **Three claims should be dropped** — time saved, reproducibility, and reuse. None
  of them are actually measured by the current design.

---

# What I need from the team

| From | What |
|---|---|
| **Dr. Levy** | Is there a **completed project** we can test against, with recoverable correct answers? Without this there is no study. Also the ethics determination — the journal says approval usually can't be obtained after the fact, so this should be settled before we run anything. |
| **Varun** | Cluster access. Has the search been run on real lab files yet, or only test files? |
| **Zarif** | Sign-off on the pass/fail targets **before** data collection, so the bar isn't set after seeing results. |
| **Admin** | Slack app and keys to put the bot live. |
| **Team decision** | Whether to add the two experiments above, and whether to call this an "agent" or more accurately a "retrieval assistant." |

**Also:** Varun's repo has a broken submodule reference that makes fresh copies fail
to set up. One-line fix, written up in the handover notes.

---

# Honest status

**Built and tested:** everything above.

**Not done:** the experiment itself. Every number produced so far comes from fake
test data, clearly labelled as such. No real result exists yet, and I haven't
invented any.

**The blocker:** whether a finished project exists to test against. That decides
whether the study is possible at all, and only Dr. Levy can answer it.
