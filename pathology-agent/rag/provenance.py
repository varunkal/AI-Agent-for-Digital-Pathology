"""
provenance.py — record exactly what produced every result.

WHY THIS EXISTS
---------------
A reviewer's first question about any number is "what, precisely, was run?" Until
now nothing recorded it: no temperature, no seed, no model digest, no library
versions, no chunk settings, no commit. Two runs a week apart could differ for
reasons nobody could reconstruct, and the paper could not honestly state its own
configuration.

This module captures that fingerprint once per run and stamps it into the logs,
so any number in the paper can be traced back to the exact conditions that
produced it.

DETERMINISM
-----------
Generation is sampled, so the same question can give different answers. For the
confirmatory comparison that is fatal: an arm difference could be sampling noise.
`SAMPLING_OPTIONS` pins temperature to 0 and fixes the seed. Replicates are still
worth running (a pinned seed does not guarantee bit-identical output across
model or runtime versions), but the intended configuration is now explicit and
recorded rather than left to defaults.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from typing import Any, Dict, Optional

# Pinned sampling configuration. Recorded in every run record.
#   temperature 0  -> greedy decoding, removes sampling variance
#   seed           -> fixed so any residual randomness is reproducible
#   num_ctx        -> set explicitly; Ollama's default silently truncates long
#                     prompts, which would drop retrieved context without error
SAMPLING_OPTIONS: Dict[str, Any] = {
    "temperature": 0,
    "seed": 0,
    "num_ctx": 8192,
}


def _run(cmd: list) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _package_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def _git_sha(path: str) -> Optional[str]:
    return _run(["git", "-C", path, "rev-parse", "--short", "HEAD"])


def _git_dirty(path: str) -> Optional[bool]:
    status = _run(["git", "-C", path, "status", "--porcelain"])
    return None if status is None else bool(status.strip())


def model_digest(model: str) -> Optional[str]:
    """The model's content ID, so 'qwen2.5-coder:3b' is pinned to a build.

    A tag is mutable — the same name can point at different weights over time, so
    the tag alone does not identify what ran. `ollama show` does not print a
    digest; `ollama list` exposes it in the ID column, which is what we use.
    """
    raw = _run(["ollama", "list"])
    if not raw:
        return None
    wanted = model if ":" in model else f"{model}:latest"
    for line in raw.splitlines()[1:]:                     # skip the header row
        parts = line.split()
        if len(parts) >= 2 and parts[0] in (model, wanted):
            return parts[1]
    return None


def model_details(model: str) -> Dict[str, Optional[str]]:
    """Architecture, parameter count, quantization and context length.

    Quantization matters and is easy to forget: a 3B model at Q4_K_M is not the
    same system as the same model at full precision, and a replication attempt
    needs to know which one produced the numbers.
    """
    raw = _run(["ollama", "show", model])
    details: Dict[str, Optional[str]] = {
        "architecture": None,
        "parameters": None,
        "quantization": None,
        "context_length": None,
    }
    if not raw:
        return details
    keys = {
        "architecture": "architecture",
        "parameters": "parameters",
        "quantization": "quantization",
        "context length": "context_length",
    }
    for line in raw.splitlines():
        stripped = line.strip()
        for label, key in keys.items():
            if stripped.lower().startswith(label):
                value = stripped[len(label):].strip()
                if value:
                    details[key] = value
    return details


def collect(
    *,
    chat_model: Optional[str] = None,
    embed_model: Optional[str] = None,
    chroma_dir: Optional[str] = None,
    collection: Optional[str] = None,
    top_k: Optional[int] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    repo_paths: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the run fingerprint. Every field is best-effort; None means unknown."""
    record: Dict[str, Any] = {
        "sampling": dict(SAMPLING_OPTIONS),
        "models": {
            "chat": chat_model,
            "chat_digest": model_digest(chat_model) if chat_model else None,
            "chat_details": model_details(chat_model) if chat_model else {},
            "embed": embed_model,
            "embed_digest": model_digest(embed_model) if embed_model else None,
        },
        "retrieval": {
            "collection": collection,
            "chroma_dir": chroma_dir,
            "top_k": top_k,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
        "software": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "ollama_client": (_run(["ollama", "--version"]) or "").split()[-1] or None,
            "chromadb": _package_version("chromadb"),
            "ollama_py": _package_version("ollama"),
        },
        "code": {},
    }

    for label, path in (repo_paths or {}).items():
        if path and os.path.isdir(path):
            record["code"][label] = {
                "git_sha": _git_sha(path),
                "uncommitted_changes": _git_dirty(path),
            }

    if extra:
        record.update(extra)
    return record


def from_config(config: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Convenience wrapper: build a fingerprint from lab_query.config()."""
    return collect(
        chat_model=config.get("CHAT_MODEL"),
        embed_model=config.get("EMBED_MODEL"),
        chroma_dir=config.get("CHROMA_DIR"),
        collection=config.get("COLLECTION_NAME"),
        top_k=config.get("TOP_K"),
        **kwargs,
    )


def describe(record: Dict[str, Any]) -> str:
    """Short human-readable summary, for run headers and the methods section."""
    models = record.get("models", {})
    retrieval = record.get("retrieval", {})
    sampling = record.get("sampling", {})
    lines = [
        f"model      {models.get('chat')}  id={models.get('chat_digest') or 'unknown'}"
        f"  quant={(models.get('chat_details') or {}).get('quantization') or '?'}"
        f"  params={(models.get('chat_details') or {}).get('parameters') or '?'}",
        f"embed      {models.get('embed')}",
        f"sampling   temperature={sampling.get('temperature')} seed={sampling.get('seed')} "
        f"num_ctx={sampling.get('num_ctx')}",
        f"retrieval  top_k={retrieval.get('top_k')} chunk={retrieval.get('chunk_size')}"
        f"/{retrieval.get('chunk_overlap')} collection={retrieval.get('collection')}",
    ]
    for label, info in (record.get("code") or {}).items():
        flag = " (UNCOMMITTED CHANGES)" if info.get("uncommitted_changes") else ""
        lines.append(f"code       {label} @ {info.get('git_sha')}{flag}")
    return "\n".join(lines)


def warnings(record: Dict[str, Any]) -> list:
    """Conditions that would undermine a reported result."""
    problems = []
    if record.get("sampling", {}).get("temperature") not in (0, 0.0):
        problems.append("temperature is not 0 — results will vary between runs")
    if not record.get("models", {}).get("chat_digest"):
        problems.append("model digest unknown — the exact weights cannot be pinned")
    for label, info in (record.get("code") or {}).items():
        if info.get("uncommitted_changes"):
            problems.append(
                f"{label} has uncommitted changes — the run is not reproducible "
                "from the recorded commit"
            )
        if not info.get("git_sha"):
            problems.append(f"{label} has no git SHA — code version unknown")
    return problems


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lab_query

    fingerprint = from_config(
        lab_query.config(),
        chunk_size=800,
        chunk_overlap=100,
        repo_paths={
            "harness": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "lab_rag": os.path.expanduser("~/labagent"),
        },
    )
    print(describe(fingerprint))
    issues = warnings(fingerprint)
    if issues:
        print("\nWARNINGS:")
        for issue in issues:
            print(f"  - {issue}")
    print("\n" + json.dumps(fingerprint, indent=2))
