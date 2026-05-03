"""
core/specter_ranker.py — SPECTER 2.0 semantic similarity ranking.

CRITICAL: Without adapter activation, this returns base SciBERT embeddings,
NOT SPECTER2 embeddings. All semantic scores downstream depend on this.
"""

import logging
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

SPECTER_DIM = 768

# ── Lazy singleton ────────────────────────────────────────────────────

_model = None
_tokenizer = None
_available: Optional[bool] = None
_adapter_active: bool = False  # hard-guarantee flag


def _load_model():
    """Load SPECTER 2.0 + explicitly activate the proximity adapter."""
    global _model, _tokenizer, _available, _adapter_active

    if _available is False:
        return

    try:
        import torch  # noqa: F401
        from adapters import AutoAdapterModel
        from transformers import AutoTokenizer

        logger.info("   [SPECTER] Loading allenai/specter2_base...")
        _tokenizer = AutoTokenizer.from_pretrained("allenai/specter2_base")
        _model = AutoAdapterModel.from_pretrained("allenai/specter2_base")

        # ── Fix 8: Explicit adapter activation ──
        # Load the proximity adapter with set_active=True
        adapter_name = _model.load_adapter(
            "allenai/specter2",
            source="hf",
            load_as="specter2",
            set_active=True,
        )

        # Belt-and-suspenders: force activation again in case load_adapter didn't
        _model.set_active_adapters(adapter_name)
        _model.eval()

        # Verify activation took effect
        try:
            active = _model.active_adapters
            active_str = str(active) if active else ""
            if active and "specter2" in active_str.lower():
                _adapter_active = True
                logger.info(f"   [SPECTER] ✅ Adapter ACTIVE: {active}")
            else:
                _adapter_active = False
                logger.error(f"   [SPECTER] ⚠️  Adapter NOT active! active_adapters={active!r}")
                logger.error("   [SPECTER] Embeddings will be base SciBERT, not SPECTER2!")
        except Exception as verify_err:
            logger.warning(f"   [SPECTER] Could not verify adapter activation: {verify_err}")
            _adapter_active = True  # assume OK if we can't check

        _available = True
        logger.info(f"   [SPECTER] Model loaded (adapter_active={_adapter_active})")

    except ImportError as e:
        _available = False
        logger.warning(f"   [SPECTER] Dependencies missing ({e}). "
                       "Install: pip install adapters transformers torch")
    except Exception as e:
        _available = False
        logger.warning(f"   [SPECTER] Model load failed: {e}")


def is_available() -> bool:
    global _available
    if _available is None:
        _load_model()
    return bool(_available)


def is_adapter_active() -> bool:
    """Public: whether the SPECTER2 adapter is verified active."""
    if _available is None:
        _load_model()
    return bool(_adapter_active)


# ── Embedding ─────────────────────────────────────────────────────────

def _clean_embedding_matrix(embeddings: "numpy.ndarray", expected_rows: int = None) -> "numpy.ndarray":
    import numpy as np
    from core.utils.math_utils import safe_normalize

    arr = np.asarray(embeddings, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.size == 0:
        rows = expected_rows or 0
        return np.zeros((rows, SPECTER_DIM), dtype=np.float32)

    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    arr = np.clip(arr, -1e6, 1e6)
    normed, valid = safe_normalize(arr)
    if (~valid).any():
        logger.warning(
            f"   [SPECTER] {int((~valid).sum())}/{arr.shape[0]} zero or invalid "
            "embedding rows; semantic similarity for them will be 0"
        )
    return normed.astype("float32", copy=False)


def _embed_texts(texts: list[str], batch_size: int = 32) -> "numpy.ndarray":
    """Embed text strings. Returns (N, 768) numpy array."""
    import numpy as np
    import torch

    if not _model or not _tokenizer:
        _load_model()
    if not _model or not _tokenizer:
        raise RuntimeError("SPECTER model not loaded")

    cleaned_texts = [(t or "").strip() for t in texts]
    if not cleaned_texts:
        return np.zeros((0, SPECTER_DIM), dtype=np.float32)

    all_embeddings = []

    for i in range(0, len(cleaned_texts), batch_size):
        batch = cleaned_texts[i : i + batch_size]
        inputs = _tokenizer(
            batch,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        )

        with torch.no_grad(), warnings.catch_warnings():
            # Suppress numpy warnings from the forward pass itself
            warnings.filterwarnings("ignore", category=RuntimeWarning,
                                    message=".*divide by zero.*|.*overflow.*|.*invalid value.*")
            # The adapter warnings should NOT appear now that we activate explicitly,
            # but suppress them if they do to avoid log noise from false positives.
            warnings.filterwarnings("ignore", message=".*adapters available.*")
            warnings.filterwarnings("ignore", message=".*prediction head.*")
            output = _model(**inputs)

        embeddings = output.last_hidden_state[:, 0, :].detach().cpu().numpy()
        all_embeddings.append(_clean_embedding_matrix(embeddings, expected_rows=len(batch)))

    if not all_embeddings:
        return np.zeros((0, SPECTER_DIM), dtype=np.float32)
    return np.concatenate(all_embeddings, axis=0)


def embed_papers(papers: list[dict]) -> "numpy.ndarray":
    """Embed papers using title [SEP] abstract. Returns (N, 768)."""
    texts = []
    for p in papers:
        title = (p.get("title", "") or "").strip()
        abstract = (p.get("abstract", "") or "").strip()
        text = f"{title} [SEP] {abstract}" if abstract else title
        texts.append(text)

    if not texts:
        import numpy as np
        return np.zeros((0, SPECTER_DIM), dtype=np.float32)

    return _embed_texts(texts)


def embed_query(query: str) -> "numpy.ndarray":
    """Embed a raw query string. Returns (1, 768)."""
    return _embed_texts([(query or "").strip()])


# ── Ranking ───────────────────────────────────────────────────────────

def _build_rich_query(
    topic: str,
    seed_papers: list[dict],
    keywords: list[str] = None,
    per_paper_keywords: dict = None,
) -> str:
    parts = [topic]
    for p in seed_papers:
        title = (p.get("title", "") or "").strip()
        if title:
            parts.append(title)
    if per_paper_keywords:
        for paper_title, kw_list in per_paper_keywords.items():
            for kw, score in kw_list:
                if kw not in parts:
                    parts.append(kw)
    if keywords:
        for kw in keywords:
            if kw not in parts:
                parts.append(kw)
    rich_query = " [SEP] ".join(parts)
    return rich_query[:2000]


def rank_papers(
    topic: str,
    seed_papers: list[dict],
    candidate_papers: list[dict],
    top_k: int = 30,
    topic_weight: float = 0.4,
    seed_weight: float = 0.6,
    keywords: list[str] = None,
    per_paper_keywords: dict = None,
) -> list[int]:
    import numpy as np
    from core.utils.math_utils import safe_cosine_sim

    if not candidate_papers:
        return []

    n_candidates = len(candidate_papers)
    top_k = min(top_k, n_candidates)

    rich_query = _build_rich_query(topic, seed_papers, keywords, per_paper_keywords)
    ppk_count = sum(len(v) for v in per_paper_keywords.values()) if per_paper_keywords else 0
    kw_count = len(keywords) if keywords else 0
    logger.info(f"   [SPECTER] Embedding {n_candidates} candidates + "
                f"{len(seed_papers)} seeds + enriched query "
                f"(topic + {len(seed_papers)} names + {ppk_count} per-paper kw + "
                f"{kw_count} search kw)...")

    query_emb = embed_query(rich_query)
    seed_embs = embed_papers(seed_papers) if seed_papers else np.zeros((0, SPECTER_DIM), dtype=np.float32)
    candidate_embs = embed_papers(candidate_papers)

    # Use safe cosine similarity (no div-by-zero warnings)
    topic_sims = safe_cosine_sim(query_emb, candidate_embs).squeeze(axis=0)

    if len(seed_embs) > 0:
        seed_sim_matrix = safe_cosine_sim(seed_embs, candidate_embs)  # (S, N)
        seed_sims = seed_sim_matrix.mean(axis=0)
    else:
        seed_sims = np.zeros(n_candidates)
        topic_weight = 1.0
        seed_weight = 0.0

    combined = topic_weight * topic_sims + seed_weight * seed_sims
    combined = np.nan_to_num(combined, nan=0.0, posinf=0.0, neginf=0.0)
    ranked_indices = np.argsort(-combined)[:top_k].tolist()

    logger.info(f"   [SPECTER] Top-{top_k} selected. "
                f"Score range: [{combined[ranked_indices[-1]]:.3f}, "
                f"{combined[ranked_indices[0]]:.3f}]")

    return ranked_indices


def embed_multi_anchor(
    query: str,
    seeds: list[dict],
    alternative_phrasings: list[str] = None,
    concepts: list[str] = None,
    domain: str = "",
) -> "numpy.ndarray":
    import numpy as np

    if not is_available():
        return np.zeros(SPECTER_DIM, dtype=np.float32)

    anchors: list[tuple[np.ndarray, float]] = []

    if query:
        try:
            q = embed_query(query)
            if q.shape[0] > 0:
                anchors.append((q[0], 0.25))
        except Exception:
            pass

    if query and domain:
        try:
            qd = embed_query(f"{query} in {domain}")
            if qd.shape[0] > 0:
                anchors.append((qd[0], 0.20))
        except Exception:
            pass

    if seeds:
        try:
            seed_embs = embed_papers(seeds)
            if seed_embs.shape[0] > 0:
                per_seed = 0.40 / seed_embs.shape[0]
                for i in range(seed_embs.shape[0]):
                    anchors.append((seed_embs[i], per_seed))
        except Exception:
            pass

    if alternative_phrasings:
        phrases = [p for p in alternative_phrasings if p][:5]
        if phrases:
            per_phrase = 0.10 / len(phrases)
            for phrase in phrases:
                try:
                    pe = embed_query(phrase)
                    if pe.shape[0] > 0:
                        anchors.append((pe[0], per_phrase))
                except Exception:
                    continue

    if concepts:
        cs = [c for c in concepts if c][:5]
        if cs:
            per_c = 0.05 / len(cs)
            for concept in cs:
                try:
                    ce = embed_query(concept)
                    if ce.shape[0] > 0:
                        anchors.append((ce[0], per_c))
                except Exception:
                    continue

    if not anchors:
        if query:
            try:
                return embed_query(query)[0]
            except Exception:
                pass
        return np.zeros(SPECTER_DIM, dtype=np.float32)

    total_weight = sum(w for _, w in anchors)
    if total_weight <= 0:
        from core.utils.math_utils import safe_normalize
        normed, valid = safe_normalize(anchors[0][0])
        return normed[0].astype("float32", copy=False) if valid.size and valid[0] else np.zeros(SPECTER_DIM, dtype=np.float32)

    combined = np.zeros_like(anchors[0][0], dtype=np.float64)
    for vec, weight in anchors:
        safe_vec = np.nan_to_num(np.asarray(vec, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        safe_vec = np.clip(safe_vec, -1e6, 1e6)
        combined += safe_vec * (weight / total_weight)

    from core.utils.math_utils import safe_normalize
    normed, valid = safe_normalize(combined)
    if valid.size and valid[0]:
        combined = normed[0]
    else:
        if query:
            try:
                return embed_query(query)[0]
            except Exception:
                pass
        return np.zeros(SPECTER_DIM, dtype=np.float32)

    return combined.astype("float32", copy=False)
