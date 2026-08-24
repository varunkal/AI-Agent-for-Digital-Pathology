"""Print each locate/reproduce claim beside the file's own opening lines,
so a human can confirm or reject it in one pass."""
import json, os

PANCYTO = "/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/projects/PanCyto"

tasks = []
for line in open("tasks_pancyto.jsonl"):
    line = line.strip()
    if line and not line.startswith("#"):
        t = json.loads(line)
        if t["category"] in ("locate", "reproduce"):
            tasks.append(t)

for t in tasks:
    print("=" * 78)
    print(f"{t['id']}  [{t['category']}]")
    print(f"Q: {t['question']}")
    print(f"CLAIMED ANSWER: {', '.join(t['expected_paths'])}")
    print("-" * 78)
    for p in t["expected_paths"]:
        fp = os.path.join(PANCYTO, p)
        try:
            with open(fp, errors="ignore") as f:
                lines = [l.rstrip() for l in f.readlines()[:16]]
        except Exception as e:
            print(f"  !! cannot read {p}: {e}")
            continue
        body = [l for l in lines if l.strip() and not l.startswith("#!")]
        print(f"  {p} opens with:")
        for l in body[:7]:
            print("     ", l[:110])
    print("  CONFIRM? [ ] yes   [ ] no")
    print()
