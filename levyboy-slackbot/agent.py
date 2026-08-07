"""
The seam between Slack and the Levy Lab agent.

WHAT THIS IS
------------
One path: every message goes to the agent. The agent has tools over the lab's
real files and decides for itself which to use, so the person asking never has
to know how the system is built.

This replaced a router that dispatched on typed prefixes (`trace:`, `fast:`,
`deep:`). That design put the burden in the wrong place. It asked the person to
classify their own question before asking it, it meant the interesting questions
took the boring path whenever someone forgot a prefix, and it made the system a
lookup table with an agent bolted on rather than an agent. The tools it used to
route to are all still here; the agent picks them now:

    search_lab_files   semantic search over the indexed corpus
    read_file          read a file in full
    trace_pipeline     deterministic dependency chain for an output artifact
    list_files         what exists in the corpus

Two backends remain, chosen by LEVYBOY_BACKEND:

  "rag"   the real stack: local Qwen via Ollama, agent loop, lab corpus.
  "stub"  canned replies, no model needed, so the Slack plumbing can be
          exercised with nothing running. Default, because it cannot mislead.

SAFETY (per Dr. Levy's 7/10 guidance and the pitch's read-only commitment):
read-only. It never writes, edits, or deletes lab files, and never executes
agent-authored code. `allow_execution` is left at its default of False, so the
run_python tool is not even offered to the model.
"""

import os
import re

BACKEND = os.environ.get("LEVYBOY_BACKEND", "stub").lower()
CORPUS_ROOT = os.environ.get("LEVYBOY_CORPUS", "")
AGENT_TIMEOUT_SECONDS = int(os.environ.get("LEVYBOY_AGENT_TIMEOUT", "120"))

EMPTY_PROMPT = (
    "Ask me something about the lab's code, notebooks or results "
    '(e.g. "how was figure 3 made?").'
)

HELP_TEXT = (
    "*LevyBoy* — the Levy Lab research assistant.\n\n"
    "Just ask. No commands to learn. I read the lab's actual files and work out "
    "what to look at.\n\n"
    "Things people ask:\n"
    "• `how was results/figure3_recurrence.png produced?`\n"
    "• `what normalization was applied?`\n"
    "• `open src/niche_discovery.py and explain what it does`\n"
    "• `what is Leiden clustering?`\n"
    "• `explain that more simply` (I remember the thread)\n\n"
    "Every answer lists the files it came from. If I answered from general "
    "knowledge instead of your files, I say so.\n\n"
    "`reset` clears this thread's memory. `help` shows this."
)

# What each tool is doing, in words a researcher would use. Shown live while the
# agent works: a minute of silence reads as broken, the same minute narrated
# reads as working.
_PROGRESS = {
    "search_lab_files": "searching the lab files",
    "read_file": "reading",
    "trace_pipeline": "tracing how it was produced",
    "list_files": "listing the corpus",
}


def describe_step(step) -> str:
    """One line describing a tool call, for the live status message."""
    phrase = _PROGRESS.get(step.tool, step.tool or "thinking")
    detail = (
        step.arguments.get("query")
        or step.arguments.get("path")
        or step.arguments.get("artifact")
        or step.arguments.get("pattern")
        or ""
    )
    detail = str(detail).strip()
    if not detail:
        return phrase
    if len(detail) > 60:
        detail = detail[:57] + "..."
    return f"{phrase} — `{detail}`"


def ask(question: str, history=None, on_progress=None) -> str:
    """A question in, an answer out. The only call Slack ever makes.

    `history` is the earlier turns of this Slack thread, so follow-ups like
    "explain that more simply" have something to refer to.

    `on_progress` is called with a human-readable string each time the agent
    takes an action, so the caller can show its working.
    """
    question = (question or "").strip()
    if not question:
        return EMPTY_PROMPT
    if question.lower() in {"help", "?", "commands"}:
        return HELP_TEXT

    if BACKEND != "rag":
        return _stub_answer(question)

    return _ask_agent(question, history=history, on_progress=on_progress)


def _ask_agent(question: str, history=None, on_progress=None) -> str:
    """Run the agent loop and render its result for Slack."""
    try:
        import lab_agent
    except Exception as exc:
        return (
            f":warning: I could not load the agent ({type(exc).__name__}: {exc}). "
            "Check that PYTHONPATH includes the pathology-agent rag directory."
        )

    if not CORPUS_ROOT:
        return (
            ":warning: LEVYBOY_CORPUS is not set, so I have no lab files to read. "
            "Set it to the corpus directory and restart me."
        )

    def relay(step):
        if on_progress is not None:
            on_progress(describe_step(step))

    # Bounded. Without a deadline a stalled model server leaves Slack showing
    # "thinking…" forever, which is exactly what a dropped Ollama connection
    # produced: no error, no timeout, no way to tell it had failed.
    import concurrent.futures as futures

    with futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lab_agent.run_agent,
            question,
            corpus_root=CORPUS_ROOT,
            history=history,
            on_step=relay,
        )
        try:
            result = future.result(timeout=AGENT_TIMEOUT_SECONDS)
        except futures.TimeoutError:
            return (
                f":hourglass: I am still working after {AGENT_TIMEOUT_SECONDS}s and "
                "stopped waiting. The local model is probably loading or under "
                "memory pressure. Try again in a moment."
            )
        except Exception as exc:
            return f":warning: I hit an error: {type(exc).__name__}: {exc}"

    return format_result(result)


# qwen3 is a reasoning model: it emits a thinking block before every answer.
# Ollama normally keeps that out of `content`, but it leaks when a run is cut
# short, and a wall of the model's private deliberation is not an answer.
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)
# Observed in live runs: the model wraps a citation in a pseudo-tag it invented
# (`<file>src/preprocess.py</file>`). Harmless, but it renders as literal angle
# brackets in Slack and looks like a bug in the bot.
_FILE_TAG = re.compile(r"</?(?:file|source|citation)>", re.IGNORECASE)


def clean_answer(text: str) -> str:
    """Strip model scaffolding that is not part of the answer."""
    text = _THINK_BLOCK.sub("", text or "")
    text = _UNCLOSED_THINK.sub("", text)
    text = _FILE_TAG.sub("", text)
    # Collapse the blank-line runs the substitutions leave behind.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def format_result(result) -> str:
    """Render an AgentResult for Slack, including where the answer came from.

    The provenance line is the point. An answer with files listed can be checked;
    an answer without them is the model talking. Both are legitimate here (a
    follow-up or a general-background question genuinely needs no file), so the
    line states which of the two happened rather than warning about it.

    Warnings are kept for things that actually went wrong. A warning that fires
    on correct behaviour gets ignored, and then the one that matters gets missed
    with it.
    """
    body = clean_answer(result.answer) or "(no answer produced)"
    lines = [body, ""]

    if result.sources:
        listed = ", ".join(f"`{s}`" for s in result.sources[:6])
        more = "" if len(result.sources) <= 6 else f" (+{len(result.sources) - 6} more)"
        lines.append(f"_Looked at:_ {listed}{more}")
    elif getattr(result, "asked_for_clarification", False):
        pass  # a question back is not an answer, so there is nothing to source
    elif not getattr(result, "used_no_tools", True):
        # Tools ran but turned up no file. That is a real search that came back
        # empty, which is a different thing from never looking, and calling it
        # "general background" would be a lie about a grounded answer.
        lines.append("_Searched your lab's files and found nothing on this._")
    elif getattr(result, "used_prior_context", False):
        lines.append("_Following up on the earlier answer in this thread._")
    else:
        lines.append("_General background, not from your lab's files._")

    # Genuine failures below this line.
    if getattr(result, "retrieval_failed", False):
        lines.append(
            "_:warning: search failed, so this answer did not use the file index._"
        )
    if result.hit_step_limit:
        lines.append("_:warning: I hit my step limit, so this may be incomplete._")
    if getattr(result, "model_error", None):
        lines.append(f"_:warning: model error during the run: {result.model_error}_")
    if getattr(result, "context_trimmed", 0):
        lines.append(
            "_:warning: this thread got long and I dropped the oldest turns to fit._"
        )
    return "\n".join(lines).rstrip()


def _stub_answer(question: str) -> str:
    """Canned reply so the Slack layer runs with no Ollama and no index."""
    return (
        f":robot_face: *(stub mode)* You asked: “{question}”\n"
        "I am not connected to the lab agent. Set LEVYBOY_BACKEND=rag with Ollama "
        "running and the corpus indexed to get real answers."
    )


def describe_backend() -> str:
    """Human-readable backend description, for logs and health checks."""
    if BACKEND != "rag":
        return "stub (no agent connected)"
    try:
        import lab_agent  # noqa: F401
    except Exception as exc:
        return f"rag (BROKEN: cannot import lab_agent: {type(exc).__name__})"
    corpus = CORPUS_ROOT or "UNSET"
    return f"rag (agent loop, corpus={corpus}, timeout={AGENT_TIMEOUT_SECONDS}s)"
