"""Definitive control check: search ONLY the files actually stored in the index."""
import os, re, chromadb

PANCYTO = "/dartfs/rc/nosnapshots/V/VaickusL-nb/EDIT_Interns_2026/projects/PanCyto"
os.environ.setdefault("LAB_RAG_CHROMA_DIR", "/dartfs-hpc/scratch/" + os.environ["USER"] + "/pancyto/index")

col = chromadb.PersistentClient(path=os.environ["LAB_RAG_CHROMA_DIR"]).get_collection("levy_lab")
got = col.get(include=["metadatas", "documents"])
indexed = sorted({m["source"] for m in got["metadatas"]})
print(f"files actually in the index: {len(indexed)}")

# Search the STORED CHUNK TEXT, i.e. exactly what retrieval can see.
blob = "\n".join(got["documents"]).lower()

CONTROLS = {
    "und-001 consent":   [r"\bconsent", r"\bassent\b"],
    "und-002 journal":   [r"\bjournal\b", r"submitted to", r"\bmanuscript\b", r"\bpreprint\b"],
    "und-003 patient age": [r"patient age", r"\bage distribution", r"years old", r"\bdemograph"],
    "und-004 hospital":  [r"\bhospital\b", r"hitchcock", r"\bdhmc\b", r"medical cent", r"\binstitution\b"],
    "und-005 funding":   [r"\bnih\b", r"\bnsf\b", r"\bR01\b", r"\bP30\b", r"\bU01\b",
                          r"\bgrant\b", r"\bfunding\b", r"funded by", r"supported by", r"\baward\b"],
}

print()
print("=== does any control question have an answer in the INDEXED TEXT? ===")
for name, pats in CONTROLS.items():
    hits = []
    for p in pats:
        for m in re.finditer(p, blob, re.I):
            s = max(0, m.start() - 60)
            hits.append(blob[s:m.end() + 60].replace("\n", " "))
    if hits:
        print(f"\n  *** {name}: {len(hits)} possible hit(s) - REVIEW")
        for h in hits[:3]:
            print("      ...", h.strip()[:150])
    else:
        print(f"  clean  {name}")

print()
print("=== 'Dartmouth' context in indexed text (gray area check) ===")
for m in re.finditer(r"dartmouth", blob, re.I):
    s = max(0, m.start() - 80)
    print("   ...", blob[s:m.end() + 80].replace("\n", " ").strip()[:190])
