# How to demo — five commands

Everything below runs on your laptop. Nothing needs the cluster.

**Once, before you start** (only if Ollama isn't already running):
```bash
ollama serve
```

---

## 1. The Slack bot — real Qwen, real retrieval

```bash
bash ~/pathology-agent/RUN_REAL.sh
```

Wait for `Bolt app is running`. Then in Slack:

```
@LevyBoy where can I find the QC notebook for this cohort?
@LevyBoy what normalization was applied to the expression data?
@LevyBoy why was leiden resolution 0.7 chosen over other values?
```

The third one is the interesting one — see §5.

---

## 2. The agent using tools on its own  ← the newest piece

```bash
cd ~/pathology-agent
PYTHONPATH=~/labagent/rag /opt/anaconda3/bin/python3 rag/lab_agent.py \
  demo/corpus "Which script generates the recurrence figure, and what does it depend on?"
```

Shows the steps it chose, which tool it called, which files it opened, then the
answer. Takes ~2-3 min on a laptop (the model is doing real reasoning).

**Say:** "It decided by itself to search, read the results, and answer. Nobody
scripted that sequence."

---

## 3. Workflow reconstruction — instant, no model

```bash
cd ~/pathology-agent
/opt/anaconda3/bin/python3 rag/workflow.py demo/corpus results/figure3_recurrence.png --no-summary
```

Walks backwards from the figure through the whole pipeline.

**Say:** "This part is computed, not generated. Every arrow quotes a real line in
a real file, so it can be checked. The model can't invent a step because the
steps come from the code."

---

## 4. Lab personalization — the with/without contrast

```bash
cd ~/pathology-agent
PYTHONPATH=~/labagent/rag /opt/anaconda3/bin/python3 -c "
import sys; sys.path.insert(0,'rag'); sys.path.insert(0,'$HOME/labagent/rag')
import lab_query
q='why was leiden resolution 0.7 chosen over other values?'
print('WITHOUT lab profile:'); print(lab_query.answer_question(q, personalize=False).answer[:300])
"
```

Then with it:

```bash
cd ~/pathology-agent
LAB_PROFILE_PATH=demo/DEMO_LAB_PROFILE.md PYTHONPATH=~/labagent/rag \
/opt/anaconda3/bin/python3 -c "
import sys; sys.path.insert(0,'rag'); sys.path.insert(0,'$HOME/labagent/rag')
import lab_query
q='why was leiden resolution 0.7 chosen over other values?'
print('WITH lab profile:'); print(lab_query.answer_question(q, personalize=True).answer[:300])
"
```

**Say honestly:** "The profile happens to contain that fact, so this shows the
mechanism works — not that personalization cures hallucination. That's what the
evaluation is for."

---

## 5. The evaluation — the part that makes it research

```bash
cd ~/pathology-agent
/opt/anaconda3/bin/python3 evaluation/analyze.py \
  --tasks demo/demo_tasks.jsonl \
  --runs /tmp/runs/*.jsonl \
  --manifest /tmp/runs/manifest.txt \
  --corpus demo/corpus
```

Four arms already run against the real model. **The headline numbers:**

| | BM25 (grep) | Assistant | No retrieval |
|---|---|---|---|
| Right file, rank 1 | **100%** | 67% | 0% |
| Fabricated paths | none possible | **0 answers** | **2 of 2 that named one** |
| Speed | instant | 16s | 6s |

**Say:** "Keyword search beats the assistant at finding files. What the assistant
adds is synthesis — and retrieval is what stops it fabricating. Without retrieval,
every answer that named a file made one up (2 of 2); the other 6 named no files at
all, so they were unusable either way."

---

## 6. Backup if anything breaks

```bash
cd ~/pathology-agent && /opt/anaconda3/bin/python3 -m pytest tests/ -q
```

Runs the full suite in seconds. Proves every component works even if a live demo fails.

---

## The line to land

> "The most useful thing I built is the part that measures it. It already caught
> my own system losing to plain keyword search on file-finding — and I'd never
> have known without the comparison."
