#!/usr/bin/env python3
"""
LIVE SLACK DEMO — the real bot, in real Slack, on your laptop.

    python3 demo/slack_live.py

This starts the actual Slack bot. You type "@LevyBoy where is the QC notebook?"
in a real Slack workspace and it replies in a real thread with real sources.

WHAT'S REAL HERE
----------------
Real: Slack, the bot, the connection, the threading, the retrieval, the sources.
      This is the same handlers.py and lab_query.py that would run on Discovery.

Stood in: the corpus is demo/corpus/ (synthetic pathology files, not lab data),
      and the language model is a keyword retriever instead of Qwen3-Coder,
      because that needs a GPU. Everything else is production code.

SETUP (about 10 minutes, once)
------------------------------
1. Make a free Slack workspace at slack.com/create  (or use one you own)

2. Go to api.slack.com/apps  →  "Create New App"  →  "From scratch"
   Name it "LevyBoy", pick your workspace.

3. Left sidebar → "Socket Mode" → toggle ON.
   It asks for a token name (anything, e.g. "socket"). Click Generate.
   COPY the token that starts with  xapp-

4. Left sidebar → "OAuth & Permissions" → scroll to "Bot Token Scopes" → Add:
        app_mentions:read
        chat:write
        im:history
        im:read
   Then scroll UP → "Install to Workspace" → Allow.
   COPY the token that starts with  xoxb-

5. Left sidebar → "Event Subscriptions" → toggle ON →
   "Subscribe to bot events" → Add:
        app_mention
        message.im
   Save Changes.

6. In your terminal:
        export SLACK_BOT_TOKEN=xoxb-...paste-yours...
        export SLACK_APP_TOKEN=xapp-...paste-yours...
        python3 demo/slack_live.py

7. In Slack, invite the bot to a channel:   /invite @LevyBoy
   Then ask it something:                   @LevyBoy where is the QC notebook?

TRY THESE
---------
    @LevyBoy where can I find the QC notebook for this cohort?
    @LevyBoy what normalization was applied to the expression data?
    @LevyBoy which script performs the niche discovery clustering?
    @LevyBoy where are the cohort inclusion criteria?
    @LevyBoy why was leiden resolution 0.7 chosen?     <-- the interesting one
"""

from __future__ import annotations

import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOT = "/Users/avilash/levyboy-slackbot"

sys.path.insert(0, os.path.join(ROOT, "rag"))
sys.path.insert(0, HERE)
sys.path.insert(0, BOT)

import demo as demo_mod              # noqa: E402  (reuses the demo's retriever)
import lab_query                     # noqa: E402


# Characters copy/paste and macOS smart-substitution commonly turn a plain
# hyphen into. Slack tokens are pure ASCII, so any of these is a paste artifact.
_DASH_LOOKALIKES = "‐‑‒–—―−﹘﹣－"


def clean_token(raw: str) -> str:
    """Repair a pasted token: strip quotes/whitespace, normalize fancy dashes.

    Without this, a smart-dash produces a UnicodeEncodeError deep inside the HTTP
    layer ("'latin-1' codec can't encode characters"), which gives no hint that
    the real problem is one wrong character in a paste.
    """
    text = (raw or "").strip().strip("'\"").strip()
    for bad in _DASH_LOOKALIKES:
        text = text.replace(bad, "-")
    return "".join(ch for ch in text if not ch.isspace())


def preflight() -> bool:
    # Repair pasted tokens before anything tries to use them.
    for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        raw = os.environ.get(name)
        if not raw:
            continue
        fixed = clean_token(raw)
        if fixed != raw:
            removed = sum(1 for ch in raw if ord(ch) > 127)
            os.environ[name] = fixed
            print(f"  Cleaned {name}"
                  + (f" (replaced {removed} non-ASCII character(s) — "
                     "looks like a smart-dash from copy/paste)" if removed else ""))
        if any(ord(ch) > 127 for ch in os.environ[name]):
            print(f"\n  {name} still contains characters Slack can't accept.")
            print("  Retype it by hand rather than pasting, or paste into a")
            print("  plain-text editor first to strip formatting.\n")
            return False

    missing = [
        name for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN")
        if not os.environ.get(name)
    ]
    if missing:
        print(f"\n  Missing: {', '.join(missing)}\n")
        print("  Set them first:\n")
        print("      export SLACK_BOT_TOKEN=xoxb-your-token")
        print("      export SLACK_APP_TOKEN=xapp-your-token\n")
        print("  See the setup steps at the top of this file:")
        print(f"      open {__file__}\n")
        return False

    if not os.environ["SLACK_BOT_TOKEN"].startswith("xoxb-"):
        print("\n  SLACK_BOT_TOKEN should start with 'xoxb-'. "
              "You may have pasted the app token by mistake.\n")
        return False
    if not os.environ["SLACK_APP_TOKEN"].startswith("xapp-"):
        print("\n  SLACK_APP_TOKEN should start with 'xapp-'. "
              "You may have pasted the bot token by mistake.\n")
        return False

    try:
        import slack_bolt  # noqa: F401
    except ImportError:
        print("\n  Missing the Slack library. Install it with:\n")
        print("      pip3 install slack-bolt\n")
        return False
    return True


def main() -> int:
    print("\n" + "=" * 70)
    print("  LEVYBOY — LIVE IN SLACK")
    print("=" * 70)

    if not preflight():
        return 1

    # Point the production retrieval code at the demo corpus, using the same
    # keyword stand-in the terminal demo uses.
    chunks = demo_mod.build_index(demo_mod.CORPUS)
    collection = demo_mod.KeywordCollection(chunks)
    lab_query._default_collection = lambda: collection
    lab_query._default_embed = demo_mod.embed
    lab_query._default_chat = demo_mod.compose_answer

    import agent
    agent.BACKEND = "rag"

    files = len({c["source"] for c in chunks})
    print(f"\n  Corpus:  {files} files, {len(chunks)} chunks  (demo/corpus — synthetic)")
    print(f"  Backend: {agent.describe_backend()}")
    print("  Model:   keyword stand-in (Qwen3-Coder needs a GPU)")

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    import handlers

    logging.basicConfig(level=logging.WARNING)
    print("\n  Checking your bot token with Slack…")
    try:
        app = App(token=os.environ["SLACK_BOT_TOKEN"])
    except Exception as exc:
        if "invalid_auth" in str(exc):
            print("""
  Slack rejected the bot token.

  Common causes:
    - The app was never installed to the workspace.
      Fix: api.slack.com/apps -> your app -> OAuth & Permissions
           -> "Install to Workspace"
    - You copied the token before installing, so it is stale.
      Re-copy the "Bot User OAuth Token" after installing.
    - You pasted a token from a different app.
""")
        else:
            print(f"\n  Could not start: {type(exc).__name__}: {exc}\n")
        return 1
    print("  Bot token accepted.")

    @app.event("app_mention")
    def on_mention(event, client):
        print(f"  ← @mention: {event.get('text', '')[:70]}")
        handlers.handle_mention_event(event, client)

    @app.event("message")
    def on_message(event, client):
        if event.get("channel_type") == "im" and not event.get("bot_id"):
            print(f"  ← DM: {event.get('text', '')[:70]}")
        handlers.handle_dm_event(event, client)

    print("\n  Connecting to Slack…")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])

    print("""
  CONNECTED. The bot is live.

  In Slack:
      /invite @LevyBoy                                  (once, per channel)
      @LevyBoy where is the QC notebook for this cohort?
      @LevyBoy what normalization was applied?
      @LevyBoy why was leiden resolution 0.7 chosen?    <-- watch this one

  Ctrl+C to stop.
""")
    print("=" * 70 + "\n")

    try:
        handler.start()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
