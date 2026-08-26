"""
lab_query.py — retrieval that returns its sources.

WHY THIS EXISTS
---------------
`lab_rag.query()` builds an answer from retrieved chunks but returns only the
answer string. The retrieved metadata (source path, offset, filename) is printed
when verbose=True and then discarded. So no caller can know *which files* an
answer came from, which makes two of the evaluation protocol's core metrics
impossible to compute:

  - top_k_accuracy          (was the right file actually retrieved?)
  - path_hallucination_rate (did the model cite files that don't exist?)

This module adds that capability WITHOUT modifying lab_rag.py. It reads the same
ChromaDB collection and defers to lab_rag's own configuration constants when
lab_rag is importable, so the two modules cannot drift apart.

READ-ONLY: only reads the vector index and calls the local model. Never opens lab
files for writing, never executes code.

TESTABLE: every external dependency (embedding, chat, collection) is injectable,
so the logic runs under test with fakes and no Ollama/ChromaDB installed.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

# --- Configuration -----------------------------------------------------------

_FALLBACK = {
    "CHROMA_DIR": os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db"),
    "COLLECTION_NAME": "levy_lab",
    "EMBED_MODEL": "nomic-embed-text",
    "CHAT_MODEL": "qwen3-coder",
    "TOP_K": 5,
}


# Environment overrides. These exist so the model can be changed WITHOUT editing
# the team lead's repository — an uncommitted local edit there would silently
# revert on any pull and take the whole system with it.
_ENV_OVERRIDES = {
    "CHAT_MODEL": "LAB_CHAT_MODEL",
    "EMBED_MODEL": "LAB_EMBED_MODEL",
    "CHROMA_DIR": "LAB_CHROMA_DIR",
    "COLLECTION_NAME": "LAB_COLLECTION",
}


def config() -> Dict[str, object]:
    """Live config. Precedence: environment > lab_rag > built-in fallback.

    Environment first so a deployment can point at a different model or index
    without touching source. lab_rag second so the team's own constants remain
    authoritative by default.
    """
    try:
        import lab_rag

        resolved = {
            key: getattr(lab_rag, key, default) for key, default in _FALLBACK.items()
        }
    except Exception:
        resolved = dict(_FALLBACK)

    for key, variable in _ENV_OVERRIDES.items():
        override = os.environ.get(variable)
        if override:
            resolved[key] = override
    return resolved


# --- Data model --------------------------------------------------------------


@dataclass
class RetrievedChunk:
    """One chunk from the vector store, with its provenance."""

    text: str
    source: str                      # repo-relative path recorded at index time
    start_char: Optional[int] = None
    filename: Optional[str] = None
    distance: Optional[float] = None

    @classmethod
    def from_chroma(cls, document: str, metadata: dict, distance=None) -> "RetrievedChunk":
        metadata = metadata or {}
        return cls(
            text=document,
            source=metadata.get("source", "<unknown>"),
            start_char=metadata.get("start_char"),
            filename=metadata.get("filename"),
            distance=distance,
        )


@dataclass
class QueryResult:
    """Everything a caller needs to score a run."""

    question: str
    answer: str
    chunks: List[RetrievedChunk] = field(default_factory=list)
    latency_s: float = 0.0
    retrieval_latency_s: float = 0.0
    abstained: bool = False
    cited_paths: List[str] = field(default_factory=list)
    # Which experimental condition produced this answer. Recorded on every run so
    # an arm can never be mislabelled at analysis time.
    personalized: bool = False
    profile_path: Optional[str] = None
    retrieval_enabled: bool = True

    @property
    def sources(self) -> List[str]:
        """Unique retrieved source paths, best-match first."""
        seen, ordered = set(), []
        for chunk in self.chunks:
            if chunk.source not in seen:
                seen.add(chunk.source)
                ordered.append(chunk.source)
        return ordered

    def to_dict(self) -> dict:
        """JSON-serializable form, for run logs."""
        return {
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources,
            "cited_paths": self.cited_paths,
            "abstained": self.abstained,
            "personalized": self.personalized,
            "profile_path": self.profile_path,
            "retrieval_enabled": self.retrieval_enabled,
            "latency_s": round(self.latency_s, 4),
            "retrieval_latency_s": round(self.retrieval_latency_s, 4),
            "chunks": [
                {"source": c.source, "start_char": c.start_char, "distance": c.distance}
                for c in self.chunks
            ],
        }


# --- Default backends (real Ollama / ChromaDB), imported lazily --------------


def _default_embed(text: str) -> Sequence[float]:
    import ollama

    return ollama.embed(model=config()["EMBED_MODEL"], input=text)["embeddings"][0]


def _default_chat(prompt: str) -> str:
    """Call the local model with PINNED sampling settings.

    Ollama's defaults sample, so the same question could give different answers
    and an arm difference could be nothing but noise. provenance.SAMPLING_OPTIONS
    fixes temperature to 0 and the seed, and sets num_ctx explicitly because the
    default silently truncates long prompts — which would drop retrieved context
    with no error and quietly corrupt the retrieval measurement.
    """
    import ollama

    import provenance

    response = ollama.chat(
        model=config()["CHAT_MODEL"],
        messages=[{"role": "user", "content": prompt}],
        options=dict(provenance.SAMPLING_OPTIONS),
    )
    return response["message"]["content"]


def _default_collection():
    import chromadb

    client = chromadb.PersistentClient(path=config()["CHROMA_DIR"])
    return client.get_collection(config()["COLLECTION_NAME"])


# --- Prompt ------------------------------------------------------------------
# Kept close to lab_rag.query()'s prompt so results from the two code paths stay
# comparable. The prompt is part of the method — note any change in the paper.

PROMPT_TEMPLATE = """You are the Levy Lab Copilot, an AI assistant for digital pathology researchers at Dartmouth.
Answer the question below using ONLY the provided context from lab files. If the context doesn't contain enough information, say so.
Always cite which file(s) your answer comes from.
{lab_context}
CONTEXT FROM LAB FILES:
{context}

QUESTION: {question}

ANSWER:"""


def build_context(chunks: Iterable[RetrievedChunk]) -> str:
    return "\n\n---\n\n".join(f"Source: {c.source}\n{c.text}" for c in chunks)


def build_prompt(
    question: str,
    chunks: Iterable[RetrievedChunk],
    *,
    lab_context: str = "",
) -> str:
    """Assemble the prompt. `lab_context` is the personalization block.

    Passing "" gives the un-personalized condition, byte-for-byte identical to
    the original prompt. That exactness matters: the ablation must differ ONLY in
    the presence of lab conventions, not in incidental whitespace or wording, or
    the contrast measures formatting rather than personalization.
    """
    block = f"\n{lab_context}\n" if lab_context.strip() else "\n"
    return PROMPT_TEMPLATE.format(
        lab_context=block,
        context=build_context(chunks),
        question=question,
    )


# --- Retrieval ---------------------------------------------------------------


def retrieve(
    question: str,
    *,
    collection=None,
    embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
    top_k: Optional[int] = None,
) -> List[RetrievedChunk]:
    """Embed the question and return top-k chunks WITH provenance."""
    collection = collection if collection is not None else _default_collection()
    embed_fn = embed_fn or _default_embed
    top_k = top_k if top_k is not None else int(config()["TOP_K"])

    embedding = embed_fn(question)
    results = collection.query(query_embeddings=[embedding], n_results=top_k)

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0] or [{}] * len(documents)
    distances = (results.get("distances") or [[None] * len(documents)])[0]

    return [
        RetrievedChunk.from_chroma(doc, meta, dist)
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]



def index_drift(corpus_root: str, *, collection=None) -> Dict[str, List[str]]:
    """Compare what is indexed against what is on disk.

    WHY THIS EXISTS
    ---------------
    A pilot run was silently invalidated by a stale index. Six files were added
    to the corpus and the vector store was never rebuilt, so the keyword
    baseline read fifteen files while the agent's semantic search could only see
    nine. The agent then answered, correctly given what it could see, that "no
    files in the corpus mention cohort B" -- for files sitting on disk. Nothing
    anywhere reported a problem, and the comparison between the two arms was
    meaningless.

    Returns {"missing_from_index": [...], "missing_from_disk": [...]}. Empty
    lists mean the index is current. Callers running an evaluation should treat
    a non-empty result as fatal: no measurement taken against a drifted index
    means anything.
    """
    import os

    collection = collection if collection is not None else _default_collection()
    got = collection.get(include=["metadatas"])
    indexed = {
        (m or {}).get("source")
        for m in (got.get("metadatas") or [])
        if (m or {}).get("source")
    }

    root = os.path.abspath(corpus_root)
    on_disk = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in {"__pycache__", "node_modules"}
        ]
        for name in filenames:
            if name.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            on_disk.add(rel)

    return {
        "missing_from_index": sorted(on_disk - indexed),
        "missing_from_disk": sorted(indexed - on_disk),
    }


# --- Abstention & citation analysis -----------------------------------------

# Markers that indicate the model declined rather than fabricating. Feeds the
# protocol's `correct_abstention_rate` on undocumented-answer control tasks.
ABSTENTION_MARKERS = (
    "doesn't contain enough information",
    "does not contain enough information",
    "doesn't contain information",
    "does not contain information",
    # Plural verb forms. The model wrote "the files do not contain information"
    # and a genuine refusal was scored as a fabrication, turning 4/5 correct
    # abstention into 3/5 on a real run. Reported by the evaluation on PanCyto.
    "do not contain information",
    "don't contain information",
    "do not contain enough information",
    "don't contain enough information",
    "not enough information",
    "insufficient information",
    "no information",
    "cannot find",
    "can't find",
    "could not find",
    "couldn't find",
    "unable to find",
    "not found in",
    "is not mentioned",
    "isn't mentioned",
    "not specified in",
    "i don't know",
    "no relevant",
    # Added after a pilot scored correct abstentions as failures. The agent's
    # system prompt instructs it to answer "that is not written down in these
    # files", and none of the markers above match that, so three genuine
    # abstentions were counted as three hallucinations. A detector that does not
    # recognise the phrasing its own prompt asks for measures nothing.
    #
    # Deliberately narrow. Each phrase asserts that a record is absent. Looser
    # wording such as "does not specify" was considered and rejected: it appears
    # inside answers that go on to guess, and a false positive here would score
    # a fabrication as a correct refusal, which is the direction of error this
    # project has to guard against hardest.
    "not written down",
    "not documented",
    "not explicitly document",
    "n't explicitly document",
    "does not document",
    "do not document",
)


def detect_abstention(answer: str, markers: Sequence[str] = ABSTENTION_MARKERS) -> bool:
    """True if the answer appears to decline for lack of grounding.

    Deliberately a transparent keyword rule, not a model judgement: the paper
    needs this inspectable and reproducible. Report it as a heuristic and
    hand-check a sample.

    KNOWN LIMIT, and a fix that was tried and rejected. Adding "does not
    specify" reclassified two answerable questions as refusals, because the
    model hedges and then answers anyway:

        "The provided context does not specify the macro-F1 score of the frozen
        pretrained baseline. The files mention that the frozen baseline used
        ImageNet statistics and achieved a score of 0.775"

    That contains a refusal phrase and the correct answer. Substring matching is
    unreliable in both directions and cannot be fixed by adding more strings. At
    five controls the classification was checked by reading. Past roughly
    fifteen that stops being practical and this needs to become something other
    than substring matching.
    """
    lowered = (answer or "").lower()
    return any(marker in lowered for marker in markers)


# Path-like tokens, anchored on a known extension so ordinary prose with dots
# doesn't match.
_PATH_RE = re.compile(
    r"[\w./\\-]*\w\.(?:py|ipynb|md|txt|json|ya?ml|csv|tsv|sh|R|rds|h5ad|h5|pkl|cfg|ini|toml)\b",
    re.IGNORECASE,
)


def extract_cited_paths(answer: str) -> List[str]:
    """Paths the model mentioned in prose. Order-preserving, deduplicated."""
    seen, ordered = set(), []
    for match in _PATH_RE.finditer(answer or ""):
        path = match.group(0).lstrip("./\\")
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def verify_paths(paths: Iterable[str], root: str) -> Dict[str, bool]:
    """Map each cited path -> whether it exists under `root`.

    The objective half of the hallucination metric: no human rater needed. A path
    counts as existing if it resolves under root, matches a real basename, or
    matches the tail of a real path (models often cite a basename, not a full
    path).
    """
    root = os.path.abspath(root)
    real_relative, real_basenames = set(), set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            real_relative.add(os.path.relpath(full, root).replace(os.sep, "/"))
            real_basenames.add(name)

    existing: Dict[str, bool] = {}
    for path in paths:
        normalized = path.replace("\\", "/")
        existing[path] = (
            normalized in real_relative
            or os.path.basename(normalized) in real_basenames
            or any(rel.endswith("/" + normalized) for rel in real_relative)
        )
    return existing


# --- Top-level entry point ---------------------------------------------------


def answer_question(
    question: str,
    *,
    collection=None,
    embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
    chat_fn: Optional[Callable[[str], str]] = None,
    top_k: Optional[int] = None,
    personalize: bool = True,
    profile_path: Optional[str] = None,
    retrieval: bool = True,
) -> QueryResult:
    """Retrieve, generate, and return the answer *plus its provenance*.

    Call this instead of lab_rag.query() when you need sources — i.e. from the
    Slack bot and from the evaluation harness.

    Two switches exist purely so the evaluation can run its arms against the
    identical code path:

    personalize=False  drops the lab-conventions block. Tests whether knowing the
                       lab's norms helps (pitch deck Aim 2).
    retrieval=False    skips retrieval entirely and asks the model cold. Tests
                       whether grounding matters at all, holding model size
                       constant — the arm that turns the central claim from a
                       definition into a causal one.
    """
    chat_fn = chat_fn or _default_chat

    lab_context = ""
    profile_used = None
    if personalize:
        import lab_profile

        profile = lab_profile.load_profile(profile_path)
        lab_context = lab_profile.render_context(profile)
        profile_used = profile.source_path if not profile.is_empty else None

    if not retrieval:
        started = time.monotonic()
        text = chat_fn(build_prompt(question, [], lab_context=lab_context))
        finished = time.monotonic()
        return QueryResult(
            question=question,
            answer=text,
            chunks=[],
            latency_s=finished - started,
            retrieval_latency_s=0.0,
            abstained=detect_abstention(text),
            cited_paths=extract_cited_paths(text),
            personalized=bool(lab_context.strip()),
            profile_path=profile_used,
            retrieval_enabled=False,
        )

    started = time.monotonic()
    chunks = retrieve(question, collection=collection, embed_fn=embed_fn, top_k=top_k)
    retrieval_done = time.monotonic()

    if not chunks:
        return QueryResult(
            question=question,
            answer=(
                "No indexed lab data matched that question. If the index is empty, "
                "run `python lab_rag.py index <directory>` on Discovery first."
            ),
            latency_s=retrieval_done - started,
            retrieval_latency_s=retrieval_done - started,
            abstained=True,
            personalized=bool(lab_context.strip()),
            profile_path=profile_used,
        )

    text = chat_fn(build_prompt(question, chunks, lab_context=lab_context))
    finished = time.monotonic()

    return QueryResult(
        question=question,
        answer=text,
        chunks=chunks,
        latency_s=finished - started,
        retrieval_latency_s=retrieval_done - started,
        abstained=detect_abstention(text),
        cited_paths=extract_cited_paths(text),
        personalized=bool(lab_context.strip()),
        profile_path=profile_used,
    )


def format_for_slack(result: QueryResult, max_sources: int = 5) -> str:
    """Render an answer with an explicit source list, for the Slack surface.

    Showing retrieved paths is the difference between "trust me" and a checkable
    answer — and it is what makes "@LevyBoy, where can I find this file?"
    actually answer the question.
    """
    body = (result.answer or "").strip()
    sources = result.sources[:max_sources]
    if not sources:
        return body
    listed = "\n".join(f"• `{s}`" for s in sources)
    return f"{body}\n\n_Retrieved from:_\n{listed}"
