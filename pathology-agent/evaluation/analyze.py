"""
analyze.py — compute every metric in EVALUATION_PROTOCOL.md §4 from run logs.

Pure standard library: no numpy, scipy, or pandas. That keeps the analysis
runnable anywhere (including a login node with a bare Python) and makes the
paper's numbers trivially reproducible by a reviewer.

Usage
-----
  python analyze.py --tasks tasks.jsonl \
                    --runs runs/agent.jsonl runs/generic.jsonl \
                    --manifest file_manifest.txt \
                    --json results.json

Run-log record schema (one JSON object per line), produced by run_eval.py:
  {
    "task_id":     "loc-001",
    "arm":         "agent" | "generic" | "human",
    "answer":      "...",
    "sources":     ["notebooks/qc.ipynb", ...],   # retrieved, best first
    "cited_paths": ["qc.ipynb", ...],             # paths named in the prose
    "abstained":   false,
    "latency_s":   4.21
  }
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks import CATEGORIES, Task, load_tasks, scorable, validate  # noqa: E402


# --- Statistics --------------------------------------------------------------


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Preferred over the normal approximation because it behaves sensibly at small
    n and near 0/1 — both of which this study will hit (n≈30, some rates near 1).
    Deterministic, so no seed to report.
    """
    if total == 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    ) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def mcnemar_exact(only_first: int, only_second: int) -> float:
    """Two-sided exact McNemar p-value for paired binary outcomes.

    only_first  = tasks where arm A succeeded and arm B failed
    only_second = tasks where arm B succeeded and arm A failed

    Concordant pairs carry no information and are excluded by construction. The
    exact binomial form is used rather than the chi-square approximation because
    the discordant count here will be small.
    """
    discordant = only_first + only_second
    if discordant == 0:
        return 1.0
    smaller = min(only_first, only_second)
    tail = sum(math.comb(discordant, i) for i in range(smaller + 1))
    return min(1.0, 2.0 * tail / (2 ** discordant))


# --- Loading -----------------------------------------------------------------


def load_runs(path: str) -> List[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON — {exc}") from exc
    return records


def load_manifest(path: str) -> Set[str]:
    """Real file paths captured at index time (protocol §5 step 1).

    Using a frozen manifest rather than walking the filesystem at analysis time
    is deliberate: the lab is actively archiving data, so paths move. The
    manifest is what makes the hallucination number reproducible later.
    """
    with open(path, "r", encoding="utf-8") as handle:
        return {
            line.strip().replace("\\", "/")
            for line in handle
            if line.strip() and not line.startswith("#")
        }


def manifest_from_directory(root: str) -> Set[str]:
    """Build a manifest by walking `root`. Use to CREATE a manifest, not to score."""
    root = os.path.abspath(root)
    paths = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            paths.add(os.path.relpath(full, root).replace(os.sep, "/"))
    return paths


# --- Matching helpers --------------------------------------------------------


def _normalize(path: str) -> str:
    """Normalize separators and strip a single leading './' — nothing more.

    Deliberately does NOT use lstrip("./"), which strips *characters* and so
    silently rewrites '../../etc/x.py' into 'etc/x.py'. That turned a path
    escaping the corpus into an apparently-valid relative path, on the primary
    metric's code path.
    """
    text = (path or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def _escapes_root(path: str) -> bool:
    """True if the path contains a '..' segment, i.e. leaves the corpus root.

    Such a path cannot be checked against a root-relative manifest, so it is
    neither a match nor an existing file. Treating it as either would let a path
    outside the indexed corpus score as valid.
    """
    return ".." in path.split("/")


def path_matches(candidate: str, expected: str, *, lenient: bool = False) -> bool:
    """Compare a produced path against a ground-truth path.

    STRICT (default): exact match, or one is a suffix of the other on a path
    segment boundary AND the shorter side has more than one segment. A bare
    basename does NOT match a full path, because in a per-cohort directory tree
    'qc.ipynb' is ambiguous between cohorts and crediting it would reward an
    answer that never identified which cohort it meant.

    LENIENT: also accepts a bare basename. Report this only as a sensitivity
    analysis. It is more permissive in the direction that flatters the system, so
    it must never be the primary scoring rule.
    """
    left, right = _normalize(candidate), _normalize(expected)
    if not left or not right:
        return False
    # A path with a '..' segment escapes the corpus root and cannot be validated
    # against a root-relative manifest, so it never counts as a match.
    if _escapes_root(left) or _escapes_root(right):
        return False
    if left == right:
        return True

    suffix_hit = left.endswith("/" + right) or right.endswith("/" + left)
    if not suffix_hit:
        return False

    shorter = right if len(right) < len(left) else left
    if "/" in shorter:
        return True                     # multi-segment suffix: unambiguous enough
    return lenient                      # bare basename: only under leniency


def corpus_referenced_paths(root: str) -> Set[str]:
    """Path-like strings that appear INSIDE the corpus text.

    Code routinely names files that are not themselves in the corpus:
    `niche_discovery.py` writes `results/niche_assignments.csv`, and a notebook
    reads `/data/cohortA/clinical_outcomes.csv`. When the model cites those, it is
    accurately reporting what the code says — it did not invent them.

    Scoring that as hallucination conflates "made something up" with "correctly
    read a reference to a file that is not indexed", and would have reported a
    50% fabrication rate that was mostly an artifact.
    """
    import re as _re

    pattern = _re.compile(
        r"[\w./\\-]*\w\.(?:py|ipynb|md|txt|json|ya?ml|csv|tsv|sh|R|rds|h5ad|h5|pkl|cfg|ini|toml)\b",
        _re.IGNORECASE,
    )
    found: Set[str] = set()
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            try:
                with open(os.path.join(dirpath, name), "r", errors="ignore") as handle:
                    for match in pattern.finditer(handle.read()):
                        found.add(_normalize(match.group(0)).lstrip("/"))
            except Exception:
                continue
    return found


# How a cited path relates to reality. Only FABRICATED is a true hallucination.
CITATION_EXACT = "exact"            # full path resolves to a real file
CITATION_BASENAME = "basename"      # file exists; path given incompletely
CITATION_REFERENCED = "referenced"  # named inside corpus text, not itself a file
CITATION_FABRICATED = "fabricated"  # appears nowhere — invented


def classify_citation(
    candidate: str,
    manifest: Set[str],
    referenced: Optional[Set[str]] = None,
) -> str:
    """Classify one cited path. Reported separately rather than pooled."""
    normalized = _normalize(candidate)
    if not normalized or _escapes_root(normalized):
        return CITATION_FABRICATED
    if path_exists(candidate, manifest):
        return CITATION_EXACT
    # Basename credit applies ONLY to a bare filename. A full path that merely
    # shares a basename with a real file ('made/up/dir/utils.py' vs
    # 'src/utils.py') asserts a directory structure that does not exist — that is
    # a fabrication, not an incomplete citation.
    if "/" not in normalized and path_exists(candidate, manifest, lenient=True):
        return CITATION_BASENAME
    if referenced:
        stripped = normalized.lstrip("/")
        if stripped in referenced or any(
            ref.endswith("/" + stripped) or stripped.endswith("/" + ref)
            for ref in referenced
        ):
            return CITATION_REFERENCED
    return CITATION_FABRICATED


def path_exists(candidate: str, manifest: Set[str], *, lenient: bool = False) -> bool:
    """True if a cited path corresponds to a real file in the manifest.

    STRICT (default): the path must resolve to a real relative path, or be a
    genuine multi-segment suffix of one.

    Bare-basename matching is NOT accepted by default. It was, and it broke the
    metric: with 'src/utils.py' in the manifest, the invented path
    'totally/made/up/dir/utils.py' scored as existing. Real lab corpora are full
    of README.md, config.yaml and utils.py, so basename matching drives the
    hallucination rate toward zero artifactually — in the direction that flatters
    the system.
    """
    normalized = _normalize(candidate)
    if not normalized or _escapes_root(normalized):
        return False
    if normalized in manifest:
        return True
    if "/" in normalized and any(real.endswith("/" + normalized) for real in manifest):
        return True
    if lenient:
        basename = os.path.basename(normalized)
        return any(os.path.basename(real) == basename for real in manifest)
    return False


# --- Per-task scoring --------------------------------------------------------


def ordered_chunk_sources(record: dict) -> Optional[List[str]]:
    """Source path of each retrieved chunk, in rank order, WITHOUT deduplication.

    Rank-ordered chunk sources are what "top-k retrieval" actually means. Using
    the deduplicated `sources` list would silently change the definition: with
    TOP_K=5, five chunks usually collapse to fewer than five distinct files, so a
    "top-5" window over unique sources degenerates into "was the file retrieved at
    all" while still carrying a rank-5 label.

    Returns None ONLY when the log has no `chunks` key at all (manual arms have no
    retrieval step), so retrieval metrics report as not-applicable rather than
    being quietly computed from something that means something else.

    An empty chunk list returns [] — NOT None. A retrieval that returned nothing
    is the most important kind of retrieval failure and must score 0, not
    not-applicable. Treating it as None dropped the task out of the denominator
    and inflated the retrieval rate.
    """
    if "chunks" not in record:
        return None
    chunks = record.get("chunks") or []
    return [_normalize(chunk.get("source", "")) for chunk in chunks]


# How many candidate paths any arm is allowed to offer before scoring. Arm C can
# surface five retrieved files while a human names one, so an uncapped
# "was it anywhere in the output" metric silently compares recall@5 against
# recall@1 and favours the intervention. Cap every arm at the same budget.
CANDIDATE_BUDGET = 3


def score_task(
    task: Task,
    record: dict,
    manifest: Optional[Set[str]],
    *,
    budget: int = CANDIDATE_BUDGET,
    referenced: Optional[Set[str]] = None,
) -> dict:
    """Score one (task, run) pair. Returns per-task outcomes for aggregation."""
    # Infrastructure failures are NOT model failures. A crashed or timed-out run
    # previously fell through with no sources and scored as a miss.
    if record.get("error"):
        return {
            "task_id": task.id,
            "category": task.category,
            "participant_id": record.get("participant_id"),
            "error": record["error"],
            "top1": None,
            "top5": None,
            "hit_at_1": None,
            "hit_at_budget": None,
            "file_identified": None,
            "retrieval_measured": False,
            "n_chunks": 0,
            "n_unique_sources": 0,
            "n_candidates": 0,
            "abstained": None,
            "abstention_correct": None,
            "cited_checked": 0,
            "cited_hallucinated": 0,
            "citation_kinds": {},
            "any_hallucinated": None,
            "cited_any": None,
            "latency_s": None,
        }

    sources = [_normalize(s) for s in record.get("sources") or []]
    cited = [_normalize(p) for p in record.get("cited_paths") or []]
    abstained = bool(record.get("abstained"))

    chunk_sources = ordered_chunk_sources(record)

    def _hits(candidates: Sequence[str]) -> bool:
        return any(
            path_matches(candidate, expected)
            for expected in task.expected_paths
            for candidate in candidates
        )

    def retrieved_at(k: int) -> Optional[bool]:
        """Rank-k retrieval hit, chunk-level. None when not measurable."""
        if not task.expected_paths or chunk_sources is None:
            return None
        return _hits(chunk_sources[:k])

    # Candidate list the user effectively received, in priority order: paths the
    # answer actually named first, then anything else that was surfaced.
    ordered_candidates: List[str] = []
    for path in cited + sources:
        if path and path not in ordered_candidates:
            ordered_candidates.append(path)

    if task.expected_paths:
        hit_at_1: Optional[bool] = _hits(ordered_candidates[:1])
        hit_at_budget: Optional[bool] = _hits(ordered_candidates[:budget])
        # Retained for continuity, but budget-capped: an uncapped version is not
        # comparable across arms.
        file_identified: Optional[bool] = hit_at_budget
    else:
        hit_at_1 = hit_at_budget = file_identified = None

    if manifest is None or not cited:
        hallucinated, cited_checked = 0, 0
        any_hallucinated: Optional[bool] = None
        citation_kinds: Dict[str, int] = {}
    else:
        kinds = [classify_citation(path, manifest, referenced) for path in cited]
        citation_kinds = {k: kinds.count(k) for k in set(kinds)}
        cited_checked = len(kinds)
        # ONLY genuine fabrication counts. A basename-only path names a real
        # file, and a path read out of the corpus text was not invented.
        hallucinated = kinds.count(CITATION_FABRICATED)
        # Task-level primary: a genuine Bernoulli trial per answer, unlike the
        # pooled citation-level rate whose observations are not independent.
        any_hallucinated = hallucinated > 0

    return {
        "task_id": task.id,
        "category": task.category,
        "participant_id": record.get("participant_id"),
        "error": None,
        "top1": retrieved_at(1),
        "top5": retrieved_at(5),
        "hit_at_1": hit_at_1,
        "hit_at_budget": hit_at_budget,
        "file_identified": file_identified,
        "retrieval_measured": chunk_sources is not None,
        "n_chunks": len(chunk_sources) if chunk_sources is not None else 0,
        "n_unique_sources": len(set(sources)),
        "n_candidates": len(ordered_candidates),
        "abstained": abstained,
        "abstention_correct": abstained == task.expect_abstention,
        "cited_checked": cited_checked,
        "cited_hallucinated": hallucinated,
        "citation_kinds": citation_kinds,
        "any_hallucinated": any_hallucinated,
        # Guards against the metric rewarding vagueness: an answer citing nothing
        # cannot hallucinate a path.
        "cited_any": bool(cited),
        "latency_s": record.get("latency_s"),
    }


# --- Aggregation -------------------------------------------------------------


def _rate(successes: int, total: int) -> dict:
    low, high = wilson_interval(successes, total)
    return {
        "n": total,
        "successes": successes,
        "rate": (successes / total) if total else None,
        "ci95": [round(low, 4), round(high, 4)] if total else None,
    }


def aggregate(scored: Sequence[dict]) -> dict:
    """Roll per-task outcomes into the protocol's headline metrics.

    Infrastructure errors are excluded from every rate and counted separately: an
    Ollama timeout is not a model failure. Distinct participants are counted so
    pseudo-replication is visible rather than hidden inside n.
    """
    errored = [s for s in scored if s.get("error")]
    usable = [s for s in scored if not s.get("error")]

    top1 = [s for s in usable if s["top1"] is not None]
    top5 = [s for s in usable if s["top5"] is not None]
    hit1 = [s for s in usable if s.get("hit_at_1") is not None]
    hitb = [s for s in usable if s.get("hit_at_budget") is not None]

    undocumented = [s for s in usable if s["category"] == "undocumented"]
    documented = [s for s in usable if s["category"] != "undocumented"]

    cited_total = sum(s["cited_checked"] for s in usable)
    cited_bad = sum(s["cited_hallucinated"] for s in usable)
    kind_totals: Dict[str, int] = {}
    for entry in usable:
        for kind, count in (entry.get("citation_kinds") or {}).items():
            kind_totals[kind] = kind_totals.get(kind, 0) + count
    task_level = [s for s in usable if s.get("any_hallucinated") is not None]

    latencies = [s["latency_s"] for s in usable if isinstance(s["latency_s"], (int, float))]

    participants = {s.get("participant_id") for s in usable if s.get("participant_id")}
    distinct_tasks = {s["task_id"] for s in usable}

    metrics = {
        "synthetic": any(entry.get("synthetic") for entry in scored),
        "n_records": len(scored),
        "n_tasks": len(usable),
        "n_distinct_tasks": len(distinct_tasks),
        "n_participants": len(participants),
        "n_errors": len(errored),
        # PRIMARY, comparable across arms — budget-capped so every arm gets the
        # same number of candidate guesses.
        "hit_at_1": _rate(sum(1 for s in hit1 if s["hit_at_1"]), len(hit1)),
        "hit_at_budget": _rate(sum(1 for s in hitb if s["hit_at_budget"]), len(hitb)),
        "candidate_budget": CANDIDATE_BUDGET,
        "mean_candidates_offered": (
            round(statistics.fmean([s.get("n_candidates", 0) for s in usable]), 2)
            if usable
            else None
        ),
        # Retrieval diagnostics: only where a retrieval step exists.
        "top1_accuracy": _rate(sum(1 for s in top1 if s["top1"]), len(top1)),
        "top5_accuracy": _rate(sum(1 for s in top5 if s["top5"]), len(top5)),
        "retrieval_measured_n": sum(1 for s in usable if s.get("retrieval_measured")),
        "mean_unique_sources": (
            round(statistics.fmean([s["n_unique_sources"] for s in usable]), 2)
            if usable
            else None
        ),
        # Task-level primary (one Bernoulli trial per answer).
        "answers_with_any_hallucination": _rate(
            sum(1 for s in task_level if s["any_hallucinated"]), len(task_level)
        ),
        # Citation-level secondary: pooled, non-independent. See caveat in report.
        "path_hallucination_rate": _rate(cited_bad, cited_total),
        "citation_breakdown": kind_totals,
        # Guards against the hallucination rate being gamed by vagueness.
        "citation_rate": _rate(
            sum(1 for s in usable if s.get("cited_any")), len(usable)
        ),
        "correct_abstention_rate": _rate(
            sum(1 for s in undocumented if s["abstained"]), len(undocumented)
        ),
        "false_abstention_rate": _rate(
            sum(1 for s in documented if s["abstained"]), len(documented)
        ),
        "latency_s": {
            "n": len(latencies),
            "mean": round(statistics.fmean(latencies), 3) if latencies else None,
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "min": round(min(latencies), 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
        },
        "by_category": {},
    }

    for category in CATEGORIES:
        subset = [s for s in usable if s["category"] == category]
        if not subset:
            continue
        sub_top5 = [s for s in subset if s["top5"] is not None]
        sub_hit = [s for s in subset if s.get("hit_at_budget") is not None]
        metrics["by_category"][category] = {
            "n": len(subset),
            "hit_at_budget": _rate(
                sum(1 for s in sub_hit if s["hit_at_budget"]), len(sub_hit)
            ),
            "top5_accuracy": _rate(sum(1 for s in sub_top5 if s["top5"]), len(sub_top5)),
            "abstention_correct": _rate(
                sum(1 for s in subset if s["abstention_correct"]), len(subset)
            ),
        }
    return metrics


def _index_unique(scored: Sequence[dict]) -> Tuple[Dict[str, dict], List[str]]:
    """Index by task id, refusing to silently overwrite duplicates.

    A dict comprehension keyed on task_id drops every participant but the last.
    That made a 3-participant arm collapse to 1 in the paired test while
    aggregate() still counted all 3 as independent tasks. Duplicates are now
    excluded from pairing and reported, so the problem is visible.
    """
    counts: Dict[str, int] = {}
    for record in scored:
        counts[record["task_id"]] = counts.get(record["task_id"], 0) + 1
    duplicates = sorted(task_id for task_id, count in counts.items() if count > 1)
    indexed = {
        record["task_id"]: record
        for record in scored
        if counts[record["task_id"]] == 1
    }
    return indexed, duplicates


def compare_arms(
    scored_a: Sequence[dict], scored_b: Sequence[dict], key: str = "hit_at_budget"
) -> dict:
    """Paired comparison of two arms on the same tasks (protocol §6, primary test).

    Defaults to `hit_at_budget` — the budget-capped, cross-arm comparable outcome.
    Passing key="top5" compares chunk-level retrieval, which is meaningful only
    between two arms that both retrieve.

    McNemar assumes ONE observation per cell. Tasks appearing more than once in an
    arm (multiple participants, or a re-run) are excluded from the test and
    reported under `excluded_duplicates`; a clustered analysis is required for
    those, which this function deliberately does not fake.
    """
    by_id_a, dup_a = _index_unique(scored_a)
    by_id_b, dup_b = _index_unique(scored_b)
    shared = sorted(set(by_id_a) & set(by_id_b))

    only_a = only_b = both = neither = 0
    for task_id in shared:
        a_val, b_val = by_id_a[task_id].get(key), by_id_b[task_id].get(key)
        if a_val is None or b_val is None:
            continue
        if a_val and not b_val:
            only_a += 1
        elif b_val and not a_val:
            only_b += 1
        elif a_val and b_val:
            both += 1
        else:
            neither += 1

    discordant = only_a + only_b
    return {
        "metric": key,
        "n_paired": both + neither + only_a + only_b,
        "excluded_duplicates": sorted(set(dup_a) | set(dup_b)),
        "n_discordant": discordant,
        # Below 6 discordant pairs, exact two-sided McNemar cannot reach p<0.05 no
        # matter how lopsided the split. Surfaced so nobody reads a null as
        # evidence of no effect.
        "significance_attainable": discordant >= 6,
        "both_correct": both,
        "both_wrong": neither,
        "only_first": only_a,
        "only_second": only_b,
        "mcnemar_exact_p": round(mcnemar_exact(only_a, only_b), 6),
    }


# --- Reporting ---------------------------------------------------------------


def _fmt_rate(entry: dict) -> str:
    if not entry or entry.get("rate") is None:
        return "n/a (no scorable tasks)"
    low, high = entry["ci95"]
    return (
        f"{entry['rate'] * 100:5.1f}%  "
        f"({entry['successes']}/{entry['n']}, 95% CI {low * 100:.0f}–{high * 100:.0f}%)"
    )


def render_report(per_arm: Dict[str, dict], comparisons: Sequence[dict]) -> str:
    lines: List[str] = []
    for arm, metrics in per_arm.items():
        header = f"\n=== Arm: {arm} ({metrics['n_tasks']} scored records"
        if metrics["n_distinct_tasks"] != metrics["n_tasks"]:
            header += f", {metrics['n_distinct_tasks']} distinct tasks"
        if metrics["n_participants"]:
            header += f", {metrics['n_participants']} participant(s)"
        if metrics["n_errors"]:
            header += f", {metrics['n_errors']} infrastructure error(s) excluded"
        lines.append(header + ") ===")
        if metrics.get("synthetic"):
            lines.append("  *** SYNTHETIC DATA — THESE ARE NOT RESULTS ***")
        if metrics["n_participants"] > 1:
            lines.append(
                "  !! Multiple participants pooled as independent tasks. Rates and"
            )
            lines.append(
                "     intervals below are PSEUDO-REPLICATED; report per-participant."
            )
        b = metrics["candidate_budget"]
        lines.append(f"  Hit@1 (capped)*            {_fmt_rate(metrics['hit_at_1'])}")
        lines.append(f"  Hit@{b} (capped)*            {_fmt_rate(metrics['hit_at_budget'])}")
        lines.append(f"  Mean candidates offered    {metrics['mean_candidates_offered']}")
        if metrics["retrieval_measured_n"]:
            lines.append(
                f"  Top-1 retrieval (chunks)   {_fmt_rate(metrics['top1_accuracy'])}"
            )
            lines.append(
                f"  Top-5 retrieval (chunks)   {_fmt_rate(metrics['top5_accuracy'])}"
            )
            lines.append(
                f"  Mean unique files/query    {metrics['mean_unique_sources']}"
            )
        else:
            lines.append("  Top-k retrieval            n/a (no retrieval step in this arm)")
        lines.append(
            f"  Answers w/ any bad path    {_fmt_rate(metrics['answers_with_any_hallucination'])}"
        )
        lines.append(f"  Path hallucination rate†   {_fmt_rate(metrics['path_hallucination_rate'])}")
        lines.append(f"  Answers citing >=1 path    {_fmt_rate(metrics['citation_rate'])}")
        breakdown = metrics.get("citation_breakdown") or {}
        if breakdown:
            parts = [f"{k}={v}" for k, v in sorted(breakdown.items())]
            lines.append(f"  Citation breakdown         {', '.join(parts)}")
        lines.append(f"  Correct abstention         {_fmt_rate(metrics['correct_abstention_rate'])}")
        lines.append(f"  False abstention           {_fmt_rate(metrics['false_abstention_rate'])}")
        latency = metrics["latency_s"]
        if latency["n"]:
            lines.append(
                f"  Latency (s)                mean {latency['mean']}, "
                f"median {latency['median']}, range {latency['min']}–{latency['max']}"
            )
        if metrics["by_category"]:
            lines.append("  By category:")
            for category, sub in metrics["by_category"].items():
                lines.append(
                    f"    {category:<13} n={sub['n']:<3} "
                    f"hit@{metrics['candidate_budget']} {_fmt_rate(sub['hit_at_budget'])}"
                )

    for comparison in comparisons:
        lines.append(
            f"\n=== Paired comparison ({comparison['label']}) on {comparison['metric']} ==="
        )
        lines.append(f"  paired tasks      {comparison['n_paired']}")
        lines.append(f"  both correct      {comparison['both_correct']}")
        lines.append(f"  both wrong        {comparison['both_wrong']}")
        lines.append(f"  only {comparison['first']:<12} {comparison['only_first']}")
        lines.append(f"  only {comparison['second']:<12} {comparison['only_second']}")
        lines.append(f"  discordant pairs  {comparison['n_discordant']}")
        lines.append(f"  McNemar exact p   {comparison['mcnemar_exact_p']}")
        if not comparison["significance_attainable"]:
            lines.append(
                "  !! Fewer than 6 discordant pairs: p<0.05 is arithmetically"
            )
            lines.append(
                "     unattainable here. A null result is NOT evidence of no effect."
            )
        if comparison["excluded_duplicates"]:
            lines.append(
                f"  !! Excluded from test (duplicate task ids, needs clustered "
                f"analysis): {comparison['excluded_duplicates']}"
            )

    lines.append(
        "\n* Hit@k is capped at the same candidate budget in every arm. An uncapped"
        "\n  'was it anywhere in the output' metric would compare the assistant's"
        "\n  whole retrieval list against a human naming one file -- recall@5 vs"
        "\n  recall@1. Capped, it means the same thing in every arm: was the correct"
        "\n  file among the first k candidates the user was actually given?\n"
        "  Top-k is chunk-level and exists only where there is a retrieval step.\n"
        "† Path hallucination is a CITATION-level rate, pooled across tasks, so\n"
        "  tasks citing many files carry more weight. Citations within one answer\n"
        "  are not independent, so the interval shown is optimistic -- treat it as\n"
        "  indicative. Basename matching also means the count is conservative (it\n"
        "  under-reports hallucination rather than over-reporting it)."
    )
    lines.append(
        "\nNote: with a task set this size these are descriptive results. Report "
        "intervals, not point estimates alone, and do not imply the study is "
        "powered for inference (protocol §6). Comparing the agent against more "
        "than one other arm makes these multiple comparisons; no correction is "
        "applied, so treat individual p-values accordingly."
    )
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Score evaluation run logs.")
    parser.add_argument("--tasks", required=True, help="frozen tasks.jsonl")
    parser.add_argument("--runs", nargs="+", required=True, help="one or more run logs")
    parser.add_argument("--manifest", help="frozen file manifest (for hallucination rate)")
    parser.add_argument(
        "--corpus",
        help="corpus dir; lets a path READ OUT of the code be told apart from an "
             "invented one. Without it, correctly-reported references to "
             "non-indexed files are miscounted as hallucinations.",
    )
    parser.add_argument(
        "--make-manifest",
        metavar="DIR",
        help="walk DIR, write a manifest to stdout, and exit",
    )
    parser.add_argument(
        "--reference",
        help="arm every other arm is compared against in the paired test. "
             "Defaults to personalized/agent/plain, whichever is present.",
    )
    parser.add_argument("--json", help="also write full metrics as JSON here")
    args = parser.parse_args(argv)

    if args.make_manifest:
        for path in sorted(manifest_from_directory(args.make_manifest)):
            print(path)
        return 0

    tasks = load_tasks(args.tasks)
    report = validate(tasks)
    for warning in report["warnings"]:
        print(f"WARN  {warning}", file=sys.stderr)
    if report["errors"]:
        for error in report["errors"]:
            print(f"ERROR {error}", file=sys.stderr)
        return 2

    usable = scorable(tasks)
    skipped = len(tasks) - len(usable)
    if skipped:
        print(
            f"NOTE  {skipped} placeholder task(s) excluded from scoring "
            "(missing expected_paths or ground_truth_source).",
            file=sys.stderr,
        )
    if not usable:
        print(
            "ERROR No scorable tasks. Ground truth must be filled in by someone "
            "with lab access before any metric can be computed.",
            file=sys.stderr,
        )
        return 2

    by_id = {task.id: task for task in usable}
    manifest = load_manifest(args.manifest) if args.manifest else None
    referenced = corpus_referenced_paths(args.corpus) if args.corpus else None
    if manifest is not None and referenced is None:
        print(
            "WARN  No --corpus given; paths the model read out of the code cannot "
            "be distinguished from invented ones, so fabrication is OVERSTATED.",
            file=sys.stderr,
        )
    if manifest is None:
        print(
            "WARN  No --manifest given; path hallucination rate cannot be computed.",
            file=sys.stderr,
        )

    per_arm_scored: Dict[str, List[dict]] = defaultdict(list)
    for run_path in args.runs:
        for record in load_runs(run_path):
            task = by_id.get(record.get("task_id"))
            if task is None:
                continue
            arm = record.get("arm") or os.path.splitext(os.path.basename(run_path))[0]
            scored_row = score_task(task, record, manifest, referenced=referenced)
            # run_eval's dry-run marks records synthetic. Carry that through to
            # the report: a dry run otherwise prints Hit@1 100%, hallucination
            # 0%, and looks exactly like a finding.
            scored_row["synthetic"] = bool(record.get("synthetic"))
            per_arm_scored[arm].append(scored_row)

    if not per_arm_scored:
        print("ERROR No run records matched any scorable task.", file=sys.stderr)
        return 2

    per_arm = {arm: aggregate(scored) for arm, scored in per_arm_scored.items()}

    # Pick the arm everything else is compared against. Previously this was
    # hardcoded to the literal name "agent" — which run_arms.py never produces —
    # so the paired test the protocol calls its PRIMARY analysis silently
    # produced nothing and the report showed four tables and no comparison.
    arms = list(per_arm_scored)
    reference = args.reference
    if reference is None:
        for candidate in ("personalized", "agent", "plain"):
            if candidate in arms:
                reference = candidate
                break
    if reference is not None and reference not in arms:
        print(
            f"ERROR --reference {reference!r} is not among the arms present "
            f"({', '.join(sorted(arms))}). Refusing to skip the primary test "
            "silently.",
            file=sys.stderr,
        )
        return 2
    if reference is None:
        print(
            "WARN  No reference arm identified, so NO paired comparison was run. "
            "Pass --reference <arm> to enable the primary statistical test.",
            file=sys.stderr,
        )

    comparisons = []
    if reference is not None:
        for other in sorted(arms):
            if other == reference:
                continue
            comparison = compare_arms(
                per_arm_scored[reference], per_arm_scored[other]
            )
            comparison.update(
                {
                    "label": f"{reference} vs {other}",
                    "first": reference,
                    "second": other,
                }
            )
            comparisons.append(comparison)

    print(render_report(per_arm, comparisons))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {"per_arm": per_arm, "comparisons": comparisons},
                handle,
                indent=2,
            )
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
