# Demo script — what to say

**One command:**

```bash
cd ~/pathology-agent && python3 demo/demo.py
```

Press **Enter** to advance. It pauses between sections so you can talk.
Add `--no-pause` to let it run straight through.

Takes about 5 minutes with commentary. Nothing to install, no internet, no cluster.

---

## Opening (20 seconds)

> "This is a research assistant for the Levy Lab. You ask it where something is in
> the lab's files, and it answers — with the sources. Everything runs on the lab's
> own hardware, so no data ever leaves the institution.
>
> One thing up front: the corpus here is synthetic, and the AI model itself is
> stood in for, because it needs a GPU. Everything else — the retrieval, the safety
> checks, the scoring — is the real production code."

**Don't skip that last part.** Being straight about what's simulated is what makes
the rest believable.

---

## Act 1 — The assistant (90 seconds)

Four questions run. The first three work well.

> "It finds the right file and lists where the answer came from. That source list
> is the point — you can check it, rather than trusting it."

**Then stop on the fourth question.** This is the most important moment.

> "This one asks *why* resolution 0.7 was chosen. Nobody ever wrote that down. The
> right answer is 'I don't know.'
>
> Instead it found a line mentioning 0.7 and answered as if that explained the
> decision. That's a real failure, and I didn't stage it.
>
> Which is exactly why the next part exists."

If someone asks *"is that a bug?"* — no. It's the known weakness of this kind of
system, and the evaluation is built to measure it rather than hope it away.

---

## Act 2 — Safety (60 seconds)

> "Dr. Levy asked on July 10 for safeguards so agents can't modify lab files. That
> was written down but nothing enforced it. Now something does."

Five attacks run, all blocked. **Point at the shortcut one:**

> "This is the one that matters. Someone puts a shortcut inside an approved folder
> that points at patient records. A naive check just compares the text of the path
> and lets it straight through. This resolves the shortcut first, then checks — so
> it's refused."

Honest caveat, worth saying yourself before anyone asks:

> "This is a guardrail, not a sealed box. It constrains code that goes through it.
> It can't stop a program that deliberately goes around it. That limitation is
> written into the code comments, not hidden."

---

## Act 3 — The evaluation (2 minutes)

This is the part that makes it a paper rather than a tool.

> "Eight questions with known correct answers. Two methods: the assistant, and a
> baseline with no grounding in the files. Same questions, same scoring."

Walk through the numbers:

- **Hit@1 and Hit@3 — 100% for the assistant, 0% for the baseline.** Both capped at
  the same number of guesses, so it's a fair comparison.
- **Made-up file paths — 0% for the assistant, 17% for the baseline.** Fully
  automatic; it checks every cited path against a real file list.
- **p = 0.031** on the paired test.

**Then land the honest part** — the script prints it in red:

> "Correct abstention: 0 out of 2. On both questions whose answers were never
> written down, it answered anyway.
>
> The baseline scored 2 out of 2 there — but only because it had nothing to say at
> all. That's not a virtue.
>
> This is the most valuable thing the harness does. Without those two control
> questions I'd be reporting 100% accuracy and would never have noticed it
> confidently answering something it cannot know."

**If you say nothing else in the whole demo, say that.** Reporting a weakness you
found in your own system is what separates a project from a demo.

---

## Act 4 — Why the results can be trusted (45 seconds)

> "Last thing. The real 30-question set ships with every correct answer blank,
> because only someone with lab access can fill those in.
>
> Watch what happens if you try to score it anyway."

It exits with an error and prints no numbers.

> "It refuses. You can't accidentally produce a percentage that looks real but
> isn't. That guarantee is why any number this thing eventually prints is worth
> something."

---

## Closing (30 seconds)

> "So: a working assistant, enforced safety, and an evaluation system that already
> caught a real weakness in my own work.
>
> What's missing is real results. That needs cluster access and one completed lab
> project to test against — a finished analysis where we know the right answers.
> That's the one thing blocking the study, and it's the main thing I need."

---

## Likely questions

**"Is this actually running the AI model?"**
No. The model needs a GPU. The retrieval, safety, and scoring are all real
production code; the model is stood in for. On Discovery it's Qwen3-Coder via
Ollama.

**"Did you change Varun's code?"**
No — verified, not one byte. Everything is new files that sit alongside his and
call into them, so there's no conflict with what he's building.

**"Why does it fail the abstention questions?"**
Because a retrieval system finds text containing the keywords and treats that as an
answer. It's a known, expected limitation. The point is that it's now *measured*
rather than assumed away.

**"How do I know these numbers aren't cherry-picked?"**
The questions are frozen in a file before anything runs, the scoring code is the
same for every method, and the whole thing is on GitHub. Run it yourself.

**"What's left?"**
Real data. A completed project to test against, cluster access, Slack keys, and an
ethics determination. Everything else is built.

---

## If something goes wrong

The demo needs only Python 3 — no packages, no internet, no cluster. If it fails,
`python3 -m pytest tests/ -q` runs 71 checks in under a second and shows the same
components working.
