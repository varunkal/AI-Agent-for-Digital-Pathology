# How to demo this — start here

There are three versions. Pick based on how much time you have.

| | What people see | Setup | Needs |
|---|---|---|---|
| **A. Terminal** | The whole system in one script | none | just Python |
| **B. Live in Slack** | You type `@LevyBoy`, it answers for real | ~10 min, once | a free Slack workspace |
| **C. Slack + real model** | The real AI on real lab files | — | **Discovery access — you don't have this yet** |

**Do B if you want people to see it working.** Do A alongside it, because A is the
part that shows the science.

---

# A. Terminal demo

```bash
cd ~/pathology-agent && python3 demo/demo.py
```

Press Enter between sections. ~5 minutes. Shows the assistant answering, the safety
guardrails blocking five attacks, the evaluation scoring two methods, and the
harness refusing to fake results.

Talking points: `demo/DEMO_SCRIPT.md`

---

# B. Live in Slack — what you're picturing

You type `@LevyBoy where is the QC notebook?` in a real Slack channel and it
replies in a thread with the answer and the file it came from.

**This is the real bot.** Same code that would run on Discovery. Only two things
differ: the files it searches are the synthetic demo corpus instead of real lab
files, and the answer is composed by a keyword matcher instead of Qwen3-Coder
(which needs a GPU).

## Setup — about 10 minutes, once

**1. Get a workspace.** Free one at [slack.com/create](https://slack.com/create),
or use one you already own. Don't use the EDIT workspace — that needs an admin.

**2. Create the app.** Go to [api.slack.com/apps](https://api.slack.com/apps) →
**Create New App** → **From scratch**. Name it `LevyBoy`, pick your workspace.

**3. Turn on Socket Mode.** Left sidebar → **Socket Mode** → toggle **On**. It asks
for a token name — type anything. Click Generate.
**Copy the token starting with `xapp-`.**

**4. Add permissions.** Left sidebar → **OAuth & Permissions** → scroll to **Bot
Token Scopes** → **Add an OAuth Scope**, four times:

```
app_mentions:read
chat:write
im:history
im:read
```

Then scroll back **up** → **Install to Workspace** → **Allow**.
**Copy the token starting with `xoxb-`.**

> Order matters — install *after* adding the scopes, or the token won't work.

**5. Subscribe to events.** Left sidebar → **Event Subscriptions** → toggle **On** →
**Subscribe to bot events** → add `app_mention` and `message.im` → **Save Changes**.

**6. Run it.**

```bash
pip3 install slack-bolt
```

```bash
cd ~/pathology-agent
export SLACK_BOT_TOKEN=xoxb-paste-yours-here
export SLACK_APP_TOKEN=xapp-paste-yours-here
python3 demo/slack_live.py
```

You should see `CONNECTED. The bot is live.`

**7. In Slack**, invite it to a channel, then ask it something:

```
/invite @LevyBoy
```
```
@LevyBoy where can I find the QC notebook for this cohort?
```

## Questions to ask during the demo

Run these in order — the last one is the point.

```
@LevyBoy where can I find the QC notebook for this cohort?
@LevyBoy what normalization was applied to the expression data?
@LevyBoy which script performs the niche discovery clustering?
@LevyBoy where are the cohort inclusion and exclusion criteria?
@LevyBoy why was leiden resolution 0.7 chosen over other values?
```

The first four work. **The fifth is the one to talk about** — nobody ever wrote
down *why* 0.7 was chosen, so the honest answer is "I don't know." Instead it finds
a line mentioning 0.7 and answers as if that explains the decision.

Say that out loud when it happens:

> "That's wrong, and I didn't stage it. Nobody wrote down why 0.7 was picked, so it
> should have said it didn't know. This is the known weak spot of retrieval systems
> — and it's exactly why I built the evaluation. Let me show you it catching this."

Then run the terminal demo (A) and point at **correct abstention: 0 out of 2**.

---

# What to say about what's real

Say this early. It costs nothing and it's what makes everything else credible:

> "Two things are stood in here. The files are synthetic, not real lab data. And
> the AI model is replaced with a keyword matcher, because the real one needs a
> GPU on Discovery. Everything else — Slack, the bot, the retrieval, the source
> tracking, the safety checks, the scoring — is the actual code."

---

# If it breaks

| Problem | Fix |
|---|---|
| `Missing: SLACK_BOT_TOKEN` | The `export` lines didn't run. Same terminal window? |
| `should start with 'xoxb-'` | The two tokens are swapped. |
| `Slack rejected the bot token` | You copied it before clicking **Install to Workspace**. Install, then re-copy. |
| Bot is online but silent | Either it isn't in the channel (`/invite @LevyBoy`), or Event Subscriptions is off / missing `app_mention`. |
| `No module named slack_bolt` | `pip3 install slack-bolt` |

**Backup if Slack fails during a live demo:** run `python3 demo/demo.py`. It needs
nothing but Python and shows the same components, including a scripted version of
the Slack exchange.

---

# The honest framing

What you can show today: **a working assistant, enforced safety, and an evaluation
system that already caught a real weakness in the assistant.**

What you can't show yet: **any real result.** That needs Discovery access and a
completed lab project with known correct answers. That's the one thing blocking the
study, and it's worth saying plainly at the end.
