"""
run_arms.py — execute every experimental arm over a frozen task set.

    python3 evaluation/run_arms.py --tasks demo/demo_tasks.jsonl \
                                   --corpus demo/corpus \
                                   --out runs/ --replicates 3

ARMS
----
  personalized    assistant + retrieval + lab profile   (the full system)
  plain           assistant + retrieval, no profile     (does lab context help?)
  norag           assistant, NO retrieval               (does grounding help?)
  bm25            keyword search only, no model         (does it beat grep?)

Each arm changes exactly one thing relative to its neighbour, so any difference
is attributable. `personalized` vs `plain` isolates the lab-personalization
contribution. `plain` vs `norag` isolates grounding while holding model size
constant. `plain` vs `bm25` asks whether the language model earns its cost.

REPLICATES
----------
Sampling is pinned to temperature 0, but a pinned seed does not guarantee
bit-identical output across runtime versions, and retrieval ties can break
differently. Replicates make any residual instability visible rather than
assumed away. Each replicate is logged separately; the analysis can pool or
report per-replicate.

PROVENANCE
----------
A fingerprint of the exact configuration is written alongside the runs, and any
condition that would undermine a reported number (nondeterminism, uncommitted
code, unknown model build) is printed as a warning before anything executes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "rag"))

from tasks import Task, load_tasks, validate  # noqa: E402

ARMS = ("personalized", "plain", "norag", "bm25")

ARM_DESCRIPTIONS = {
    "personalized": "assistant + retrieval + lab profile",
    "plain": "assistant + retrieval, no lab profile",
    "norag": "assistant, no retrieval (model memory only)",
    "bm25": "keyword search only, no language model",
}


def run_arm(
    arm: str,
    tasks: Sequence[Task],
    *,
    corpus: str,
    profile_path: Optional[str],
    replicate: int,
) -> List[dict]:
    """Run one arm over every task once. Returns records."""
    records: List[dict] = []

    if arm == "bm25":
        import lexical_baseline

        index = lexical_baseline.build_index(corpus)
        for task in tasks:
            record = lexical_baseline.answer_record(index, task.question)
            records.append(record)
        return records

    import lab_query

    personalize = arm == "personalized"
    retrieval = arm != "norag"

    for task in tasks:
        try:
            result = lab_query.answer_question(
                task.question,
                personalize=personalize,
                profile_path=profile_path if personalize else None,
                retrieval=retrieval,
            )
            record = result.to_dict()
            record["arm"] = arm
        except Exception as exc:  # noqa: BLE001 — logged, not fatal
            record = {"arm": arm, "error": f"{type(exc).__name__}: {exc}"}
        records.append(record)
    return records


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run all experimental arms.")
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", required=True, help="directory for run logs")
    parser.add_argument("--profile", help="path to LAB_PROFILE.md")
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks)
    report = validate(tasks)
    for error in report["errors"]:
        print(f"ERROR {error}", file=sys.stderr)
    if report["errors"]:
        return 2

    os.makedirs(args.out, exist_ok=True)

    # --- provenance, before anything runs -----------------------------------
    import lab_query
    import provenance

    fingerprint = provenance.from_config(
        lab_query.config(),
        chunk_size=800,
        chunk_overlap=100,
        repo_paths={"harness": ROOT, "lab_rag": os.path.expanduser("~/labagent")},
        extra={
            "corpus": os.path.abspath(args.corpus),
            "tasks": os.path.abspath(args.tasks),
            "profile": os.path.abspath(args.profile) if args.profile else None,
            "replicates": args.replicates,
            "arms": args.arms,
        },
    )
    print(provenance.describe(fingerprint))
    issues = provenance.warnings(fingerprint)
    if issues:
        print("\nWARNINGS — these would undermine a reported result:")
        for issue in issues:
            print(f"  - {issue}")
    with open(os.path.join(args.out, "provenance.json"), "w") as handle:
        json.dump(fingerprint, handle, indent=2)

    print(f"\n{len(tasks)} tasks x {len(args.arms)} arms x {args.replicates} replicate(s)")
    print(f"= {len(tasks) * len(args.arms) * args.replicates} queries\n")

    for arm in args.arms:
        path = os.path.join(args.out, f"{arm}.jsonl")
        written = 0
        with open(path, "w", encoding="utf-8") as handle:
            for replicate in range(1, args.replicates + 1):
                print(f"  {arm:<14} replicate {replicate}/{args.replicates} …", flush=True)
                records = run_arm(
                    arm, tasks,
                    corpus=args.corpus,
                    profile_path=args.profile,
                    replicate=replicate,
                )
                for task, record in zip(tasks, records):
                    record["task_id"] = task.id
                    record["category"] = task.category
                    record["replicate"] = replicate
                    record.setdefault("arm", arm)
                    handle.write(json.dumps(record) + "\n")
                    written += 1
        errors = 0
        with open(path) as handle:
            for line in handle:
                if line.strip() and json.loads(line).get("error"):
                    errors += 1
        note = f"  ({errors} error(s))" if errors else ""
        print(f"  {arm:<14} {written} records -> {path}{note}")

    print(f"\nDone. Score with:\n"
          f"  python3 evaluation/analyze.py --tasks {args.tasks} \\\n"
          f"      --runs {args.out}/*.jsonl --manifest <manifest>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
