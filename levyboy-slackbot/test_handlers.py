"""Unit tests for the pure bot logic. Run: python -m pytest  (or python test_handlers.py)"""

import handlers


class FakeClient:
    def __init__(self):
        self.posted = []
        self.updated = []

    def chat_postMessage(self, channel, thread_ts=None, text=""):
        self.posted.append({"channel": channel, "thread_ts": thread_ts, "text": text})
        return {"ts": "1.0", "channel": channel}

    def chat_update(self, channel, ts, text=""):
        self.updated.append({"ts": ts, "text": text})
        return {"ts": ts}


def _ask(**kwargs):
    """Build a stand-in for agent.ask that tolerates the real keyword arguments."""
    reply = kwargs.pop("reply", "an answer")
    seen = kwargs.pop("seen", None)

    def fake(question, history=None, on_progress=None):
        if seen is not None:
            seen.append(history)
        return reply

    return fake


def test_strip_mention_removes_bot_id():
    assert handlers.strip_mention("<@U123ABC> where is the file?") == "where is the file?"


def test_strip_mention_handles_no_mention():
    assert handlers.strip_mention("just text") == "just text"


def test_strip_mention_empty():
    assert handlers.strip_mention("") == ""
    assert handlers.strip_mention(None) == ""


def test_answer_posts_placeholder_then_edits():
    c = FakeClient()
    result = handlers.answer(c, "C1", "10.0", "where is the QC notebook?")
    # posted a placeholder in the right thread…
    assert c.posted[0]["thread_ts"] == "10.0"
    assert c.posted[0]["text"] == handlers.PLACEHOLDER
    # …then edited that same message with the final answer.
    assert c.updated[-1]["text"] == result
    assert "QC notebook" in result


def test_answer_survives_agent_error(monkeypatch):
    def boom(question, history=None, on_progress=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(handlers.agent, "ask", boom)
    c = FakeClient()
    result = handlers.answer(c, "C1", "10.0", "anything")
    assert "Agent error" in result
    assert "boom" in result
    assert c.updated  # the placeholder still got edited, bot didn't crash


# --- live progress ------------------------------------------------------------
#
# The agent takes tens of seconds. A chat client showing nothing for that long
# reads as broken, which is most of what "it isn't working" turned out to mean.


def test_progress_updates_are_shown_while_the_agent_works(monkeypatch):
    def ask(question, history=None, on_progress=None):
        on_progress("searching the lab files — `normalization`")
        on_progress("reading — `src/preprocess.py`")
        return "final answer"

    monkeypatch.setattr(handlers.agent, "ask", ask)
    c = FakeClient()
    handlers.answer(c, "C1", "T1", "what normalization was applied?")

    # Two progress edits, then the answer. All on the same message.
    assert len(c.updated) == 3
    assert all(u["ts"] == "1.0" for u in c.updated)
    assert "searching the lab files" in c.updated[0]["text"]
    assert "src/preprocess.py" in c.updated[1]["text"]
    assert c.updated[-1]["text"] == "final answer"


def test_progress_failure_does_not_lose_the_answer(monkeypatch):
    """A rate-limited status edit must not cost us the reply."""

    class FlakyClient(FakeClient):
        def chat_update(self, channel, ts, text=""):
            if "working" in text:
                raise RuntimeError("rate limited")
            return super().chat_update(channel, ts, text)

    def ask(question, history=None, on_progress=None):
        on_progress("searching the lab files")
        return "final answer"

    monkeypatch.setattr(handlers.agent, "ask", ask)
    c = FlakyClient()
    result = handlers.answer(c, "C1", "T1", "anything")
    assert result == "final answer"
    assert c.updated[-1]["text"] == "final answer"


def test_progress_message_is_bounded(monkeypatch):
    def ask(question, history=None, on_progress=None):
        for i in range(12):
            on_progress(f"step {i}")
        return "done"

    monkeypatch.setattr(handlers.agent, "ask", ask)
    c = FakeClient()
    handlers.answer(c, "C1", "T1", "anything")
    last_progress = c.updated[-2]["text"]
    assert last_progress.count("•") == handlers.MAX_PROGRESS_LINES
    assert "step 11" in last_progress
    assert "step 0" not in last_progress


# --- conversation memory ------------------------------------------------------
#
# The bug these cover: every message was turn one, so "explain that without the
# jargon" reached the model with nothing for "that" to refer to, and it answered
# by describing itself.


def test_first_message_in_a_thread_has_no_history():
    handlers.forget_all()
    assert handlers.thread_history("T1") == []


def test_follow_up_receives_the_earlier_turns(monkeypatch):
    handlers.forget_all()
    seen = []
    monkeypatch.setattr(handlers.agent, "ask", _ask(seen=seen))
    c = FakeClient()
    handlers.answer(c, "C1", "T9", "how was figure 3 produced?")
    handlers.answer(c, "C1", "T9", "explain that without the jargon")

    assert seen[0] == []  # first turn: nothing to carry
    assert seen[1] == [
        {"role": "user", "content": "how was figure 3 produced?"},
        {"role": "assistant", "content": "an answer"},
    ]


def test_threads_do_not_leak_into_each_other(monkeypatch):
    handlers.forget_all()
    seen = []
    monkeypatch.setattr(handlers.agent, "ask", _ask(seen=seen, reply="A"))
    c = FakeClient()
    handlers.answer(c, "C1", "T1", "question in thread one")
    handlers.answer(c, "C1", "T2", "unrelated question in thread two")
    assert seen[1] == []  # a different thread starts clean


def test_history_is_capped(monkeypatch):
    """Every carried turn is re-read on every step of the agent loop, so an
    unbounded thread would get slower and slower until it hit the context limit."""
    handlers.forget_all()
    monkeypatch.setattr(handlers.agent, "ask", _ask(reply="A"))
    c = FakeClient()
    for i in range(10):
        handlers.answer(c, "C1", "T5", f"q{i}")
    history = handlers.thread_history("T5")
    assert len(history) == handlers.MAX_TURNS
    assert history[-1] == {"role": "assistant", "content": "A"}
    # oldest turns dropped, newest kept: 10 exchanges = 20 turns, capped at 12
    assert history[0]["content"] == "q4"


def test_long_turns_are_truncated(monkeypatch):
    """An unbounded turn is re-read on every step and can push the whole
    conversation out of the model's context window."""
    handlers.forget_all()
    monkeypatch.setattr(handlers.agent, "ask", _ask(reply="B" * 5000))
    c = FakeClient()
    handlers.answer(c, "C1", "T8", "A" * 5000)
    history = handlers.thread_history("T8")
    assert len(history[0]["content"]) == handlers.MAX_TURN_CHARS
    assert len(history[1]["content"]) == handlers.MAX_TURN_CHARS


def test_status_trailers_are_not_fed_back(monkeypatch):
    """"_Looked at:_ …" is for the human. Carrying it forward as conversation
    makes the model narrate its own diagnostics."""
    handlers.forget_all()
    monkeypatch.setattr(
        handlers.agent,
        "ask",
        _ask(reply="The real answer.\n\n_Looked at:_ `src/preprocess.py`"),
    )
    c = FakeClient()
    handlers.answer(c, "C1", "T6", "anything")
    assert handlers.thread_history("T6")[1] == {
        "role": "assistant",
        "content": "The real answer.",
    }


def test_errors_are_not_remembered(monkeypatch):
    handlers.forget_all()

    def boom(question, history=None, on_progress=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(handlers.agent, "ask", boom)
    c = FakeClient()
    handlers.answer(c, "C1", "T7", "anything")
    assert handlers.thread_history("T7") == []


def test_reset_clears_only_that_thread(monkeypatch):
    handlers.forget_all()
    monkeypatch.setattr(handlers.agent, "ask", _ask(reply="A"))
    c = FakeClient()
    handlers.answer(c, "C1", "T1", "first question")
    handlers.answer(c, "C1", "T2", "other thread")

    out = handlers.answer(c, "C1", "T1", "reset")
    assert "Cleared" in out
    assert handlers.thread_history("T1") == []
    assert handlers.thread_history("T2") != []


def test_thread_store_is_bounded(monkeypatch):
    handlers.forget_all()
    monkeypatch.setattr(handlers.agent, "ask", _ask(reply="A"))
    c = FakeClient()
    for i in range(handlers.MAX_THREADS + 25):
        handlers.answer(c, "C1", f"T{i}", "q")
    assert len(handlers._threads) == handlers.MAX_THREADS
    assert handlers.thread_history("T0") == []  # oldest evicted


def test_mention_reuses_existing_thread():
    c = FakeClient()
    event = {"channel": "C1", "ts": "20.0", "thread_ts": "15.0", "text": "<@U1> hi"}
    handlers.handle_mention_event(event, c)
    assert c.posted[0]["thread_ts"] == "15.0"  # stayed in the existing thread


def test_dm_ignores_bot_messages():
    c = FakeClient()
    assert handlers.handle_dm_event({"channel_type": "im", "bot_id": "B1", "text": "x"}, c) is None
    assert c.posted == []


def test_dm_ignores_non_im():
    c = FakeClient()
    assert handlers.handle_dm_event({"channel_type": "channel", "text": "x"}, c) is None


def test_dm_answers_real_user():
    c = FakeClient()
    event = {"channel_type": "im", "channel": "D1", "ts": "30.0", "text": "where is X?"}
    handlers.handle_dm_event(event, c)
    assert len(c.posted) == 1 and len(c.updated) == 1


# =============================================================================
# The agent seam: one path, no prefixes, honest about where an answer came from
# =============================================================================

import os  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, "/Users/avilash/pathology-agent/rag")
import agent as agent_mod  # noqa: E402


def _reload(**env):
    import importlib

    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(agent_mod)
    return agent_mod


class FakeResult:
    """Stand-in for lab_agent.AgentResult."""

    def __init__(self, **kw):
        self.answer = kw.get("answer", "the answer")
        self.sources = kw.get("sources", [])
        self.hit_step_limit = kw.get("hit_step_limit", False)
        self.used_no_tools = kw.get("used_no_tools", False)
        self.used_prior_context = kw.get("used_prior_context", False)
        self.asked_for_clarification = kw.get("asked_for_clarification", False)
        self.retrieval_failed = kw.get("retrieval_failed", False)
        self.model_error = kw.get("model_error", None)
        self.context_trimmed = kw.get("context_trimmed", 0)


def test_help_needs_no_model_and_teaches_no_syntax():
    text = agent_mod.ask("help")
    assert "LevyBoy" in text
    assert "Just ask" in text
    # The prefix router is gone. Help must not teach commands that don't exist.
    for gone in ("fast:", "trace:", "deep:"):
        assert gone not in text


def test_empty_question_prompts_rather_than_erroring():
    assert "Ask me something" in agent_mod.ask("")


def test_every_question_goes_to_the_agent():
    """One path. The agent decides which tools a question needs, rather than the
    person having to classify their own question before asking it."""
    mod = _reload(
        LEVYBOY_BACKEND="rag",
        LEVYBOY_CORPUS="/Users/avilash/pathology-agent/demo/corpus",
    )
    asked = []
    mod._ask_agent = lambda q, history=None, on_progress=None: asked.append(q) or "A"

    for question in (
        "what normalization was applied?",
        "how was results/figure3_recurrence.png produced?",
        "what is Leiden clustering?",
        "explain that more simply",
        "trace: results/figure3_recurrence.png",
    ):
        mod.ask(question)

    assert len(asked) == 5
    # Old prefixes are no longer magic: they reach the agent verbatim.
    assert asked[-1] == "trace: results/figure3_recurrence.png"


def test_history_and_progress_reach_the_agent():
    mod = _reload(
        LEVYBOY_BACKEND="rag",
        LEVYBOY_CORPUS="/Users/avilash/pathology-agent/demo/corpus",
    )
    captured = {}

    def fake(question, history=None, on_progress=None):
        captured.update(question=question, history=history, on_progress=on_progress)
        return "A"

    mod._ask_agent = fake
    marker = object()
    mod.ask("a question", history=[{"role": "user", "content": "earlier"}], on_progress=marker)
    assert captured["history"] == [{"role": "user", "content": "earlier"}]
    assert captured["on_progress"] is marker


def test_missing_corpus_is_reported_not_hidden():
    mod = _reload(LEVYBOY_BACKEND="rag", LEVYBOY_CORPUS=None)
    out = mod.ask("what normalization was applied?")
    assert "LEVYBOY_CORPUS" in out


def test_stub_backend_still_works_without_any_corpus():
    mod = _reload(LEVYBOY_BACKEND="stub", LEVYBOY_CORPUS=None)
    assert "stub" in mod.ask("anything").lower()


# --- where did this answer come from? ----------------------------------------
#
# The whole point. An answer with files listed can be checked. An answer without
# them is the model talking. Both are legitimate, so the line says which
# happened rather than warning about it.


def test_answers_from_files_list_the_files():
    out = agent_mod.format_result(
        FakeResult(sources=["src/preprocess.py", "config/pipeline.yaml"])
    )
    assert "_Looked at:_" in out
    assert "`src/preprocess.py`" in out
    assert ":warning:" not in out


def test_answers_with_no_files_say_so():
    out = agent_mod.format_result(FakeResult(sources=[], used_no_tools=True))
    assert "General background, not from your lab's files" in out


def test_follow_ups_are_labelled_as_follow_ups():
    out = agent_mod.format_result(
        FakeResult(sources=[], used_no_tools=True, used_prior_context=True)
    )
    assert "Following up" in out
    assert "General background" not in out


def test_a_clarifying_question_gets_no_provenance_line():
    """Asking what the user meant is not an answer, so there is nothing to
    source, and labelling it would be noise."""
    out = agent_mod.format_result(
        FakeResult(
            answer="Which file do you mean?",
            sources=[],
            used_no_tools=True,
            asked_for_clarification=True,
        )
    )
    assert "General background" not in out
    assert "Looked at" not in out


def test_source_list_is_capped():
    out = agent_mod.format_result(FakeResult(sources=[f"f{i}.py" for i in range(9)]))
    assert "+3 more" in out


def test_real_failures_still_warn():
    assert ":warning:" in agent_mod.format_result(FakeResult(retrieval_failed=True))
    assert ":warning:" in agent_mod.format_result(FakeResult(hit_step_limit=True))
    assert ":warning:" in agent_mod.format_result(FakeResult(model_error="boom"))
    assert ":warning:" in agent_mod.format_result(FakeResult(context_trimmed=3))


def test_progress_lines_are_human_readable():
    class Step:
        def __init__(self, tool, arguments):
            self.tool = tool
            self.arguments = arguments

    assert "searching the lab files" in agent_mod.describe_step(
        Step("search_lab_files", {"query": "normalization"})
    )
    assert "`src/preprocess.py`" in agent_mod.describe_step(
        Step("read_file", {"path": "src/preprocess.py"})
    )
    assert "tracing" in agent_mod.describe_step(
        Step("trace_pipeline", {"artifact": "results/fig3.png"})
    )
    # Long arguments are truncated so the status line stays one line.
    long = agent_mod.describe_step(Step("search_lab_files", {"query": "x" * 200}))
    assert len(long) < 100


if __name__ == "__main__":
    # Minimal runner so it works even without pytest installed.
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            if "monkeypatch" in fn.__code__.co_varnames:
                continue  # needs pytest; skip in the no-dep runner
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed (monkeypatch tests run under pytest)")


def test_a_search_that_found_nothing_is_not_called_general_background():
    """Tools ran and came back empty. That is a real search with a real result,
    and mislabelling it as unsourced would misrepresent a grounded answer."""
    out = agent_mod.format_result(
        FakeResult(sources=[], used_no_tools=False, used_prior_context=False)
    )
    assert "Searched your lab's files and found nothing" in out
    assert "General background" not in out


# --- model scaffolding is not part of the answer ------------------------------


def test_invented_citation_tags_are_stripped():
    """Seen in a live run: the model wrapped a citation in a tag it made up.
    Slack renders that as literal angle brackets, which reads as a bug."""
    out = agent_mod.clean_answer("Normalization is log1p.\n\n<file>src/preprocess.py</file>")
    assert "<file>" not in out and "</file>" not in out
    assert "src/preprocess.py" in out


def test_leaked_thinking_blocks_are_removed():
    """qwen3 thinks before every answer. That block is not an answer."""
    out = agent_mod.clean_answer("<think>I should search for this</think>The answer.")
    assert out == "The answer."
    # An unterminated block (a run cut short) must not dump the rest either.
    assert agent_mod.clean_answer("Real answer.\n<think>and then I") == "Real answer."


def test_clean_answer_leaves_normal_text_alone():
    text = "Leiden resolution is 0.7, set in `config/pipeline.yaml`."
    assert agent_mod.clean_answer(text) == text
