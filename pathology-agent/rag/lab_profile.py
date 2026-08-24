"""
lab_profile.py — the lab-personalization layer.

WHY THIS EXISTS
---------------
Pitch deck, Aim 2: "Basically, making the LLM ours by making it know our lab."
Project description: agents should "learn and adopt lab-specific workflows, file
structures, best practices, preferred statistical methods, naming conventions,
quality-control standards, and interpretation norms."

Retrieval alone does not do this. Retrieval finds passages that look like the
question. It does not know that this lab always normalizes to median counts, that
`cohortA/` means something specific, or that a resolution of 0.7 is the house
default. That knowledge lives in people's heads and in conventions, not in any
one file that similarity search will surface.

This module holds that knowledge as an explicit, human-editable profile and
injects it into the prompt. It is the difference between a generic assistant with
a search box and an assistant that behaves like someone who works here.

WHY A MARKDOWN FILE
-------------------
The profile has to be written and maintained by lab members, not engineers. A
Markdown file with `## Section` headers is editable by anyone, reviewable in a
pull request, and diffable. No YAML parser, no schema to learn, no dependencies.

MEASURABLE BY CONSTRUCTION
--------------------------
Everything here is switchable. The evaluation runs the same questions with the
profile on and off, so the contribution is a measured contrast rather than an
assertion. If personalization does not help, that is a real finding and this
module makes it visible instead of hiding it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Section headings the profile may define. Anything else is kept but not
# prioritized. Drawn directly from the project description's list of what a
# lab-personalized agent should know.
KNOWN_SECTIONS = (
    "Overview",
    "Naming conventions",
    "File structure",
    "Standard pipelines",
    "Quality control standards",
    "Preferred statistical methods",
    "Data structures",
    "Figure conventions",
    "Interpretation norms",
    "Known pitfalls",
)

DEFAULT_PROFILE_NAME = "LAB_PROFILE.md"


_PLACEHOLDER = re.compile(r"^\s*(\[?\s*)?(todo|tbd|fill in|xxx)\b", re.IGNORECASE)


def _is_placeholder(body: str) -> bool:
    """True if a section is an unfilled template stub rather than real content."""
    return bool(_PLACEHOLDER.match(body or ""))


@dataclass
class LabProfile:
    """Lab conventions, parsed from Markdown."""

    sections: Dict[str, str] = field(default_factory=dict)
    source_path: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        """True if nothing real has been written yet.

        A profile of nothing but TODO markers counts as EMPTY. Treating it as
        filled would report 100% coverage on a blank template and would inject
        the literal word "TODO" into the model's context.
        """
        return not any(
            body.strip() and not _is_placeholder(body)
            for body in self.sections.values()
        )

    @property
    def filled_sections(self) -> List[str]:
        return [
            name for name, body in self.sections.items()
            if body.strip() and not _is_placeholder(body)
        ]

    @property
    def unfilled_sections(self) -> List[str]:
        """Sections present as headings but with no content, or still a TODO.

        Surfaced so a half-written profile is obvious rather than silently
        weakening the system.
        """
        return [
            name for name, body in self.sections.items()
            if not body.strip() or _is_placeholder(body)
        ]

    def coverage(self) -> float:
        """Fraction of the known section list that is actually filled in."""
        filled = sum(
            1 for name in KNOWN_SECTIONS
            if self.sections.get(name, "").strip()
            and not _is_placeholder(self.sections[name])
        )
        return filled / len(KNOWN_SECTIONS)


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def parse_profile(text: str, source_path: Optional[str] = None) -> LabProfile:
    """Parse `## Section` headings into a profile. Content before the first
    heading is ignored (it is the file's own preamble, not lab knowledge)."""
    sections: Dict[str, str] = {}
    matches = list(_HEADING.finditer(text or ""))
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # Drop HTML-style comments used for instructions to the author.
        body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
        sections[name] = body
    return LabProfile(sections=sections, source_path=source_path)


def load_profile(path: Optional[str] = None) -> LabProfile:
    """Load the profile from disk. Returns an empty profile if absent.

    An absent profile is not an error — it is the un-personalized condition, and
    the evaluation needs to be able to run in exactly that state.
    """
    if path is None:
        path = os.environ.get("LAB_PROFILE_PATH") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), DEFAULT_PROFILE_NAME
        )
    if not os.path.exists(path):
        return LabProfile(sections={}, source_path=None)
    with open(path, "r", encoding="utf-8") as handle:
        return parse_profile(handle.read(), source_path=path)


# --- Prompt construction -----------------------------------------------------

_PREAMBLE = (
    "LAB CONTEXT — conventions of the laboratory you are assisting. Use these to "
    "interpret questions and to judge whether retrieved files match the lab's "
    "normal practice. This is background knowledge, NOT a source you may cite: "
    "if a question asks for a specific fact, it must still be supported by the "
    "retrieved files, and if it is not, say so."
)


def render_context(
    profile: LabProfile,
    *,
    include: Optional[List[str]] = None,
    max_chars: int = 4000,
) -> str:
    """Render the profile as a prompt block. Empty profile renders to "".

    The preamble matters: without it the model treats lab conventions as
    retrieved evidence and starts citing "the lab context" as though it were a
    file. That would directly undermine the grounding measurement, so the
    instruction to keep them separate is part of the method.
    """
    if profile.is_empty:
        return ""

    wanted = include or [
        name for name in KNOWN_SECTIONS
        if profile.sections.get(name, "").strip()
        and not _is_placeholder(profile.sections[name])
    ]
    # Preserve any custom sections the lab added beyond the known list.
    for name in profile.sections:
        if (name not in wanted and name not in KNOWN_SECTIONS
                and profile.sections[name].strip()
                and not _is_placeholder(profile.sections[name])):
            wanted.append(name)

    parts, budget = [], max_chars
    for name in wanted:
        body = profile.sections.get(name, "").strip()
        if not body or _is_placeholder(body):
            continue          # never put "TODO" in front of the model
        block = f"### {name}\n{body}"
        if len(block) > budget:
            block = block[: max(0, budget)].rstrip() + "\n[truncated]"
        if not block.strip():
            break
        parts.append(block)
        budget -= len(block)
        if budget <= 0:
            break

    if not parts:
        return ""
    return _PREAMBLE + "\n\n" + "\n\n".join(parts)


def describe(profile: LabProfile) -> str:
    """Human-readable summary, for logs and for the paper's methods section."""
    if profile.is_empty:
        return "Lab profile: NONE (un-personalized condition)"
    lines = [
        f"Lab profile: {profile.source_path or '<inline>'}",
        f"  sections filled : {len(profile.filled_sections)}",
        f"  coverage        : {profile.coverage() * 100:.0f}% of known categories",
    ]
    if profile.unfilled_sections:
        lines.append(f"  STILL TODO      : {', '.join(profile.unfilled_sections)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    loaded = load_profile(sys.argv[1] if len(sys.argv) > 1 else None)
    print(describe(loaded))
    if not loaded.is_empty:
        print("\n--- rendered prompt block ---\n")
        print(render_context(loaded))
