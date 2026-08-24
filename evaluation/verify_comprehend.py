"""Verify every comprehend ground-truth value actually appears in its claimed file."""
import json, os, re

PANCYTO = "/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/projects/PanCyto"

# (task id, literal strings that must appear in at least one expected file)
CHECKS = {
    "com-001": ["128"],
    "com-002": ["bf16"],
    "com-003": ["0.775"],
    "com-005": ["500", "937"],
    "com-006": ["10", "15"],
    "com-007": ["120"],
    "com-009": ["n_storage_tokens", "4"],
    "com-010": ["3.0e-05"],
}

tasks = {}
for line in open("tasks_pancyto.jsonl"):
    line = line.strip()
    if line and not line.startswith("#"):
        t = json.loads(line); tasks[t["id"]] = t

print("=== COMPREHEND GROUND TRUTH: does the claimed value exist in the claimed file? ===")
problems = []
for tid, needles in CHECKS.items():
    t = tasks[tid]
    blob = ""
    for p in t["expected_paths"]:
        fp = os.path.join(PANCYTO, p)
        try:
            blob += open(fp, errors="ignore").read()
        except Exception as e:
            problems.append(f"{tid}: cannot read {p}: {e}")
    missing = [n for n in needles if n not in blob]
    status = "OK  " if not missing else "FAIL"
    if missing:
        problems.append(f"{tid}: {missing} NOT FOUND in {t['expected_paths']}")
    print(f"  {status} {tid}  claim={t['answer_note'][:60]!r}")
    if missing:
        print(f"        missing: {missing}")

print()
print("=== SUMMARY ===")
print("  problems:", problems if problems else "none")
