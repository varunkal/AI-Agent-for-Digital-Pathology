"""
run_eval.py — execute a frozen task set against one arm and write a run log.

Arms (protocol §2)
------------------
  agent   Our lab-personalized system. Fully automated: calls
          rag/lab_query.answer_question(), which preserves sources.
  manual  Human (arm A) or generic-LLM (arm B) sessions, transcribed by hand.
  dryrun  A built-in fake. Validates the whole pipeline with no HPC, no model,
          no index. Produces clearly-labelled synthetic output.

WHY THERE IS NO AUTOMATED EXTERNAL-API ARM
------------------------------------------
The protocol's arm B compares against a generic model with no lab context, which
means an external API. This script deliberately does NOT implement that call.

Reason: sending lab content to an external service is a data-egress decision that
requires the PI's explicit approval (protocol §8), and the project's own
constraints state no patient data may leave institutional infrastructure. Baking
in an automated egress path would make it trivially easy to do the wrong thing by
accident.

So arm B is run by a human, in a browser, on de-identified task phrasings only,
and transcribed with `--arm manual`. That keeps a person in the loop on every
outbound query. Do not "improve" this by adding an API client until Dr. Levy has
signed off in writing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rag"))

from tasks import Task, load_tasks, validate  # noqa: E402

ARMS = ("agent", "manual", "dryrun")


# --- Arm implementations -----------------------------------------------------


def run_agent(task: Task) -> dict:
    """Our system. Requires Ollama running and a populated index (on Discovery)."""
    import lab_query

    result = lab_query.answer_question(task.question)
    payload = result.to_dict()
    payload["arm"] = "agent"
    return payload


def run_dryrun(task: Task) -> dict:
    """Deterministic fake, for validating the pipeline end to end.

    Marked synthetic in the record so it can never be mistaken for real data.
    On 'undocumented' tasks it abstains, which is the behavior we want to be able
    to detect — so a dry run exercises the abstention metric too.
    """
    started = time.monotonic()
    if task.expect_abstention:
        answer = "The provided context does not contain enough information to answer that."
        sources: List[str] = []
    else:
        sources = list(task.expected_paths[:1]) or ["<none>"]
        answer = f"[SYNTHETIC] See `{sources[0]}` for this. Not a real model output."
    return {
        "arm": "dryrun",
        "synthetic": True,
        "question": task.question,
        "answer": answer,
        "sources": sources,
        # Include chunk detail so a dry run exercises the chunk-level retrieval
        # metrics too, exactly as the real agent arm does.
        "chunks": [{"source": s, "start_char": 0, "distance": 0.1} for s in sources],
        "cited_paths": sources if sources != ["<none>"] else [],
        "abstained": bool(task.expect_abstention),
        "latency_s": round(time.monotonic() - started, 4),
    }


def run_manual(task: Task) -> dict:
    """Prompt the operator to paste in what a human or external model produced."""
    print("\n" + "=" * 72)
    print(f"Task {task.id}  [{task.category}]")
    print(f"QUESTION: {task.question}")
    if task.category != "undocumented":
        print("(If the responder could not answer, leave the answer blank.)")
    print("=" * 72)

    started = time.monotonic()
    print("Paste the answer, then a blank line:")
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    elapsed = time.monotonic() - started
    answer = "\n".join(lines).strip()

    raw_paths = input("File paths cited (comma-separated, blank if none): ").strip()
    cited = [p.strip() for p in raw_paths.split(",") if p.strip()]

    raw_seconds = input(
        f"Seconds taken (blank = measured {elapsed:.0f}s): "
    ).strip()
    try:
        latency = float(raw_seconds) if raw_seconds else elapsed
    except ValueError:
        latency = elapsed

    abstained_input = input("Did they decline / say they couldn't find it? [y/N]: ").strip().lower()
    abstained = abstained_input.startswith("y") or not answer

    return {
        "question": task.question,
        "answer": answer,
        # For manual arms there is no retrieval step, so `sources` is what the
        # responder actually pointed at. Retrieval metrics are therefore only
        # meaningful for the agent arm — note this in the paper.
        "sources": cited,
        "cited_paths": cited,
        "abstained": abstained,
        "latency_s": round(latency, 2),
    }


RUNNERS: Dict[str, Callable[[Task], dict]] = {
    "agent": run_agent,
    "manual": run_manual,
    "dryrun": run_dryrun,
}


# --- Driver ------------------------------------------------------------------


def run(
    tasks: Sequence[Task],
    arm: str,
    out_path: str,
    *,
    arm_label: Optional[str] = None,
    resume: bool = True,
) -> int:
    """Run every task through `arm`, appending one JSON record per line.

    Appends and skips already-completed task ids so an interrupted manual session
    can be resumed without redoing work.
    """
    runner = RUNNERS[arm]
    label = arm_label or arm

    done = set()
    if resume and os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line).get("task_id"))
                except json.JSONDecodeError:
                    continue
        if done:
            print(f"Resuming: {len(done)} task(s) already recorded in {out_path}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    written = 0
    with open(out_path, "a", encoding="utf-8") as handle:
        for task in tasks:
            if task.id in done:
                continue
            try:
                record = runner(task)
            except KeyboardInterrupt:
                print("\nInterrupted. Progress saved; rerun to resume.")
                break
            except Exception as exc:  # noqa: BLE001 - log and continue
                print(f"  ERROR on {task.id}: {type(exc).__name__}: {exc}", file=sys.stderr)
                record = {"error": f"{type(exc).__name__}: {exc}"}

            record["task_id"] = task.id
            record["category"] = task.category
            record.setdefault("arm", label)
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            written += 1
            print(f"  [{written}] {task.id} recorded")

    print(f"\nWrote {written} record(s) to {out_path}")
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run an evaluation arm.")
    parser.add_argument("--tasks", required=True, help="frozen tasks.jsonl")
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--out", required=True, help="run log to append to")
    parser.add_argument(
        "--arm-label",
        help="label recorded in the log (e.g. 'generic' or 'human') when using --arm manual",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--only",
        help="comma-separated task ids or categories to run",
    )
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks)
    report = validate(tasks)
    for error in report["errors"]:
        print(f"ERROR {error}", file=sys.stderr)
    if report["errors"]:
        return 2

    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        tasks = [t for t in tasks if t.id in wanted or t.category in wanted]
        if not tasks:
            print(f"ERROR --only matched no tasks: {sorted(wanted)}", file=sys.stderr)
            return 2

    if args.arm == "manual" and not args.arm_label:
        print(
            "NOTE  --arm manual without --arm-label; records will be labelled "
            "'manual'. Use --arm-label human or --arm-label generic so arms can "
            "be told apart at analysis time.",
            file=sys.stderr,
        )

    if args.arm == "dryrun":
        print(
            "DRY RUN: output is SYNTHETIC and marked as such. It validates the "
            "pipeline only and must never be reported as a result.\n"
        )

    run(
        tasks,
        args.arm,
        args.out,
        arm_label=args.arm_label,
        resume=not args.no_resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
