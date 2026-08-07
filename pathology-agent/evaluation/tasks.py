"""
tasks.py — the frozen evaluation task set: schema, loading, validation.

A task is one question with known ground truth. The task set must be written and
FROZEN before any arm is run (see EVALUATION_PROTOCOL.md §5) so that success
thresholds cannot be set after seeing results.

Categories (protocol §3):
  locate       - "where is X" retrieval questions
  comprehend   - questions about what a file/analysis does
  reproduce    - "what steps regenerate figure N"
  undocumented - control tasks whose answers were NEVER written down. The correct
                 behavior is to decline. These exist to measure whether the agent
                 fabricates, and to stop us overclaiming.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

CATEGORIES = ("locate", "comprehend", "reproduce", "undocumented")

# Target counts from the protocol. Validation warns (not errors) on mismatch, so
# a smaller pilot set is still runnable.
TARGET_COUNTS = {"locate": 10, "comprehend": 8, "reproduce": 7, "undocumented": 5}


@dataclass
class Task:
    id: str
    category: str
    question: str
    expected_paths: List[str] = field(default_factory=list)
    expected_answer: Optional[str] = None
    expect_abstention: bool = False
    ground_truth_source: Optional[str] = None
    notes: Optional[str] = None

    @property
    def is_placeholder(self) -> bool:
        """True if ground truth has not been filled in by someone with lab access.

        Placeholder tasks are excluded from scoring. This is what keeps template
        tasks from silently becoming fake results.
        """
        if self.category == "undocumented":
            # These need no expected_paths; they need a confirmed provenance note.
            return not self.ground_truth_source
        return not self.expected_paths or not self.ground_truth_source

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        missing = {"id", "category", "question"} - set(raw)
        if missing:
            raise ValueError(f"Task missing required field(s): {sorted(missing)} in {raw!r}")
        if raw["category"] not in CATEGORIES:
            raise ValueError(
                f"Task {raw['id']!r}: unknown category {raw['category']!r}; "
                f"must be one of {CATEGORIES}"
            )
        return cls(
            id=str(raw["id"]),
            category=raw["category"],
            question=raw["question"],
            expected_paths=list(raw.get("expected_paths") or []),
            expected_answer=raw.get("expected_answer"),
            expect_abstention=bool(
                raw.get("expect_abstention", raw["category"] == "undocumented")
            ),
            ground_truth_source=raw.get("ground_truth_source"),
            notes=raw.get("notes"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "question": self.question,
            "expected_paths": self.expected_paths,
            "expected_answer": self.expected_answer,
            "expect_abstention": self.expect_abstention,
            "ground_truth_source": self.ground_truth_source,
            "notes": self.notes,
        }


def load_tasks(path: str) -> List[Task]:
    """Load tasks from JSONL. Blank lines and `#` comment lines are ignored."""
    tasks: List[Task] = []
    seen_ids = set()
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON — {exc}") from exc
            task = Task.from_dict(raw)
            if task.id in seen_ids:
                raise ValueError(f"{path}:{lineno}: duplicate task id {task.id!r}")
            seen_ids.add(task.id)
            tasks.append(task)
    return tasks


def save_tasks(tasks: Sequence[Task], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task.to_dict()) + "\n")


def validate(tasks: Sequence[Task]) -> Dict[str, List[str]]:
    """Return {"errors": [...], "warnings": [...]}.

    Errors mean the set cannot be scored. Warnings mean it deviates from the
    protocol but is still runnable (e.g. a smaller pilot).
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not tasks:
        errors.append("Task set is empty.")
        return {"errors": errors, "warnings": warnings}

    counts = {category: 0 for category in CATEGORIES}
    for task in tasks:
        counts[task.category] += 1

        if task.category in ("locate", "reproduce") and not task.expected_paths:
            warnings.append(
                f"{task.id}: {task.category} task has no expected_paths — "
                "cannot score retrieval accuracy; will be treated as a placeholder."
            )
        if task.category == "undocumented" and not task.expect_abstention:
            errors.append(
                f"{task.id}: undocumented tasks must set expect_abstention=true."
            )
        if task.category != "undocumented" and task.expect_abstention:
            warnings.append(
                f"{task.id}: expect_abstention=true on a {task.category} task — "
                "is that intended?"
            )
        if not task.ground_truth_source:
            warnings.append(
                f"{task.id}: no ground_truth_source. Per protocol §3, each task's "
                "answer must be confirmed by someone with lab access, and by whom "
                "recorded. Unconfirmed tasks are excluded from scoring."
            )

    for category, target in TARGET_COUNTS.items():
        if counts[category] != target:
            warnings.append(
                f"category {category!r}: {counts[category]} tasks (protocol targets {target})"
            )

    if counts["undocumented"] == 0:
        errors.append(
            "No 'undocumented' control tasks. These are required — without them "
            "there is no measure of whether the agent fabricates answers."
        )

    return {"errors": errors, "warnings": warnings}


def scorable(tasks: Sequence[Task]) -> List[Task]:
    """Tasks with real ground truth. Placeholders are excluded from all metrics."""
    return [task for task in tasks if not task.is_placeholder]


def summarize(tasks: Sequence[Task]) -> str:
    counts: Dict[str, int] = {}
    for task in tasks:
        counts[task.category] = counts.get(task.category, 0) + 1
    ready = len(scorable(tasks))
    lines = [f"{len(tasks)} tasks loaded ({ready} scorable, {len(tasks) - ready} placeholder)"]
    for category in CATEGORIES:
        lines.append(f"  {category:<13} {counts.get(category, 0)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tasks.py <tasks.jsonl>   # validate a task set")
        sys.exit(1)

    loaded = load_tasks(sys.argv[1])
    print(summarize(loaded))
    report = validate(loaded)
    for warning in report["warnings"]:
        print(f"WARN  {warning}")
    for error in report["errors"]:
        print(f"ERROR {error}")
    sys.exit(1 if report["errors"] else 0)
