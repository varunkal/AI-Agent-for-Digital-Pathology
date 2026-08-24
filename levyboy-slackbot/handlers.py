"""
Core LevyBoy logic, with NO Slack dependency.

Everything that decides *what the bot does* lives here so it can be run and
tested without slack_bolt, without tokens, and without a live workspace. app.py
is a thin adapter that wires real Slack events into these functions; the local
demo (demo_local.py) wires fake events into the exact same functions.

A "client" here is any object exposing Slack's chat_postMessage / chat_update.
The real slack_bolt client satisfies this; so does the FakeClient in the demo.
"""

import collections
import re

import agent

PLACEHOLDER = ":hourglass_flowing_sand: thinking…"

# Conversation memory, keyed by Slack thread.
#
# Without this, every message was turn one. A follow-up like "explain that
# without the jargon" reached the model with no referent for "that", so it
# answered a question nobody asked, typically by describing itself.
#
# Bounded on every axis deliberately:
#   MAX_THREADS   caps memory in a long-running process.
#   MAX_TURNS     caps how far back a thread reaches. Raised from 6 to 12
#                 because following up on a file is the normal way people use
#                 this, not an edge case: open a file, then ask four or five
#                 things about it. Three exchanges ran out mid-conversation.
#   MAX_TURN_CHARS truncates each remembered turn. Every carried turn is re-read
#                 by the model on every step of the agent loop, so an unbounded
#                 one costs latency on all eight steps and can push the whole
#                 conversation out of the context window.
MAX_THREADS = 200
MAX_TURNS = 12  # 6 question/answer pairs
MAX_TURN_CHARS = 700

# How many progress lines to show while the agent works. Enough to see what it
# is doing, short enough that the message does not jump around the screen.
MAX_PROGRESS_LINES = 5

_threads: "collections.OrderedDict[str, list]" = collections.OrderedDict()


def thread_history(thread_ts: str) -> list:
    """Earlier turns of this thread, oldest first. Empty for a new thread."""
    return list(_threads.get(thread_ts, []))


def remember(thread_ts: str, question: str, reply: str) -> None:
    """Record one exchange, evicting the oldest thread once the cap is hit."""
    turns = _threads.setdefault(thread_ts, [])
    turns.append({"role": "user", "content": question[:MAX_TURN_CHARS]})
    turns.append({"role": "assistant", "content": reply[:MAX_TURN_CHARS]})
    del turns[:-MAX_TURNS]
    _threads.move_to_end(thread_ts)
    while len(_threads) > MAX_THREADS:
        _threads.popitem(last=False)


def forget(thread_ts: str) -> None:
    """Drop one thread's memory, for `@LevyBoy reset`."""
    _threads.pop(thread_ts, None)


def forget_all() -> None:
    """Drop all conversation state. For tests."""
    _threads.clear()


def strip_mention(text: str) -> str:
    """Remove any '<@…>' bot mention so the agent gets a clean question.

    Uses <@[^>]+> so it's robust to every Slack mention form, including
    team-qualified ones like <@U123|username>.
    """
    return re.sub(r"<@[^>]+>", "", text or "").strip()


def _spoken_part(reply: str) -> str:
    """The answer without our own status trailers.

    The reply carries "_Looked at:_ …" and warning lines for the human reader.
    Feeding those back as conversation would have the model treat its own
    diagnostics as content and start narrating them.
    """
    # Every trailer we emit is italic, so it opens with an underscore. A real
    # answer line never does.
    lines = [line for line in reply.splitlines() if not line.lstrip().startswith("_")]
    return "\n".join(lines).strip()


def _progress_text(steps) -> str:
    """The live status message: what the agent has done so far."""
    shown = steps[-MAX_PROGRESS_LINES:]
    bullets = "\n".join(f"• {line}" for line in shown)
    return f":hourglass_flowing_sand: working…\n{bullets}"


def answer(client, channel: str, thread_ts: str, question: str) -> str:
    """Post a placeholder, run the agent, edit the placeholder with the result.

    Returns the final answer text (handy for tests/logging). Any agent failure is
    caught and surfaced in-thread so the bot process stays alive, and so the
    person asking gets a reply rather than a message that sits on "thinking"
    forever.
    """
    if question.strip().lower() in {"reset", "forget", "start over"}:
        forget(thread_ts)
        text = "Cleared this thread's memory. Ask me something fresh."
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
        return text

    placeholder = client.chat_postMessage(
        channel=channel, thread_ts=thread_ts, text=PLACEHOLDER
    )
    done: list = []

    def on_progress(line: str) -> None:
        # Best effort. A failed status edit (rate limit, transient network) must
        # not lose the answer that is still being computed.
        done.append(line)
        try:
            client.chat_update(
                channel=channel, ts=placeholder["ts"], text=_progress_text(done)
            )
        except Exception:
            pass

    try:
        result = agent.ask(question, history=thread_history(thread_ts), on_progress=on_progress)
    except Exception as e:  # noqa: BLE001 - keep bot alive, report in thread
        result = f":warning: Agent error: {e}"
    else:
        # Only successful exchanges are remembered. Carrying an error message
        # forward would have the model try to explain the traceback on the next
        # turn instead of answering the question.
        spoken = _spoken_part(result)
        if spoken:
            remember(thread_ts, question, spoken)
    client.chat_update(channel=channel, ts=placeholder["ts"], text=result)
    return result


def handle_mention_event(event, client) -> str:
    """Logic for an app_mention event. Replies in a thread."""
    question = strip_mention(event.get("text", ""))
    thread_ts = event.get("thread_ts") or event["ts"]
    return answer(client, event["channel"], thread_ts, question)


def is_real_dm(event) -> bool:
    """True only for genuine user DMs (skip the bot's own + system messages)."""
    return (
        event.get("channel_type") == "im"
        and not event.get("bot_id")
        and not event.get("subtype")
    )


def handle_dm_event(event, client):
    """Logic for a direct message. Ignores bot/system noise; else replies."""
    if not is_real_dm(event):
        return None
    question = strip_mention(event.get("text", ""))
    thread_ts = event.get("thread_ts") or event["ts"]
    return answer(client, event["channel"], thread_ts, question)
