"""
LevyBoy - Slack adapter for the Levy Lab digital-pathology agent.

Thin wiring only: it maps real Slack events onto the pure functions in
handlers.py. All behavior/tests live in handlers.py so they run without Slack.

Uses Socket Mode (outbound WebSocket) so it runs from inside the Discovery HPC
firewall with no public endpoint.

Run:
    pip install -r requirements.txt
    cp .env.example .env    # then fill in the two tokens
    python app.py
"""

import logging
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import handlers

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("levyboy")

app = App(token=os.environ["SLACK_BOT_TOKEN"])  # xoxb-... bot token


@app.event("app_mention")
def on_mention(event, client):
    handlers.handle_mention_event(event, client)


@app.event("message")
def on_message(event, client):
    handlers.handle_dm_event(event, client)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])  # xapp-... token
    log.info("LevyBoy starting (Socket Mode)…")
    handler.start()
