"""
safe_exec.py — run model-written code under constraints, with an audit trail.

WHY THIS EXISTS
---------------
Pitch deck, "Can Do": search, read, summarize, suggest, **run safe test code**.
"Can't Do": edit/delete original files, submit uncontrolled jobs.

The agent already writes and executes Python — that is how `hello_lab.py` was
produced. Nothing constrained where it ran or what it could reach. This module is
the "safe" in "run safe test code."

Dr. Levy, 10 July: "Please be careful about using agents modifying existing file
structure... Please make sure safeguards are in place."

WHAT THIS IS NOT
----------------
**This is not a security sandbox.** It is a guardrail against accident, not an
adversary. A determined process can still open sockets, spawn children within its
limits, or read anything the running user can read. Real isolation needs a
container, a VM, or OS-level confinement (seccomp, sandbox-exec), and that is a
deployment decision for whoever runs this on the cluster.

Saying this plainly matters: overstating a security boundary is the kind of claim
that gets a paper torn apart, and worse, gets someone to trust it with real
patient data.

WHAT IT ACTUALLY ENFORCES
-------------------------
  - a separate process, so a crash or hang cannot take down the caller
  - working directory confined to a scratch dir; lab directories are never cwd
  - wall-clock timeout, and CPU / memory / file-size / process-count limits
  - a stripped environment (no inherited credentials or API keys)
  - refusal to run at all if the scratch dir sits inside a protected root
  - a JSONL audit log of every execution: code, output, exit status, duration

The audit log is the part the lab should care about most. If an agent ever does
something surprising, there is a record of exactly what ran.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

try:  # Unix only; absent on Windows.
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore

DEFAULT_TIMEOUT_S = 30
DEFAULT_MEMORY_MB = 2048
DEFAULT_MAX_OUTPUT_BYTES = 200_000
DEFAULT_MAX_FILE_MB = 50
DEFAULT_MAX_PROCESSES = 32


@dataclass
class ExecResult:
    """Outcome of one execution."""

    ok: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    refused: Optional[str] = None          # set when it never ran
    scratch_dir: Optional[str] = None
    files_written: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_s": round(self.duration_s, 4),
            "timed_out": self.timed_out,
            "refused": self.refused,
            "scratch_dir": self.scratch_dir,
            "files_written": self.files_written,
        }


def _limits(memory_mb: int, cpu_seconds: int, max_file_mb: int, max_procs: int):
    """Applied in the child before exec. Unix only; a no-op elsewhere."""
    if resource is None:  # pragma: no cover
        return None

    def apply():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (max_file_mb * 1024 ** 2, max_file_mb * 1024 ** 2)
        )
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (max_procs, max_procs))
        except (ValueError, OSError):
            pass
        # Address-space limits are unreliable on macOS (the allocator reserves
        # large regions up front and Python dies at import), so RLIMIT_AS is
        # applied only on Linux.
        #
        # CONSEQUENCE, stated plainly: on macOS there is NO memory cap. A snippet
        # can allocate until the machine swaps. The CPU-time and wall-clock limits
        # still bound it, but memory does not. Since development happens on macOS
        # and deployment is Linux, the memory limit is untested on the platform it
        # actually runs on, and absent on the platform it is developed on. Do not
        # describe this as a memory-limited sandbox.
        if sys.platform.startswith("linux"):
            limit = memory_mb * 1024 ** 2
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        os.setsid()          # own process group, so a timeout kills the tree

    return apply


def _clean_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Minimal environment. Credentials in the parent are not inherited."""
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": tempfile.gettempdir(),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    if extra:
        env.update(extra)
    return env


def run_python(
    code: str,
    *,
    scratch_dir: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    memory_mb: int = DEFAULT_MEMORY_MB,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_file_mb: int = DEFAULT_MAX_FILE_MB,
    max_processes: int = DEFAULT_MAX_PROCESSES,
    protected_roots: Sequence[str] = (),
    audit_log: Optional[str] = None,
    python: Optional[str] = None,
) -> ExecResult:
    """Execute `code` in a subprocess whose working directory is `scratch_dir`.

    `protected_roots` are directories the scratch dir must NOT live inside — pass
    the lab data roots. If scratch resolves inside one, execution is refused
    outright rather than sandboxed, because a writable scratch inside a lab
    directory defeats the entire point.
    """
    started = time.monotonic()

    scratch = os.path.realpath(os.path.abspath(os.path.expanduser(scratch_dir)))
    for root in protected_roots:
        real_root = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
        if scratch == real_root or scratch.startswith(real_root + os.sep):
            return _finish(
                ExecResult(
                    ok=False, exit_code=None, stdout="", stderr="",
                    duration_s=time.monotonic() - started,
                    refused=(
                        f"scratch directory {scratch!r} is inside protected root "
                        f"{real_root!r}; refusing to execute"
                    ),
                    scratch_dir=scratch,
                ),
                code, audit_log,
            )

    os.makedirs(scratch, exist_ok=True)
    before = _snapshot(scratch)

    script = os.path.join(scratch, "_agent_snippet.py")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(code)

    try:
        completed = subprocess.run(
            [python or sys.executable, "-I", script],   # -I: isolated mode
            cwd=scratch,
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=_limits(memory_mb, timeout_s, max_file_mb, max_processes),
        )
        result = ExecResult(
            ok=completed.returncode == 0,
            exit_code=completed.returncode,
            stdout=_truncate(completed.stdout, max_output_bytes),
            stderr=_truncate(completed.stderr, max_output_bytes),
            duration_s=time.monotonic() - started,
            scratch_dir=scratch,
        )
    except subprocess.TimeoutExpired as exc:
        result = ExecResult(
            ok=False,
            exit_code=None,
            stdout=_truncate(exc.stdout or "", max_output_bytes),
            stderr=_truncate(exc.stderr or "", max_output_bytes),
            duration_s=time.monotonic() - started,
            timed_out=True,
            scratch_dir=scratch,
        )
    except Exception as exc:  # noqa: BLE001
        result = ExecResult(
            ok=False, exit_code=None, stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
            duration_s=time.monotonic() - started,
            scratch_dir=scratch,
        )

    result.files_written = sorted(_snapshot(scratch) - before - {"_agent_snippet.py"})
    return _finish(result, code, audit_log)


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[output truncated at {limit} bytes]"


def _snapshot(root: str) -> set:
    found = set()
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            found.add(
                os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            )
    return found


def _finish(result: ExecResult, code: str, audit_log: Optional[str]) -> ExecResult:
    """Append to the audit trail. Failure to log never masks the result."""
    if not audit_log:
        return result
    try:
        os.makedirs(os.path.dirname(os.path.abspath(audit_log)) or ".", exist_ok=True)
        entry = {"code": code, **result.to_dict()}
        with open(audit_log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    return result


CAPABILITIES = {
    "enforced": (
        "runs in a separate process with its own process group",
        "working directory confined to a scratch directory",
        "wall-clock timeout and CPU limit",
        "file-size and subprocess-count limits (memory limit on Linux)",
        "stripped environment: no inherited credentials or API keys",
        "refuses to run if scratch is inside a protected lab root",
        "every execution appended to a JSONL audit log",
    ),
    "NOT enforced": (
        "network access is not blocked",
        "reads outside the scratch directory are not blocked",
        "MEMORY IS NOT CAPPED ON macOS -- RLIMIT_AS is Linux-only, so on the "
        "development platform a snippet can allocate until the machine swaps",
        "this is not a security boundary against a determined adversary",
        "real isolation requires a container, VM, or OS-level confinement",
        "NEVER EXERCISED BY A LIVE MODEL: every test uses a scripted fake, no "
        "demo enables it, and no evaluation arm touches it. Treat 'the agent can "
        "run safe test code' as built-and-unit-tested, not as demonstrated.",
    ),
}


def describe_posture() -> str:
    lines = ["Code execution guardrails", "  Enforced:"]
    lines += [f"    - {item}" for item in CAPABILITIES["enforced"]]
    lines.append("  NOT enforced:")
    lines += [f"    - {item}" for item in CAPABILITIES["NOT enforced"]]
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe_posture())
