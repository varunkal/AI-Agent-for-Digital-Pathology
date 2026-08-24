"""
workflow.py — reconstruct the pipeline that produced a result.

WHY THIS EXISTS
---------------
Pitch deck, Approach: "Generate workflow summaries."
Project description: help researchers "move from high-level biological questions
to concrete, reproducible computational experiments", and make it "easier to
reproduce and build on previous projects".

Question-answering does not do this. Asking "which script made Figure 3?" gets one
file. What a researcher actually needs is the whole chain: which script, reading
which inputs, produced by which earlier step, with which parameters — the thing
that would let them re-run it.

DESIGN: STRUCTURE IS COMPUTED, PROSE IS GENERATED
-------------------------------------------------
The dependency graph is built by parsing the corpus for file references. No model
is involved, so the structure is verifiable: every edge points at a real string in
a real file, and can be checked by hand.

The language model is used only to describe the chain in readable terms. It cannot
invent a step, because the steps come from the graph.

This split matters. A model asked to "summarize the workflow" from retrieved
snippets will confidently produce a plausible pipeline that never existed — and
that failure is invisible, because plausible-and-wrong reads exactly like correct.
Computing the structure first removes that whole failure mode.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

# File-like strings appearing in code or prose.
_PATHY = re.compile(
    r"[\w./\\-]*\w\.(?:py|ipynb|md|txt|json|ya?ml|csv|tsv|sh|R|rds|h5ad|h5|pkl|png|pdf|svg)\b",
    re.IGNORECASE,
)

# Crude but effective read/write signals. Reported as evidence, never as
# certainty — a reader can check the quoted line.
_WRITE_HINTS = (
    "savefig", "to_csv", "write", "dump", "save", "output", "writes", "->", "wrote",
)
_READ_HINTS = (
    "read_csv", "read_h5ad", "load", "open(", "input", "reads", "import", "read",
)

SOURCE_EXTENSIONS = {".py", ".ipynb", ".sh", ".r"}


@dataclass
class FileRef:
    """One mention of a path inside a file."""

    path: str                 # the referenced path, as written
    line: str                 # the line it appeared on, for the reader to check
    direction: str            # "reads" | "writes" | "mentions"


@dataclass
class WorkflowStep:
    source_file: str
    reads: List[str] = field(default_factory=list)
    writes: List[str] = field(default_factory=list)
    evidence: List[FileRef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "reads": self.reads,
            "writes": self.writes,
            "evidence": [
                {"path": e.path, "line": e.line.strip()[:160], "direction": e.direction}
                for e in self.evidence
            ],
        }


@dataclass
class Workflow:
    target: str
    steps: List[WorkflowStep] = field(default_factory=list)
    summary: str = ""
    unresolved: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "steps": [s.to_dict() for s in self.steps],
            "summary": self.summary,
            "unresolved": self.unresolved,
        }


# --- Graph construction (no model involved) ----------------------------------


def _read_text(path: str) -> str:
    if path.lower().endswith(".ipynb"):
        try:
            with open(path, "r", errors="ignore") as handle:
                notebook = json.load(handle)
            return "\n".join(
                "".join(cell.get("source", []))
                for cell in notebook.get("cells", [])
                if cell.get("cell_type") in ("markdown", "code")
            )
        except Exception:
            return ""
    try:
        with open(path, "r", errors="ignore") as handle:
            return handle.read()
    except Exception:
        return ""


def _direction(line: str, path: str) -> str:
    """Classify a reference as read, write, or bare mention.

    Write is checked first: a line like `fig.savefig('out.png')` contains
    'save' and would otherwise be swallowed by the read hint 'open('.
    """
    low = line.lower()
    if any(hint in low for hint in _WRITE_HINTS):
        return "writes"
    if any(hint in low for hint in _READ_HINTS):
        return "reads"
    return "mentions"


def scan_corpus(root: str) -> Dict[str, List[FileRef]]:
    """Map each source file -> the file references it contains."""
    root = os.path.abspath(root)
    graph: Dict[str, List[FileRef]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in SOURCE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            refs: List[FileRef] = []
            for line in _read_text(full).splitlines():
                for match in _PATHY.finditer(line):
                    referenced = match.group(0)
                    # Skip a file referring to itself.
                    if os.path.basename(referenced) == name:
                        continue
                    refs.append(
                        FileRef(
                            path=referenced.lstrip("./"),
                            line=line,
                            direction=_direction(line, referenced),
                        )
                    )
            graph[rel] = refs
    return graph


def _same_file(a: str, b: str) -> bool:
    a, b = a.replace("\\", "/").lstrip("/"), b.replace("\\", "/").lstrip("/")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a) or (
        os.path.basename(a) == os.path.basename(b)
    )


def producers_of(graph: Dict[str, List[FileRef]], target: str) -> List[str]:
    """Source files that appear to WRITE `target`."""
    return sorted(
        source
        for source, refs in graph.items()
        if any(r.direction == "writes" and _same_file(r.path, target) for r in refs)
    )


def trace(
    root: str,
    target: str,
    *,
    max_depth: int = 5,
) -> Workflow:
    """Walk backwards from `target` to the chain of steps that produced it.

    Purely structural. Every step corresponds to a real file containing a real
    line that references the artifact — nothing is inferred by a model.
    """
    graph = scan_corpus(root)
    corpus_files = set(graph)

    workflow = Workflow(target=target)
    seen: Set[str] = set()
    frontier: List[Tuple[str, int]] = [(target, 0)]

    while frontier:
        artifact, depth = frontier.pop(0)
        if depth > max_depth:
            continue
        for source in producers_of(graph, artifact):
            if source in seen:
                continue
            seen.add(source)
            refs = graph[source]
            reads = sorted({r.path for r in refs if r.direction == "reads"})
            writes = sorted({r.path for r in refs if r.direction == "writes"})
            workflow.steps.append(
                WorkflowStep(
                    source_file=source,
                    reads=reads,
                    writes=writes,
                    evidence=[r for r in refs if _same_file(r.path, artifact)],
                )
            )
            for upstream in reads:
                if any(_same_file(upstream, f) for f in corpus_files):
                    frontier.append((upstream, depth + 1))
                elif producers_of(graph, upstream):
                    frontier.append((upstream, depth + 1))
                else:
                    if upstream not in workflow.unresolved:
                        workflow.unresolved.append(upstream)

    # Deepest-first: the earliest pipeline stage should read first.
    workflow.steps.reverse()
    return workflow


# --- Rendering ---------------------------------------------------------------


def render_structure(workflow: Workflow) -> str:
    """The graph as text. This part is checkable line by line."""
    if not workflow.steps:
        return (
            f"No step in the corpus appears to produce {workflow.target!r}.\n"
            "Either it is an input rather than an output, or the producing code "
            "is not indexed."
        )
    lines = [f"Pipeline producing {workflow.target}:", ""]
    for number, step in enumerate(workflow.steps, 1):
        lines.append(f"  {number}. {step.source_file}")
        if step.reads:
            lines.append(f"       reads : {', '.join(step.reads[:6])}")
        if step.writes:
            lines.append(f"       writes: {', '.join(step.writes[:6])}")
        for ref in step.evidence[:2]:
            lines.append(f"       > {ref.line.strip()[:110]}")
    if workflow.unresolved:
        lines += [
            "",
            "  Inputs with no producer in the corpus (raw data or not indexed):",
            *[f"    - {u}" for u in workflow.unresolved[:8]],
        ]
    return "\n".join(lines)


SUMMARY_PROMPT = """You are describing a computational pipeline to a researcher who
needs to re-run it.

Below is a dependency chain extracted DIRECTLY from the lab's files. It is factual
— do not add steps, files, or parameters that are not listed. If something is
missing, say it is missing.

Write a short summary: what the pipeline does, in what order, and what a person
would need in order to reproduce it.

{structure}

SUMMARY:"""


def summarize(
    workflow: Workflow,
    *,
    chat_fn: Optional[Callable[[str], str]] = None,
) -> str:
    """Ask the model to describe the computed chain in prose.

    The model receives ONLY the extracted structure, not free-form retrieved
    text, so it has nothing to invent a step from.
    """
    structure = render_structure(workflow)
    if not workflow.steps:
        return structure
    if chat_fn is None:
        import lab_query

        chat_fn = lab_query._default_chat
    return chat_fn(SUMMARY_PROMPT.format(structure=structure))


def build(
    root: str,
    target: str,
    *,
    chat_fn: Optional[Callable[[str], str]] = None,
    describe: bool = True,
) -> Workflow:
    workflow = trace(root, target)
    if describe:
        workflow.summary = summarize(workflow, chat_fn=chat_fn)
    return workflow


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python workflow.py <corpus_dir> <target_file> [--no-summary]")
        raise SystemExit(1)
    result = trace(sys.argv[1], sys.argv[2])
    print(render_structure(result))
    if "--no-summary" not in sys.argv:
        print("\n--- summary ---\n")
        print(summarize(result))
