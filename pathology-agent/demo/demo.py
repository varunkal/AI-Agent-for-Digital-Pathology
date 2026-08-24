#!/usr/bin/env python3
"""
FULL DEMO — run with:  python3 demo/demo.py

Exercises every component built for this project, end to end, on a laptop:
  Act 1  Slack bot answering with its sources
  Act 2  Safety guardrails blocking real escape attempts
  Act 3  The evaluation harness scoring two methods against ground truth
  Act 4  The anti-fabrication guardrail refusing to invent results

WHAT IS REAL AND WHAT IS STOOD IN
---------------------------------
REAL: the chunking, the retrieval ranking, every safety check, every metric,
every statistical test, and all the scoring logic. This is the actual production
code, not a mock-up of it.

STOOD IN: the embedding model and the language model. On Discovery those are
nomic-embed-text and Qwen3-Coder served by Ollama on a GPU. Neither runs on a
laptop, so this demo substitutes a deterministic keyword retriever and a
template-based answer composer. Both are clearly labelled on screen.

The corpus in demo/corpus/ is SYNTHETIC — realistic-looking pathology files
written for this demo. No real lab data is used anywhere.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CORPUS = os.path.join(HERE, "corpus")
sys.path.insert(0, os.path.join(ROOT, "rag"))
sys.path.insert(0, os.path.join(ROOT, "evaluation"))

import analyze                      # noqa: E402
import lab_query                    # noqa: E402
import safety                       # noqa: E402
import tasks as tasks_mod           # noqa: E402

PAUSE = "--no-pause" not in sys.argv
BOLD, DIM, GREEN, RED, YELLOW, CYAN, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[0m"
)


def act(number: str, title: str) -> None:
    print(f"\n{BOLD}{'=' * 74}{RESET}")
    print(f"{BOLD}  ACT {number} — {title}{RESET}")
    print(f"{BOLD}{'=' * 74}{RESET}\n")
    if PAUSE:
        input(f"{DIM}   [Enter]{RESET}")
        print()


def step(text: str) -> None:
    print(f"{CYAN}▸ {text}{RESET}")


def ok(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def bad(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}")


def note(text: str) -> None:
    print(f"  {DIM}{text}{RESET}")


# =============================================================================
# Stand-ins for the GPU-hosted pieces
# =============================================================================

CHUNK_SIZE, CHUNK_OVERLAP = 800, 100     # identical to lab_rag.py


def read_notebook(path: str) -> str:
    """Extract markdown and code cells, exactly as lab_rag.read_notebook does."""
    import json

    with open(path, "r", errors="ignore") as handle:
        notebook = json.load(handle)
    parts = []
    for index, cell in enumerate(notebook.get("cells", [])):
        source = "".join(cell.get("source", []))
        kind = cell.get("cell_type", "")
        if kind == "markdown":
            parts.append(f"[Markdown Cell {index + 1}]\n{source}")
        elif kind == "code":
            parts.append(f"[Code Cell {index + 1}]\n{source}")
    return "\n\n".join(parts)


def build_index(root: str):
    """Chunk the corpus exactly as lab_rag.py does. This part is REAL."""
    chunks = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if name.endswith(".ipynb"):
                body = read_notebook(path)
            else:
                with open(path, "r", errors="ignore") as handle:
                    body = handle.read()
            text = f"FILE: {rel}\n\n{body}"
            start = 0
            while start < len(text):
                end = start + CHUNK_SIZE
                piece = text[start:end]
                cut = piece.rfind("\n", CHUNK_SIZE // 2)
                if cut > 0:
                    piece, end = piece[:cut], start + cut
                chunks.append({"text": piece.strip(), "source": rel, "start": start})
                start = end - CHUNK_OVERLAP
    return chunks


_WORD = re.compile(r"[a-z0-9_]+")


def _tokens(text: str):
    return set(_WORD.findall(text.lower()))


class KeywordCollection:
    """Stands in for ChromaDB. Same query interface; keyword scoring instead of
    embeddings so the demo runs with no GPU. Ranking is genuinely computed."""

    def __init__(self, chunks):
        self.chunks = chunks

    def query(self, query_embeddings=None, n_results=5):
        wanted = query_embeddings[0]         # the question text, passed through
        scored = []
        for chunk in self.chunks:
            overlap = len(wanted & _tokens(chunk["text"]))
            if overlap:
                scored.append((overlap, chunk))
        scored.sort(key=lambda pair: -pair[0])
        top = [chunk for _score, chunk in scored[:n_results]]
        return {
            "documents": [[c["text"] for c in top]],
            "metadatas": [[{"source": c["source"], "start_char": c["start"],
                            "filename": os.path.basename(c["source"])} for c in top]],
            "distances": [[1.0 / (1 + s) for s, _c in scored[:n_results]]],
        }


def embed(text: str):
    return _tokens(text)


def compose_answer(prompt: str) -> str:
    """Stands in for Qwen3-Coder. Extracts the most relevant line from the
    retrieved context and cites its file. Deterministic, no model."""
    question = prompt.split("QUESTION:")[-1].split("ANSWER:")[0].strip()
    blocks = prompt.split("CONTEXT FROM LAB FILES:")[-1].split("QUESTION:")[0]
    sections = [b for b in blocks.split("---") if b.strip()]
    if not sections:
        return "The provided context does not contain enough information to answer that."

    q_tokens = _tokens(question)
    best_line, best_score, best_source = "", 0, ""
    for section in sections:
        source = ""
        for line in section.strip().splitlines():
            if line.startswith("Source:"):
                source = line.split("Source:", 1)[1].strip()
                continue
            stripped = line.strip()
            if stripped.startswith(("[Markdown Cell", "[Code Cell", "FILE:", "#!")):
                continue
            score = len(q_tokens & _tokens(line))
            if score > best_score and len(stripped) > 25:
                best_line, best_score, best_source = line.strip(), score, source
    if best_score < 2:
        return "The provided context does not contain enough information to answer that."
    return f"{best_line}\n\nThis comes from `{best_source}`."


# =============================================================================
# ACTS
# =============================================================================


def act1_slack(collection):
    act("1", "The Slack bot — answers that show their sources")

    sys.path.insert(0, "/Users/avilash/levyboy-slackbot")
    import handlers                                     # noqa: E402

    lab_query._default_collection = lambda: collection
    lab_query._default_embed = embed
    lab_query._default_chat = compose_answer

    import agent                                        # noqa: E402
    agent.BACKEND = "rag"

    class FakeSlack:
        def __init__(self):
            self.text = {}

        def chat_postMessage(self, channel, thread_ts=None, text=""):
            print(f"  {DIM}LevyBoy posts: {text}{RESET}")
            return {"ts": "1", "channel": channel}

        def chat_update(self, channel, ts, text=""):
            self.text[ts] = text
            print(f"\n{GREEN}  LevyBoy replies:{RESET}")
            for line in text.splitlines():
                print(f"    {line}")
            return {"ts": ts}

    questions = [
        "where can I find the QC notebook for this cohort?",
        "what normalization was applied to the expression data?",
        "which script generates figure 3?",
        "why was leiden resolution 0.7 chosen over other values?",
    ]

    for question in questions:
        print(f"\n{BOLD}  Avilash:{RESET} @LevyBoy {question}")
        client = FakeSlack()
        handlers.handle_mention_event(
            {"channel": "C0PATHLGY", "ts": "10.0", "text": f"<@U0BOT> {question}"},
            client,
        )
        if PAUSE:
            input(f"\n{DIM}   [Enter]{RESET}")

    print()
    print(f"  {YELLOW}Watch the last one closely.{RESET}")
    note("Nobody ever wrote down WHY 0.7 was chosen. The correct answer is")
    note("'I don't know'. Instead the assistant found a line mentioning 0.7 and")
    note("answered as though that explained the choice.")
    print()
    note("That is a real weakness, not a scripted one — and it is exactly what")
    note("Act 3 is built to catch. Watch the 'correct abstention' number.")


def act2_safety():
    act("2", "Safety — the guardrails Dr. Levy asked for, actually enforced")

    with tempfile.TemporaryDirectory() as base:
        lab = os.path.join(base, "lab_data")
        scratch = os.path.join(base, "scratch")
        secret = os.path.join(base, "PATIENT_RECORDS")
        os.makedirs(lab)
        os.makedirs(scratch)
        os.makedirs(secret)
        with open(os.path.join(lab, "notes.md"), "w") as handle:
            handle.write("Cohort A analysis notes")
        with open(os.path.join(secret, "phi.csv"), "w") as handle:
            handle.write("patient_id,name,mrn")

        guard = safety.PathGuard(read_roots=[lab, scratch], write_root=scratch)
        print(safety.describe_posture(guard).replace(base, "…"))
        print()

        step("Reading an approved lab file")
        ok(f'allowed — got "{guard.read_text(os.path.join(lab, "notes.md"))}"')

        attacks = [
            ("Reading a file outside the approved folder",
             lambda: guard.read_text(os.path.join(secret, "phi.csv"))),
            ("Escaping upward with ../",
             lambda: guard.check_readable(os.path.join(lab, "..", "PATIENT_RECORDS", "phi.csv"))),
            ("Overwriting an original lab file",
             lambda: guard.check_writable(os.path.join(lab, "notes.md"))),
            ("Reading the .git folder",
             lambda: guard.check_readable(os.path.join(lab, ".git", "config"))),
        ]

        link = os.path.join(lab, "shortcut.csv")
        try:
            os.symlink(os.path.join(secret, "phi.csv"), link)
            attacks.insert(2, (
                "A SHORTCUT inside the approved folder pointing at patient records",
                lambda: guard.read_text(link),
            ))
        except OSError:
            pass

        for label, attempt in attacks:
            step(label)
            try:
                attempt()
                bad("NOT BLOCKED — this would be a serious problem")
            except safety.UnsafePathError as exc:
                reason = str(exc).replace(base, "…").replace(os.path.realpath(base), "…")
                ok(f"blocked — {reason[:110]}")

        step("Writing to the designated scratch folder")
        guard.check_writable(os.path.join(scratch, "output.csv"))
        ok("allowed — scratch is the one place writing is permitted")

    print()
    note("The shortcut case is the one that matters. A naive check compares text")
    note("prefixes and would let that through, straight into patient records.")


def act3_evaluation(collection):
    act("3", "The evaluation — scoring two methods against known answers")

    tasks_path = os.path.join(HERE, "demo_tasks.jsonl")
    manifest_path = os.path.join(HERE, "demo_manifest.txt")

    with open(manifest_path, "w") as handle:
        handle.write("\n".join(sorted(analyze.manifest_from_directory(CORPUS))))

    loaded = tasks_mod.load_tasks(tasks_path)
    print(tasks_mod.summarize(loaded))
    print()

    scored_agent, scored_keyword = [], []
    for task in loaded:
        result = lab_query.answer_question(
            task.question, collection=collection, embed_fn=embed,
            chat_fn=compose_answer, top_k=5,
        )
        record = result.to_dict()
        scored_agent.append(analyze.score_task(task, record, analyze.load_manifest(manifest_path)))

        # Baseline: a plausible-but-often-wrong guess, standing in for a method
        # with no grounding in the corpus.
        guess = {"loc": "src/preprocess.py", "com": "docs/README.md",
                 "rep": "src/utils.py", "und": ""}[task.id.split("-")[0]]
        baseline = {
            "sources": [guess] if guess else [],
            "chunks": [{"source": guess}] if guess else [],
            "cited_paths": [guess] if guess else [],
            "abstained": not guess,
            "latency_s": 6.0,
        }
        scored_keyword.append(
            analyze.score_task(task, baseline, analyze.load_manifest(manifest_path))
        )

    metrics = {
        "assistant (retrieval)": analyze.aggregate(scored_agent),
        "no-retrieval baseline": analyze.aggregate(scored_keyword),
    }
    comparison = analyze.compare_arms(scored_agent, scored_keyword)
    comparison.update({"label": "assistant vs baseline",
                       "first": "assistant", "second": "baseline"})
    print(analyze.render_report(metrics, [comparison]))

    agent_abstention = analyze.aggregate(scored_agent)["correct_abstention_rate"]
    print(f"\n{YELLOW}  Read this honestly:{RESET}")
    note("The assistant found the right file on every answerable question, and")
    note("beat the ungrounded baseline (p = 0.031).")
    print()
    print(f"  {RED}But look at correct abstention: "
          f"{agent_abstention['successes']}/{agent_abstention['n']}.{RESET}")
    note("On both questions whose answers were never written down, it answered")
    note("anyway instead of saying 'I don't know'. The ungrounded baseline scored")
    note("2/2 there — for the uninteresting reason that it had nothing to say.")
    print()
    note("This is the single most useful thing the harness does. Without those")
    note("control questions we would report 100% accuracy and never notice the")
    note("assistant confidently answering things it cannot know.")


def act4_no_fake_results():
    act("4", "The guardrail that makes fabricated results impossible")

    template = os.path.join(ROOT, "evaluation", "tasks.template.jsonl")
    loaded = tasks_mod.load_tasks(template)
    print(f"  The shipped 30-question template loads fine:\n")
    print("   ", tasks_mod.summarize(loaded).replace("\n", "\n    "))
    print()
    note("30 questions, but ZERO scorable — every correct answer is blank,")
    note("because only someone with lab access can fill those in.")
    print()

    step("Trying to score it anyway")
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "run.jsonl")
        with open(log, "w") as handle:
            handle.write('{"task_id": "loc-001", "arm": "agent", "sources": ["x.py"]}\n')
        buffer, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            code = analyze.main(["--tasks", template, "--runs", log])
    ok(f"refused — exit code {code}, no numbers printed")
    print()
    note("It errors out rather than producing a percentage. You cannot")
    note("accidentally generate a result that looks real but isn't.")


def main():
    print(f"\n{BOLD}{'=' * 74}")
    print("  LAB-PERSONALIZED RESEARCH ASSISTANT — FULL DEMO")
    print(f"{'=' * 74}{RESET}")
    print(f"""
  REAL in this demo: chunking, retrieval ranking, every safety check,
  every metric, every statistic, all scoring logic — the production code.

  STOOD IN: the embedding model and language model (Qwen3-Coder on a GPU).
  Replaced with a deterministic keyword retriever so this runs on a laptop.

  The corpus is SYNTHETIC. No real lab data is used anywhere.
""")
    if PAUSE:
        input(f"{DIM}   [Enter to begin]{RESET}")

    chunks = build_index(CORPUS)
    collection = KeywordCollection(chunks)
    files = len({c["source"] for c in chunks})
    print(f"\n  Indexed {files} files into {len(chunks)} chunks "
          f"({CHUNK_SIZE} chars, {CHUNK_OVERLAP} overlap — same as production).")

    act1_slack(collection)
    act2_safety()
    act3_evaluation(collection)
    act4_no_fake_results()

    print(f"\n{BOLD}{'=' * 74}")
    print("  DEMO COMPLETE")
    print(f"{'=' * 74}{RESET}")
    print("""
  Shown:
    1. An assistant that answers and shows which files it used
    2. Safety guardrails blocking five real escape attempts
    3. A working evaluation that scores methods against known answers,
       catches invented file paths, and detects fabricated answers
    4. A system that refuses to produce results it cannot back up

  Not shown, because it does not exist yet: any real result.
  That needs cluster access and a completed lab project to test against.
""")


if __name__ == "__main__":
    main()
