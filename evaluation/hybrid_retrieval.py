"""
hybrid_retrieval.py - dense, sparse, and hybrid retrieval on one corpus.

baseline-comparison.md showed BM25 and the dense retriever failing on
*different* tasks: BM25 recovers exact identifiers (loc-008 set_rgb_stats.py),
dense recovers conceptual paraphrase (com-002 float32/bfloat16). That predicts
a hybrid captures both, for 24/25 = 96%. This tests that prediction.

Three things this does that the original agent run could not:

  1. Dense scores over the WHOLE corpus. The agent run only ever saw ChromaDB's
     top-5, so its dense ranking below rank 5 was unobservable and no fusion
     was possible.
  2. Dense retrieval isolated from generation. The `agent` arm's metrics mix
     retrieval quality with the LLM's citation behaviour; `dense` here is the
     retrieval step alone.
  3. Reciprocal rank fusion, which needs full rankings from both retrievers.

Embeddings come from the same nomic-embed-text model lab_rag.py uses, over
HTTP, so the dense arm is comparable to the deployed system. CPU is fine: the
corpus is ~635 chunks.

Read-only. Emits run logs in analyze.py's schema.
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_retrieval import (  # noqa: E402
    BM25, TOP_K, build_corpus, load_tasks, tokenize,
)

EMBED_MODEL = "nomic-embed-text"
RRF_K = 60          # standard RRF damping constant (Cormack et al. 2009)
EMBED_BATCH = 16    # smaller than lab_rag's 50: nomic's context is only 2048
                    # tokens and llama-server is launched with -b 2048, so a
                    # 50-chunk batch overruns the server batch and stalls.


def embed(host, texts, retries=3, timeout=300):
    """POST to Ollama's /api/embed. stdlib only, so this runs on a bare node."""
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{host}/api/embed", data=payload,
        headers={"Content-Type": "application/json"},
    )
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())["embeddings"]
            if len(out) != len(texts):
                raise RuntimeError(f"sent {len(texts)}, got {len(out)}")
            return out
        except Exception as e:      # noqa: BLE001 - retry any transport error
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"embed failed after {retries} attempts: {last}")


def warmup(host):
    """One tiny embed before the real work, so a broken or pathologically slow
    server fails in seconds instead of after a 3-retry batch timeout."""
    t0 = time.time()
    v = embed(host, ["warmup"], retries=1, timeout=180)
    print(f"warmup ok: dim={len(v[0])} in {time.time() - t0:.1f}s", file=sys.stderr)


def embed_all(host, texts):
    out = []
    t0 = time.time()
    for i in range(0, len(texts), EMBED_BATCH):
        bt = time.time()
        out.extend(embed(host, texts[i:i + EMBED_BATCH]))
        done = min(i + EMBED_BATCH, len(texts))
        rate = done / max(time.time() - t0, 1e-9)
        print(f"  embedded {done}/{len(texts)}  "
              f"batch {time.time() - bt:.1f}s  eta {(len(texts) - done) / max(rate, 1e-9):.0f}s",
              file=sys.stderr, flush=True)
    return out


def normalize(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def cosine_scores(qv, mat):
    """qv and mat rows are pre-normalized, so dot product is cosine."""
    return [sum(a * b for a, b in zip(qv, row)) for row in mat]


def ranking(scores, positive_only=True):
    """Indices ordered best-first. Ties broken by index for determinism."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    if positive_only:
        order = [i for i in order if scores[i] > 0]
    return order


def rrf(rankings, k=RRF_K):
    """Reciprocal rank fusion. Rank-based, so the two retrievers' score
    scales (BM25 is unbounded, cosine is [-1,1]) never need calibrating."""
    fused = {}
    for r in rankings:
        for rank, idx in enumerate(r):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused, key=lambda i: (-fused[i], i)), fused


def write_run(path, arm, tasks, picks, chunks, scores_by_task):
    with open(path, "w") as fh:
        for t in tasks:
            top = picks[t["id"]][:TOP_K]
            sc = scores_by_task[t["id"]]
            fh.write(json.dumps({
                "task_id": t["id"],
                "arm": arm,
                "question": t["question"],
                "answer": "",
                "sources": [chunks[i]["source"] for i in top],
                "cited_paths": [],
                "abstained": False,
                "retrieval_enabled": True,
                "latency_s": 0.0,
                "chunks": [{
                    "source": chunks[i]["source"],
                    "start_char": chunks[i]["start_char"],
                    "score": round(sc.get(i, 0.0), 6),
                } for i in top],
            }) + "\n")
    print(f"wrote {path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--cache", help="reuse/store chunk embeddings here")
    args = ap.parse_args()

    warmup(args.host)

    chunks, nfiles = build_corpus(args.corpus)
    print(f"corpus: {nfiles} files, {len(chunks)} chunks", file=sys.stderr)
    tasks = load_tasks(args.tasks)
    os.makedirs(args.outdir, exist_ok=True)

    # --- dense ---
    texts = [c["text"] for c in chunks]
    if args.cache and os.path.exists(args.cache):
        with open(args.cache) as f:
            mat = json.load(f)
        if len(mat) != len(texts):
            raise SystemExit(
                f"cache has {len(mat)} vectors, corpus has {len(texts)}; delete it"
            )
        print(f"loaded {len(mat)} cached embeddings", file=sys.stderr)
    else:
        print("embedding corpus...", file=sys.stderr)
        mat = embed_all(args.host, texts)
        if args.cache:
            with open(args.cache, "w") as f:
                json.dump(mat, f)
    mat = [normalize(v) for v in mat]

    print("embedding queries...", file=sys.stderr)
    qvecs = [normalize(v) for v in embed_all(args.host, [t["question"] for t in tasks])]

    # --- sparse ---
    bm = BM25([tokenize(c["text"]) for c in chunks])

    picks = {a: {} for a in ("dense", "bm25", "hybrid_rrf")}
    scores = {a: {} for a in ("dense", "bm25", "hybrid_rrf")}

    for t, qv in zip(tasks, qvecs):
        qt = tokenize(t["question"])

        d_scores = cosine_scores(qv, mat)
        # Cosine is dense: nearly every chunk scores > 0, so an unfiltered
        # ranking is a full permutation of the corpus. That is exactly what
        # RRF needs, and it is why dense must NOT be positive-filtered here.
        d_rank = ranking(d_scores, positive_only=False)

        s_scores = bm.scores(qt)
        s_rank = ranking(s_scores, positive_only=True)

        h_rank, h_scores = rrf([d_rank, s_rank])

        picks["dense"][t["id"]] = d_rank
        scores["dense"][t["id"]] = {i: d_scores[i] for i in d_rank[:TOP_K]}
        picks["bm25"][t["id"]] = s_rank
        scores["bm25"][t["id"]] = {i: s_scores[i] for i in s_rank[:TOP_K]}
        picks["hybrid_rrf"][t["id"]] = h_rank
        scores["hybrid_rrf"][t["id"]] = {i: h_scores[i] for i in h_rank[:TOP_K]}

    for arm in picks:
        write_run(os.path.join(args.outdir, f"pancyto_{arm}.jsonl"),
                  arm, tasks, picks[arm], chunks, scores[arm])


if __name__ == "__main__":
    main()
