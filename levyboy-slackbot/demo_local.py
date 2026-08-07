"""
End-to-end LevyBoy demo WITHOUT Slack, tokens, or a workspace.

It builds realistic Slack event payloads, feeds them through the *real* bot
handlers (handlers.py), and renders what the bot would post as a Slack-style
thread transcript. This proves the whole path -- mention parsing, threaded
reply, "thinking…" placeholder being edited to the answer, agent call, DM
handling, and bot-message filtering -- runs correctly.

The only thing NOT exercised here is Slack's own servers; swapping this FakeClient
for the live slack_bolt client (app.py) is all that remains once tokens exist.

Run:  python demo_local.py
"""

import itertools

import handlers


class FakeClient:
    """Stand-in for the slack_bolt client. Records posts and prints the thread."""

    def __init__(self):
        self._ts = itertools.count(1)
        self.messages = {}  # ts -> dict

    def chat_postMessage(self, channel, thread_ts=None, text=""):
        ts = f"{next(self._ts):.6f}"
        self.messages[ts] = {"channel": channel, "thread_ts": thread_ts, "text": text}
        print(f"    ┌─ bot posts (ts={ts}, thread={thread_ts}): {text}")
        return {"ts": ts, "channel": channel}

    def chat_update(self, channel, ts, text=""):
        self.messages[ts]["text"] = text
        print(f"    └─ bot edits (ts={ts}): {text}")
        return {"ts": ts}


def show(label, event, client, handler):
    print(f"\n### {label}")
    who = event.get("user", "user")
    print(f"  {who} in {event['channel']}: {event.get('text','')!r}")
    result = handler(event, client)
    if result is None:
        print("    (ignored — not a real user message)")
    return result


def main():
    client = FakeClient()

    # 1) A normal channel @mention.
    show(
        "Channel mention",
        {
            "type": "app_mention",
            "user": "U0AVILASH",
            "channel": "C0PATHLGY",
            "ts": "1000.0001",
            "text": "<@U0LEVYBOT> where can I find the QC notebook?",
        },
        client,
        handlers.handle_mention_event,
    )

    # 2) A mention already inside a thread — reply should stay in that thread.
    show(
        "Mention inside an existing thread",
        {
            "type": "app_mention",
            "user": "U0NEHAN",
            "channel": "C0PATHLGY",
            "ts": "1000.0050",
            "thread_ts": "1000.0009",
            "text": "<@U0LEVYBOT> and which script generates the survival figure?",
        },
        client,
        handlers.handle_mention_event,
    )

    # 3) A direct message to the bot.
    show(
        "Direct message",
        {
            "type": "message",
            "channel_type": "im",
            "user": "U0VARUN",
            "channel": "D0VARUN",
            "ts": "1000.0100",
            "text": "where is the Visium preprocessing config?",
        },
        client,
        handlers.handle_dm_event,
    )

    # 4) The bot's own message echoing back — must be ignored (no reply loop).
    show(
        "Bot's own message (should be ignored)",
        {
            "type": "message",
            "channel_type": "im",
            "bot_id": "B0LEVYBOT",
            "channel": "D0VARUN",
            "ts": "1000.0101",
            "text": "some earlier bot reply",
        },
        client,
        handlers.handle_dm_event,
    )

    # 5) Empty mention (just "@LevyBoy") — should get the friendly prompt.
    show(
        "Empty mention",
        {
            "type": "app_mention",
            "user": "U0AVILASH",
            "channel": "C0PATHLGY",
            "ts": "1000.0200",
            "text": "<@U0LEVYBOT>",
        },
        client,
        handlers.handle_mention_event,
    )

    print("\nDemo complete — every path ran through the real handlers.")


if __name__ == "__main__":
    main()
