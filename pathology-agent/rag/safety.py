"""
safety.py — enforced read-only access to lab materials.

WHY THIS EXISTS
---------------
Two explicit constraints on this project:

  Dr. Levy, Slack, 7/10/2026:
    "Please be careful about using agents modifying existing file structure,
     would not recommend doing that as it can disrupt our processes... Please
     make sure safeguards are in place"

  Project description (Project List 2026):
    "Agents should operate in controlled environments and should not overwrite
     or modify original research data."

Until now these were stated intentions, not enforced code. This module makes them
mechanical: a path allowlist, real read-only file opening, and confinement of any
write to an explicit scratch directory.

DESIGN NOTES
------------
Every check resolves symlinks BEFORE testing containment. A naive prefix check on
the unresolved path is bypassable with a symlink pointing outside the allowed
root, which is exactly the failure mode that would let an agent touch real lab
data.

This is a guardrail, not a sandbox. It constrains code that chooses to route file
access through it. It does not contain a determined process (which could call
open() directly, or shell out). Real isolation needs OS-level controls — say so
plainly in the paper rather than overclaiming.
"""

from __future__ import annotations

import os
from typing import IO, Iterable, List, Optional, Sequence


class UnsafePathError(PermissionError):
    """Raised when a path escapes the allowed roots, or a write is attempted."""


def _real(path: str) -> str:
    """Absolute, symlink-resolved path. Resolution happens before any check."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def is_within(path: str, root: str) -> bool:
    """True if `path` is inside `root` after symlink resolution.

    Uses os.path.commonpath rather than str.startswith so that a sibling
    directory sharing a name prefix (/data vs /data-backup) is not treated as
    contained.
    """
    resolved_path, resolved_root = _real(path), _real(root)
    if resolved_path == resolved_root:
        return True
    try:
        return os.path.commonpath([resolved_path, resolved_root]) == resolved_root
    except ValueError:
        # Different drives / unrelated roots.
        return False


class PathGuard:
    """Confines file access to an allowlist of readable roots.

    read_roots:   directories the agent may read from (lab materials).
    write_root:   the ONLY directory writes are permitted in, if any. When None,
                  the guard is strictly read-only.
    """

    DEFAULT_DENIED = (".git", ".env", "id_rsa", "id_ed25519", ".ssh")

    def __init__(
        self,
        read_roots: Sequence[str],
        write_root: Optional[str] = None,
        denied_names: Iterable[str] = DEFAULT_DENIED,
        allowed_extensions: Optional[Iterable[str]] = None,
    ) -> None:
        """
        denied_names:       directory or file NAMES that may never be touched, at
                            any depth. Checked per path component, so passing
                            "eval" blocks <root>/eval/anything.
        allowed_extensions: when set, ONLY files with these extensions may be
                            read. None means no extension restriction.

        The two together are what let this guard mirror an indexer's allowlist.
        On a real lab corpus that is a privacy control, not tidiness: a cytology
        project's eval/ directory holds slide-ID lists, and its compare*/
        filenames are accession numbers, so a tool that walks the tree freely
        can surface patient identifiers even when it never opens a data file.
        """
        if not read_roots:
            raise ValueError("PathGuard requires at least one readable root.")
        self.read_roots: List[str] = [_real(r) for r in read_roots]
        self.write_root: Optional[str] = _real(write_root) if write_root else None
        self.denied_names = tuple(denied_names)
        self.allowed_extensions: Optional[tuple] = (
            tuple(e.lower() if e.startswith(".") else "." + e.lower()
                  for e in allowed_extensions)
            if allowed_extensions is not None
            else None
        )

    @classmethod
    def from_env(
        cls,
        read_roots: Sequence[str],
        write_root: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> "PathGuard":
        """Build a guard from the SAME environment variables the indexer uses.

        LAB_RAG_SKIP_DIRS and LAB_RAG_EXTENSIONS are read by lab_rag.py when
        building the vector index. Reading them here too means one setting
        controls what gets indexed AND what the agent's file tools may touch, so
        the two cannot drift apart and leave the agent able to read something
        that was deliberately kept out of the index.
        """
        environ = os.environ if env is None else env

        skip = [
            d.strip() for d in (environ.get("LAB_RAG_SKIP_DIRS") or "").split(",")
            if d.strip()
        ]
        exts_raw = (environ.get("LAB_RAG_EXTENSIONS") or "").strip()
        exts = [e.strip() for e in exts_raw.split(",") if e.strip()] or None

        return cls(
            read_roots,
            write_root=write_root,
            denied_names=tuple(cls.DEFAULT_DENIED) + tuple(skip),
            allowed_extensions=exts,
        )

    # -- checks ---------------------------------------------------------------

    def _check_denied(self, path: str) -> None:
        parts = set(_real(path).split(os.sep))
        hit = parts.intersection(self.denied_names)
        if hit:
            raise UnsafePathError(
                f"Refusing to access {path!r}: contains protected component {sorted(hit)!r}"
            )

    def _extension_denied(self, name: str) -> bool:
        if self.allowed_extensions is None:
            return False
        return os.path.splitext(name)[1].lower() not in self.allowed_extensions

    def _check_extension(self, path: str) -> None:
        """Refuse a file type outside the allowlist, when one is configured.

        Directory exclusion alone is not enough. A slide-ID list dropped
        anywhere in the tree is a .txt file, and if .txt is not on the allowlist
        it cannot be read regardless of where it sits.
        """
        if self.allowed_extensions is None:
            return
        # Directories carry no extension and are governed by denied_names.
        if os.path.isdir(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.allowed_extensions:
            raise UnsafePathError(
                f"Refusing to read {path!r}: extension {ext or '(none)'!r} is not in "
                f"the allowed set {self.allowed_extensions!r}"
            )

    def check_readable(self, path: str) -> str:
        """Return the resolved path if it may be read; else raise."""
        self._check_denied(path)
        self._check_extension(path)
        if any(is_within(path, root) for root in self.read_roots):
            return _real(path)
        raise UnsafePathError(
            f"Refusing to read {path!r}: outside allowed roots {self.read_roots!r}"
        )

    def check_writable(self, path: str) -> str:
        """Return the resolved path if it may be written; else raise.

        Strictly read-only guards always raise. This is the check that enforces
        'never modify original research data'.
        """
        if self.write_root is None:
            raise UnsafePathError(
                f"Refusing to write {path!r}: this guard is read-only. "
                "Lab materials must never be modified."
            )
        self._check_denied(path)
        if is_within(path, self.write_root):
            return _real(path)
        raise UnsafePathError(
            f"Refusing to write {path!r}: writes are confined to {self.write_root!r}"
        )

    # -- guarded operations ---------------------------------------------------

    def open_read(self, path: str, encoding: str = "utf-8", errors: str = "ignore") -> IO:
        """Open a file for reading only. Write modes are impossible here."""
        return open(self.check_readable(path), "r", encoding=encoding, errors=errors)

    def read_text(self, path: str, encoding: str = "utf-8", errors: str = "ignore") -> str:
        with self.open_read(path, encoding=encoding, errors=errors) as handle:
            return handle.read()

    def walk_readable(self, root: Optional[str] = None):
        """os.walk restricted to allowed roots, skipping hidden and denied dirs.

        Yields (dirpath, dirnames, filenames) exactly like os.walk, so it can
        replace os.walk in indexing code with no other changes.
        """
        roots = [self.check_readable(root)] if root else list(self.read_roots)
        for base in roots:
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not d.startswith(".") and d not in self.denied_names
                ]
                # Filenames are filtered too, not just directories. Listing a
                # file the guard would refuse to open advertises its existence,
                # and on a real corpus the filename can itself be the sensitive
                # part: an accession number in the name leaks whether or not
                # anything ever reads the contents.
                visible = [
                    f
                    for f in filenames
                    if f not in self.denied_names and not self._extension_denied(f)
                ]
                yield dirpath, dirnames, visible


# --- Capability declaration --------------------------------------------------
# Mirrors the can/can't table in the pitch deck and design doc. Kept in code so
# the documented posture and the enforced posture stay in sync, and so the paper
# can quote a single authoritative source.

CAPABILITIES = {
    "can": (
        "search and read files within allowlisted lab directories",
        "summarize retrieved content and cite source paths",
        "write only inside an explicitly designated scratch directory",
    ),
    # ENFORCED by code in this module, with tests.
    "cannot": (
        "edit, overwrite, or delete original lab files",
        "read protected paths (.git, .env, SSH keys)",
        "escape the allowlist via symlink or '..' traversal",
    ),
    # NOT enforced. Listed separately and deliberately: an unenforced item sitting
    # in the "cannot" tuple is a false assurance, and a false assurance about data
    # handling is worse than no assurance at all.
    "NOT enforced": (
        "network egress is not blocked at any layer",
        "THE SLACK INTERFACE IS EGRESS. Answers, retrieved file paths, and — in a "
        "workflow trace — verbatim lines of lab source code are sent to Slack, a "
        "third-party cloud service. Model inference is local; the chat surface is "
        "not. Any deployment over real lab data must either accept that or use a "
        "local-only interface.",
        "HPC job submission is unconstrained (no submission code exists yet, so "
        "this is vacuous rather than a guarantee)",
        "reads that bypass PathGuard: lab_rag.py and lab_query.py open files "
        "directly, so the allowlist covers only code routed through this module",
        "final scientific judgement — a design posture, not a code property",
    ),
}


def describe_posture(guard: PathGuard) -> str:
    """Human-readable summary, for logs, the Slack /health path, and the paper.

    Prints what is NOT enforced as prominently as what is. Anyone deciding
    whether to point this at real patient data needs the second list more than
    the first.
    """
    mode = "READ-ONLY" if guard.write_root is None else f"read + scratch writes ({guard.write_root})"
    lines = [f"Access mode: {mode}", "Readable roots:"]
    lines += [f"  - {root}" for root in guard.read_roots]
    lines.append("ENFORCED — cannot: " + "; ".join(CAPABILITIES["cannot"]))
    lines.append("NOT ENFORCED:")
    lines += [f"  ! {item}" for item in CAPABILITIES["NOT enforced"]]
    return "\n".join(lines)
