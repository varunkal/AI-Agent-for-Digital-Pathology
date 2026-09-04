# The Hybrid RAG Model — how it works and what we measured

A plain-language record of the retrieval system, written to be understood
without a background in the field. Numbers here are reproducible from the
scripts in `evaluation/`.

## What the system does, in one paragraph

A user asks the Slack bot a question. The bot does not know anything about the
lab on its own. So it (1) searches the lab's files for the few text chunks most
likely to hold the answer, (2) pastes those chunks into the language model's
prompt, and (3) the model writes an answer using only what it was handed. Step
1 is the whole ballgame: if the right file is not in the chunks it grabbed, the
model answers with the wrong material in front of it and cannot recover.

## Two kinds of search

- **Keyword search (BM25):** matches the literal words. Ask about "rgb stats"
  and it finds files that contain "rgb" and "stats." Simple, exact, and very
  good at unique names like `set_rgb_stats.py`.
- **Semantic search (vector / ChromaDB):** turns meaning into numbers and finds
  text that *means* something similar, even with no shared words. Ask about
  "per-channel color statistics" and it can find a file that says "RGB mean and
  standard deviation." Powerful, but fuzzy.

## What "hybrid" means

Run both searches at once. Each returns a ranked list. Merge the two lists into
one, giving keyword search's votes more weight. That merged list is what the
model sees. "Hybrid" just means "both searches combined" instead of one.

We combine the lists with **reciprocal rank fusion (RRF)**: each retriever
contributes points based on where it ranked a file, and the points are summed.
Ranking-based fusion means we never have to reconcile the two searches'
different scoring scales.

## The core finding: search quality collapses as the corpus grows

We evaluated on a fixed set of 30 questions (25 scorable) with hand-verified
answers, on the PanCyto clinical pathology codebase.

| Corpus | Search method | Top-5 accuracy |
|---|---|---|
| 49 files | Semantic only | 88% |
| 49 files | Hybrid | **96%** |
| 610 files | Semantic only (deployed) | **56%** |
| 610 files | Keyword only | 88% |
| 610 files | Hybrid, equal weight | 80% |
| 610 files | **Hybrid, keyword-weighted 3x** | **88%** |

"Top-5" = the correct file was among the 5 chunks retrieved.

Reading this table:

1. **On a small corpus, everything works well** and hybrid is best (96%).
2. **On the full codebase, semantic search alone collapses to 56%** — nearly
   half of questions never see the right file. The extra files are legitimate,
   similar lab code (other projects full of comparable training scripts), so
   meaning-based search cannot tell them apart.
3. **Keyword search barely moved** (88%), because exact file names stay unique
   no matter how big the haystack gets.
4. **Combining them naively made things worse** (80%): equal weighting let the
   weak searcher outvote the strong one.
5. **Weighting keyword search 3x fixed it** (88%). Same files, same questions —
   only the search strategy changed.

The repair is about 60 lines of code and needs no GPU. The hard part was not
fixing it; it was *measuring* it. Without a benchmark, nobody would have known
the deployed system was at 56% on a real project.

## Failures are silent

When retrieval misses, the bot does not say "I could not find it." It writes a
confident, well-formatted, cited answer from whatever wrong files it grabbed.
Example we caught: asked for the project's funding source, it answered
"qdp-alpha," pulled from a billing line in a batch script — a real citation to
a real file, and the wrong conclusion. In a clinical research setting, a tool
that invents plausible answers is more dangerous than one that admits it does
not know.

## Speed (server-side, one V100/L40S GPU)

| Stage | Time |
|---|---|
| Embed the question | ~6.5s |
| Search the chunks | <0.2s even at 6,275 chunks |
| Generate the answer | ~11s |
| **Total per question** | **~17s** |
| Cold start (load the 18.6GB model) | ~11-170s, once per server launch |

Search is essentially free. The time is model loading and text generation. The
6.5s to embed one short question is a target for future work: it is slow only
because one model must be evicted from GPU memory to load the other.

Retrieving more chunks (k) is cheap — going from 5 to 20 costs about 1.4s — but
only helps the *small* corpus (92% to 96%). On the large corpus more chunks did
nothing, because the missed file is ranked ~#200, not ~#6.

## Limitations (state these plainly)

- 25 scorable questions, single run, one corpus. The true accuracy behind an
  88% could reasonably sit anywhere from ~70% to ~96%.
- Ground truth is verified but drafted by reading the code, not by the original
  author for every item. One task (`rep-007`) is flagged unverified and is
  missed by every method — likely a bad question, not a bad retriever.
- The 610-file result is one project. It does not show the system works across
  many projects; that was never indexed.

## What is not done yet

**Re-ranking.** On 610 files the system is stuck at 88% and neither weighting
nor retrieving more chunks moves it. The standard next step: retrieve ~50 rough
candidates, have a model carefully read and re-score those 50, keep the best 5.
More expensive, but it is the intervention that could push past 88%.

## Reproduce

```
python evaluation/baseline_retrieval.py --corpus <PanCyto> \
  --tasks evaluation/tasks_pancyto.jsonl --outdir runs
python evaluation/hybrid_retrieval.py --corpus <PanCyto> \
  --tasks evaluation/tasks_pancyto.jsonl --outdir runs \
  --host http://127.0.0.1:11434 --cache embed_cache.json
python pathology-agent/evaluation/analyze.py \
  --tasks evaluation/tasks_pancyto.jsonl --runs runs/*.jsonl
```
