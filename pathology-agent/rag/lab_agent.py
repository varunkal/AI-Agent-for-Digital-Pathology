"""
lab_agent.py — the agent loop that connects the model to the lab's knowledge.

WHY THIS EXISTS
---------------
Pitch deck Aim 1: "Connect the agent to our Levy Lab context (code, notebooks,
metadata, project files)."

Until now the project had two halves that never met:
  - the SEARCH answers a question but cannot act
  - the AGENT runs code but cannot search the lab's knowledge

This module joins them. The model is given tools — search, read, list, and
(optionally) execute — decides which to call, sees the results, and continues
until it can answer. That is the difference between a question-answering box and
something that can work through a problem.

MODEL COMPATIBILITY — A REAL CONSTRAINT
---------------------------------------
Not every local model can call tools. qwen2.5-coder:3b emits a JSON blob as plain
TEXT instead of populating the tool-call field, so a loop that trusts the API
field alone silently does nothing. This reproduces, independently, the finding
recorded in the project's own build log: Qwen2.5-Coder was rejected because it
"emitted JSON instead of executing".

Rather than depend on one model behaving well, the loop accepts BOTH: native tool
calls when the model supports them, and a parsed JSON fallback when it does not.
Which path was used is recorded on every step, because "the model claimed to call
a tool but didn't really" is exactly the kind of detail that quietly invalidates
an evaluation.

SAFETY
------
Read-only by default. `allow_execution=False` means the run_python tool is not
even offered to the model. File reads go through safety.PathGuard, so the same
allowlist and symlink protections apply here as everywhere else. Every step is
recorded in a trace: what was called, with what arguments, and what came back.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

MAX_STEPS = 8
MAX_TOOL_OUTPUT = 6000

# A model that cannot call tools will still answer — from memory, confidently,
# about files it never opened. That failure is invisible unless checked, so the
# loop checks before running rather than after.
DEFAULT_AGENT_MODEL = "qwen3:4b"


def model_supports_tools(model: str) -> Optional[bool]:
    """Does this model actually support tool calling? None if undeterminable.

    `ollama show` lists capabilities. qwen2.5-coder does NOT include "tools": it
    prints JSON describing a call instead of making one, so the loop silently
    performs no actions and the model answers from memory. Checking up front
    turns a silent wrong answer into a loud refusal.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["ollama", "show", model], capture_output=True, text=True, timeout=15
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    text = out.stdout.lower()
    if "capabilities" not in text:
        return None
    section = text.split("capabilities", 1)[1]
    return "tools" in section.split("system")[0]


# The prompt IS the behaviour. Earlier versions told the model to search or else,
# which made it a search box: it re-searched on every follow-up, tried to search
# for "explain that", and had no way to answer "what is Leiden clustering"
# except by pretending the answer came from a lab file.
#
# This version names the kinds of question it actually gets and says what to do
# with each. The ordering matters: file questions first (the common case and the
# one worth getting right), vague-question handling last (the rare exception),
# so the model does not reach for clarification as a default.
SYSTEM_PROMPT = """You are LevyBoy, the Levy Lab's research assistant at Dartmouth. The lab
does digital pathology: spatial transcriptomics, tissue imaging, and the code
and notebooks around them.

You have tools that read the lab's real files. Use them whenever the question is
about this lab's own work: its code, its data, its figures, its parameters, or
how something was done. Never answer a question about their files from memory.
Name the files you used.

Handle each kind of question the way it deserves:

QUESTIONS ABOUT THEIR FILES. Search, read whatever looks relevant, then answer.
If the question names any subject at all, a file, a step, a method, a parameter,
"normalization", "QC", "the markers", that is enough to search for. Do not ask
the user to narrow it down first.

HOW SOMETHING WAS PRODUCED. Use trace_pipeline on the output file. It returns
the real chain of scripts and notebooks, computed from the files themselves.

FOLLOW-UPS. When the user is reacting to what you just said, "explain that more
simply", "why does that matter", "what about the QC step", answer from the
conversation you already had. You do not need to search again for something you
already established. Search again only if they have asked something genuinely
new.

GENERAL BACKGROUND. Questions like "what is Leiden clustering" or "how does a
Cox model work" are not about their files. Answer from what you know and say
plainly that this is general background rather than something from their files.
Do not search for these.

THINGS NOBODY WROTE DOWN. Some things are genuinely not recorded: why a
parameter was chosen, how many patients are in a cohort, what someone plans to
do next. Search first. If it is not there, say so plainly. "That is not written
down in these files" is a correct and useful answer. Never fill the gap with a
plausible guess.

TOO VAGUE TO ACT ON. Only when a question has no subject at all and nothing
earlier in the conversation to attach it to ("explain that", said out of
nowhere), ask which thing they mean, in one short question. Do not describe
yourself and do not list what you can do. Nobody asked.

Write plainly, for a researcher who does not know your internals. Be brief.
"""


# --- Trace -------------------------------------------------------------------


@dataclass
class Step:
    """One action in the loop. The trace is what makes behaviour auditable."""

    index: int
    tool: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    output: str = ""
    call_style: Optional[str] = None      # "native" | "parsed_text" | None
    error: Optional[str] = None
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "tool": self.tool,
            "arguments": self.arguments,
            "output": self.output[:1000],
            "call_style": self.call_style,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
        }


@dataclass
class AgentResult:
    question: str
    answer: str
    steps: List[Step] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    latency_s: float = 0.0
    hit_step_limit: bool = False
    used_no_tools: bool = False
    used_prior_context: bool = False
    asked_for_clarification: bool = False
    retrieval_failed: bool = False
    retrieval_error: Optional[str] = None
    model_error: Optional[str] = None
    #: Turns shed to stay inside the model's context window. Non-zero means the
    #: model could not see the whole conversation when it answered.
    context_trimmed: int = 0

    @property
    def tools_used(self) -> List[str]:
        return [s.tool for s in self.steps if s.tool]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources,
            "steps": [s.to_dict() for s in self.steps],
            "tools_used": self.tools_used,
            "n_steps": len(self.steps),
            "hit_step_limit": self.hit_step_limit,
            "used_no_tools": self.used_no_tools,
            "used_prior_context": self.used_prior_context,
            "asked_for_clarification": self.asked_for_clarification,
            "retrieval_failed": self.retrieval_failed,
            "retrieval_error": self.retrieval_error,
            "model_error": self.model_error,
            "context_trimmed": self.context_trimmed,
            "latency_s": round(self.latency_s, 3),
        }


# --- Tool definitions --------------------------------------------------------


def tool_schemas(allow_execution: bool = False) -> List[dict]:
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "search_lab_files",
                "description": (
                    "Semantic search across the lab's indexed notebooks, scripts and "
                    "documentation. Returns matching passages with their file paths. "
                    "Use this first for any question about where something is or how "
                    "something was done."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to look for, in natural language.",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read a lab file in full, given its path relative to the corpus "
                    "root. Use after search when a passage is not enough."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative file path."}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "trace_pipeline",
                "description": (
                    "Given an output artifact (a figure, a results file), return the "
                    "chain of scripts and notebooks that produced it, with the exact "
                    "line of code for each step. Computed from real file references, "
                    "not inferred — use this for any 'how was X produced', 'what "
                    "depends on X', or 'how do I regenerate X' question."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "artifact": {
                            "type": "string",
                            "description": "Path of the output file, e.g. results/figure3.png",
                        }
                    },
                    "required": ["artifact"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List the files available in the lab corpus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Optional substring filter, e.g. 'notebooks'.",
                        }
                    },
                },
            },
        },
    ]
    if allow_execution:
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": "run_python",
                    "description": (
                        "Run a short Python snippet in an isolated scratch directory. "
                        "Cannot modify lab files. Use only for small checks or "
                        "calculations."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Python source."}
                        },
                        "required": ["code"],
                    },
                },
            }
        )
    return schemas


# --- Tool implementations ----------------------------------------------------


class LabTools:
    """The tools, bound to a corpus and the safety guard."""

    def __init__(
        self,
        corpus_root: str,
        *,
        retrieve_fn: Optional[Callable] = None,
        scratch_dir: Optional[str] = None,
        allow_execution: bool = False,
        top_k: int = 5,
    ) -> None:
        self.corpus_root = os.path.abspath(corpus_root)
        self.retrieve_fn = retrieve_fn
        self.allow_execution = allow_execution
        self.top_k = top_k
        self.scratch_dir = scratch_dir
        self.sources_seen: List[str] = []
        self.retrieval_failed = False
        self.retrieval_error: Optional[str] = None

        import safety

        self.guard = safety.PathGuard(
            read_roots=[self.corpus_root],
            write_root=scratch_dir if allow_execution else None,
        )

    # -- individual tools --

    def search_lab_files(self, query: str) -> str:
        try:
            if self.retrieve_fn is None:
                import lab_query

                chunks = lab_query.retrieve(query, top_k=self.top_k)
            else:
                chunks = self.retrieve_fn(query)
        except Exception as exc:
            # A missing or empty index otherwise surfaces as a raw ChromaDB
            # error inside the loop, where the model sees it as a tool result
            # and tries to reason about a stack trace.
            #
            # Flagged as well as reported: the model will happily fall back to
            # list_files or to memory and produce a confident answer, and
            # used_no_tools stays False because a tool WAS called. A dead index
            # would otherwise look like a working demo.
            self.retrieval_failed = True
            self.retrieval_error = f"{type(exc).__name__}: {exc}"
            return (
                f"Search is unavailable ({type(exc).__name__}). The corpus may not "
                "be indexed yet — run `python lab_rag.py index <directory>` first. "
                "Use list_files and read_file instead."
            )
        if not chunks:
            return "No matching passages found."
        lines = []
        for chunk in chunks:
            source = getattr(chunk, "source", "<unknown>")
            if source not in self.sources_seen:
                self.sources_seen.append(source)
            text = getattr(chunk, "text", "")
            lines.append(f"--- {source} ---\n{text[:900]}")
        return "\n\n".join(lines)

    def trace_pipeline(self, artifact: str) -> str:
        """Deterministic dependency chain. The agent calls this rather than
        guessing a pipeline from retrieved snippets — the structure comes from
        real file references, so it cannot be fabricated."""
        try:
            import workflow
        except Exception as exc:
            return f"Pipeline tracing unavailable: {type(exc).__name__}: {exc}"

        traced = workflow.trace(self.corpus_root, artifact)
        for step in traced.steps:
            if step.source_file not in self.sources_seen:
                self.sources_seen.append(step.source_file)
        return workflow.render_structure(traced)

    def read_file(self, path: str) -> str:
        candidate = path if os.path.isabs(path) else os.path.join(self.corpus_root, path)
        try:
            text = self.guard.read_text(candidate)
        except Exception as exc:
            return f"Could not read {path!r}: {type(exc).__name__}: {exc}"
        normalized = os.path.relpath(os.path.realpath(candidate), self.corpus_root)
        if normalized not in self.sources_seen:
            self.sources_seen.append(normalized)
        return text[:MAX_TOOL_OUTPUT]

    def list_files(self, pattern: str = "") -> str:
        found = []
        for dirpath, dirnames, filenames in self.guard.walk_readable():
            for name in filenames:
                rel = os.path.relpath(
                    os.path.join(dirpath, name), self.corpus_root
                ).replace(os.sep, "/")
                if not pattern or pattern.lower() in rel.lower():
                    found.append(rel)
        return "\n".join(sorted(found)) if found else "No files matched."

    def run_python(self, code: str) -> str:
        if not self.allow_execution:
            return "Code execution is disabled for this session."
        import safe_exec

        result = safe_exec.run_python(
            code,
            scratch_dir=self.scratch_dir or "/tmp/lab_agent_scratch",
            protected_roots=[self.corpus_root],
        )
        if result.refused:
            return f"Refused: {result.refused}"
        parts = []
        if result.stdout:
            parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr}")
        if result.timed_out:
            parts.append("(timed out)")
        return "\n".join(parts) or "(no output)"

    def dispatch(self, name: str, arguments: Dict[str, Any]) -> str:
        handler = {
            "search_lab_files": lambda: self.search_lab_files(arguments.get("query", "")),
            "read_file": lambda: self.read_file(arguments.get("path", "")),
            "trace_pipeline": lambda: self.trace_pipeline(arguments.get("artifact", "")),
            "list_files": lambda: self.list_files(arguments.get("pattern", "") or ""),
            "run_python": lambda: self.run_python(arguments.get("code", "")),
        }.get(name)
        if handler is None:
            return f"Unknown tool {name!r}."
        return handler()


# --- Fallback parsing --------------------------------------------------------

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{[^{}]*\"(?:name|tool)\"\s*:.*?\})", re.DOTALL)

KNOWN_TOOLS = {"search_lab_files", "read_file", "trace_pipeline", "list_files", "run_python"}


#: A reply this short containing a question mark is the model asking rather than
#: answering. Deliberately tight — a real answer that happens to contain "?"
#: would have to also be under two lines to be misread, and such a reply makes no
#: factual claim to be wrong about.
#:
#: This used to require the reply to END in "?", which missed the most common
#: shape the model actually produces: "Which part do you want me to explain?
#: Please specify what you're referring to." Observed live. The consequence was
#: a correct clarification being labelled as an answer from general knowledge.
_CLARIFICATION_MAX_CHARS = 200


def is_clarifying_question(answer: str) -> bool:
    """Did the model ask what the user meant instead of answering?

    Worth distinguishing because "no tools were called" is a warning about
    answering from model memory, and asking for clarification is the opposite of
    that failure — it is the model correctly declining to guess. Flagging it the
    same way trains people to ignore the warning.
    """
    stripped = (answer or "").strip()
    if "?" not in stripped or len(stripped) > _CLARIFICATION_MAX_CHARS:
        return False
    return len(stripped.splitlines()) <= 2


def parse_text_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Recover a tool call a model emitted as plain text instead of a real call.

    Some local models describe the call in prose or JSON rather than populating
    the API's tool-call field. Without this the loop silently does nothing and
    the model looks incapable when it is merely non-compliant.

    Deliberately conservative: a schema echo (arguments whose values are type
    descriptors like {"type": "string"}) is NOT a call — that is the model
    repeating the tool definition back, which is a different failure and must not
    be mistaken for intent.
    """
    if not text:
        return None
    candidates = _JSON_BLOCK.findall(text) + _BARE_JSON.findall(text)
    for blob in candidates:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        name = parsed.get("name") or parsed.get("tool")
        if name not in KNOWN_TOOLS:
            continue
        arguments = parsed.get("arguments") or parsed.get("parameters") or {}
        if not isinstance(arguments, dict):
            continue
        # Reject schema echoes.
        cleaned = {}
        for key, value in arguments.items():
            if isinstance(value, dict) and set(value) & {"type", "description"}:
                continue
            cleaned[key] = value
        if not cleaned:
            continue
        return {"name": name, "arguments": cleaned}
    return None


# --- Context budget ----------------------------------------------------------

# num_ctx is 8192 tokens (provenance.SAMPLING_OPTIONS). Ollama does not error
# when a prompt exceeds it, it silently drops the oldest tokens, which takes the
# system prompt with them. The model then stops calling tools and starts
# free-associating, and nothing anywhere reports a problem.
#
# That is reachable in normal use: a long thread plus several tool results, each
# up to MAX_TOOL_OUTPUT characters, adds up fast. So the loop trims on purpose
# instead of letting the runtime do it silently.
#
# ~3.5 characters per token, leaving room for the reply and for qwen3's thinking
# block, which it emits before every answer.
CONTEXT_CHAR_BUDGET = 20000


def trim_messages(messages: List[Dict[str, Any]], budget: int = CONTEXT_CHAR_BUDGET):
    """Drop the oldest middle turns until the conversation fits the window.

    Keeps the system prompt (it is the behaviour) and the most recent turns (they
    are the live task), and sheds what is between. Returns the kept messages and
    how many were dropped.

    A `tool` message is never left as the first kept message: it would reference
    an assistant tool call that is no longer present, which some servers reject
    and every model finds confusing.
    """
    if not messages:
        return messages, 0

    system, rest = messages[:1], messages[1:]
    used = len(str(system[0].get("content", "")))

    kept: List[Dict[str, Any]] = []
    for message in reversed(rest):
        size = len(str(message.get("content", ""))) + 200  # 200 for role/tool_call overhead
        if kept and used + size > budget:
            break
        used += size
        kept.append(message)
    kept.reverse()

    while kept and kept[0].get("role") == "tool":
        kept.pop(0)

    return system + kept, len(rest) - len(kept)


# --- The loop ----------------------------------------------------------------


def run_agent(
    question: str,
    *,
    corpus_root: str,
    model: Optional[str] = None,
    chat_fn: Optional[Callable] = None,
    tools: Optional[LabTools] = None,
    allow_execution: bool = False,
    max_steps: int = MAX_STEPS,
    scratch_dir: Optional[str] = None,
    history: Optional[Sequence[Dict[str, str]]] = None,
    on_step: Optional[Callable[[Step], None]] = None,
) -> AgentResult:
    """Run the tool-using loop until the model answers or hits the step limit.

    `history` is prior turns of the same conversation, oldest first, as
    {"role": "user"|"assistant", "content": ...}. Without it every question is
    turn one: a follow-up like "explain that more simply" has no referent, and
    the model answers about something else entirely — usually itself.

    `on_step` is called with each completed Step as it happens. The loop takes
    tens of seconds and a chat client showing nothing for that long reads as
    broken, so the caller needs to be able to say what is going on while it runs.
    A failing callback must never take the run down with it, so it is guarded.
    """
    started = time.monotonic()
    tools = tools or LabTools(
        corpus_root,
        scratch_dir=scratch_dir,
        allow_execution=allow_execution,
    )
    schemas = tool_schemas(allow_execution=allow_execution)

    if chat_fn is None:
        # Single source of truth: lab_rag.CHAT_MODEL, read through lab_query.config().
        # A separate default here would mean two places to change when moving to
        # the cluster, and the agent silently running a different model than the
        # rest of the system.
        if model:
            chosen = model
        else:
            try:
                import lab_query

                chosen = str(lab_query.config()["CHAT_MODEL"])
            except Exception:
                chosen = DEFAULT_AGENT_MODEL
        supports = model_supports_tools(chosen)
        if supports is False:
            raise RuntimeError(
                f"Model {chosen!r} does not support tool calling. It will answer "
                "from memory without opening a single file, which looks like a "
                "working agent and is not. Use a tool-capable model "
                f"(default: {DEFAULT_AGENT_MODEL})."
            )
        if supports is None:
            # Usually means the model is not pulled, so `ollama show` failed.
            # Continuing gets a 404 several seconds later from inside the loop,
            # which reads as an agent failure rather than a missing model.
            raise RuntimeError(
                f"Cannot determine whether {chosen!r} supports tool calling — it "
                "is probably not installed. Run `ollama list` to check, then "
                f"`ollama pull {chosen}`. Refusing to run a model whose "
                "capabilities are unknown."
            )

        def chat_fn(messages, tool_schemas_):       # noqa: ANN001
            import ollama

            import provenance

            return ollama.chat(
                model=chosen,
                messages=messages,
                tools=tool_schemas_,
                options=dict(provenance.SAMPLING_OPTIONS),
            )

    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Prior turns go between the system prompt and the new question, so the model
    # reads them as conversation rather than as instructions. Only role+content
    # are carried: replaying old tool_calls would invite the model to treat stale
    # tool output as fresh.
    for turn in history or []:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    had_history = len(messages) > 2
    steps: List[Step] = []
    answer = ""
    hit_limit = True
    dropped_total = 0

    def notify(step: Step) -> None:
        """Report progress. A broken callback must not kill a working run."""
        if on_step is None:
            return
        try:
            on_step(step)
        except Exception:
            pass

    for index in range(max_steps):
        step_started = time.monotonic()
        messages, dropped = trim_messages(messages)
        dropped_total += dropped
        try:
            response = chat_fn(messages, schemas)
        except Exception as exc:
            # The model server can drop a connection mid-request — Ollama does
            # this when it is swapping models under memory pressure
            # (httpx.RemoteProtocolError: Server disconnected). Left unhandled,
            # this propagated out and killed the run: the CLI died silently and
            # Slack sat on "thinking…" forever with no error and no timeout.
            #
            # Now it ends the run with an explicit failure the caller can show.
            steps.append(
                Step(
                    index=index,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_s=time.monotonic() - step_started,
                )
            )
            answer = (
                f"The model became unavailable partway through "
                f"({type(exc).__name__}). This is usually the local model server "
                "restarting or running out of memory — check `ollama ps` and try "
                "again."
            )
            hit_limit = False
            break
        message = response["message"] if isinstance(response, dict) else response.message
        content = (message.get("content") if isinstance(message, dict) else message.content) or ""
        native_calls = (
            message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
        )

        call, style = None, None
        if native_calls:
            first = native_calls[0]
            function = first["function"] if isinstance(first, dict) else first.function
            name = function["name"] if isinstance(function, dict) else function.name
            raw_args = function["arguments"] if isinstance(function, dict) else function.arguments
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}
            call, style = {"name": name, "arguments": raw_args or {}}, "native"
        else:
            recovered = parse_text_tool_call(content)
            if recovered:
                call, style = recovered, "parsed_text"

        if call is None:
            answer = content.strip()
            hit_limit = False
            if answer:
                steps.append(
                    Step(index=index, output=answer[:500],
                         duration_s=time.monotonic() - step_started)
                )
            break

        output = tools.dispatch(call["name"], call["arguments"])
        step = Step(
            index=index,
            tool=call["name"],
            arguments=call["arguments"],
            output=output,
            call_style=style,
            duration_s=time.monotonic() - step_started,
        )
        steps.append(step)
        notify(step)
        # Feed the exchange back in the shape the API expects: the assistant's
        # message WITH its tool_calls intact, then the result as a `tool` message.
        #
        # Previously both were appended as plain assistant/user text, which drops
        # the tool_calls field. The model then sees a history where it apparently
        # said nothing and a user pasted some output, so it re-reasons from
        # scratch every turn — the direct cause of multi-minute runs.
        if style == "native" and native_calls:
            assistant_message: Dict[str, Any] = {
                "role": "assistant",
                "content": content or "",
                "tool_calls": native_calls,
            }
            messages.append(assistant_message)
            messages.append(
                {
                    "role": "tool",
                    "tool_name": call["name"],
                    "content": output[:MAX_TOOL_OUTPUT],
                }
            )
        else:
            # Recovered from text: there is no tool_call id to reference, so the
            # plain-text form is the only option.
            messages.append({"role": "assistant", "content": content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": f"Result of {call['name']}:\n{output[:MAX_TOOL_OUTPUT]}",
                }
            )

    result = AgentResult(
        question=question,
        answer=answer,
        steps=steps,
        sources=list(tools.sources_seen),
        latency_s=time.monotonic() - started,
        hit_step_limit=hit_limit,
        context_trimmed=dropped_total,
    )
    # Answering with no tool calls means the answer came from model memory, not
    # from the lab's files. That is the exact failure this project exists to
    # avoid, so it is surfaced rather than left for the reader to notice.
    result.used_no_tools = not result.tools_used
    # Answering a follow-up ("say that more simply") from the conversation is
    # legitimate — the facts were established by tools on an earlier turn. That
    # is a different thing from answering a fresh question out of model memory,
    # and conflating them would train people to ignore the warning.
    result.used_prior_context = had_history
    result.asked_for_clarification = result.used_no_tools and is_clarifying_question(
        answer
    )
    result.model_error = next(
        (step.error for step in steps if step.error), None
    )
    result.retrieval_failed = getattr(tools, "retrieval_failed", False)
    result.retrieval_error = getattr(tools, "retrieval_error", None)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print('Usage: python lab_agent.py <corpus_dir> "<question>" [--execute]')
        raise SystemExit(1)

    corpus = sys.argv[1]
    question = " ".join(a for a in sys.argv[2:] if not a.startswith("--"))
    allow_exec = "--execute" in sys.argv

    print(f"\nQ: {question}\n")
    outcome = run_agent(
        question,
        corpus_root=corpus,
        allow_execution=allow_exec,
        scratch_dir="/tmp/lab_agent_scratch",
    )

    print("Steps the agent took:")
    for step in outcome.steps:
        if step.tool:
            args = ", ".join(f"{k}={v!r}" for k, v in step.arguments.items())
            print(f"  {step.index}. {step.tool}({args})   [{step.call_style}]")
    if outcome.used_no_tools:
        print("  (none — the model answered WITHOUT opening any file)")
    print(f"\nFiles it looked at: {', '.join(outcome.sources) or 'none'}")
    if outcome.retrieval_failed:
        print(f"\n!! WARNING: SEARCH FAILED ({outcome.retrieval_error}).")
        print("   Any answer above came from directory listings or model memory,")
        print("   not from retrieval. The index is probably missing or empty.")
    if outcome.used_no_tools:
        print("\n!! WARNING: no tools were called. This answer came from the "
              "model's memory,\n   not from the lab's files, and should not be "
              "trusted.")
    print(f"Took {outcome.latency_s:.0f}s over {len(outcome.steps)} step(s)")
    print(f"\nANSWER:\n{outcome.answer}\n")
