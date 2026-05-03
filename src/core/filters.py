"""
core/filters.py — Post-retrieval filters and deduplication.

Filters applied before Stage 3 quality filtering:
  1. Document-type filter (handbooks, encyclopedias, journal series)
     — matches both title AND venue patterns
  2. Fingerprint dedup — handles Arabic + Roman volume numbers, editions
  3. Year-aware quality guard — year=0/null papers only kept with high cites
  4. Semantic domain coherence (embedding-based, via shared safe normalize)
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple
import numpy as np

from core.utils.math_utils import safe_normalize, safe_cosine_sim

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year  # Fix 7: always dynamic


# ═══════════════════════════════════════════════════════════════════════
# Document-type filter (Fix 5: title AND venue patterns)
# ═══════════════════════════════════════════════════════════════════════

NON_PAPER_TITLE_PATTERNS = [
    re.compile(r"^\s*handbook\s+of\b",            re.IGNORECASE),
    re.compile(r"^\s*advances\s+in\b",            re.IGNORECASE),
    re.compile(r"^\s*encyclopedia\s+of\b",        re.IGNORECASE),
    re.compile(r"^\s*proceedings\s+of\b",         re.IGNORECASE),
    re.compile(r"^\s*annual\s+review\s+of\b",     re.IGNORECASE),
    re.compile(r"^\s*progress\s+in\b",            re.IGNORECASE),
    re.compile(r"^\s*oxford\s+handbook\b",        re.IGNORECASE),
    re.compile(r"^\s*cambridge\s+handbook\b",     re.IGNORECASE),
    re.compile(r"^\s*sage\s+handbook\b",          re.IGNORECASE),
    re.compile(r"^\s*routledge\s+handbook\b",     re.IGNORECASE),
    re.compile(r"^\s*blackwell\s+handbook\b",     re.IGNORECASE),
    re.compile(r"^\s*wiley\s+handbook\b",         re.IGNORECASE),
    re.compile(r"\bvol\.?\s*\d+\b.*\bvol\.?\s*\d+\b", re.IGNORECASE),
    re.compile(r"^\s*textbook\s+of\b",            re.IGNORECASE),
]

# Fix 5: Regex patterns for venue field (catches "The International Encyclopedia of ...")
NON_PAPER_VENUE_PATTERNS = [
    re.compile(r"\bencyclopedia\b",               re.IGNORECASE),
    re.compile(r"\bhandbook\b",                   re.IGNORECASE),
    re.compile(r"\bannual\s+review\s+of\b",       re.IGNORECASE),
    re.compile(r"\badvances\s+in\b",              re.IGNORECASE),
]

# Explicit venue blocklist (fallback for non-matching edge cases)
NON_PAPER_VENUES_EXACT = {
    "sage encyclopedia of research design",
    "understanding psychology for medicine",
}


def is_genuine_paper(paper: dict) -> bool:
    """Return False if paper looks like a handbook/journal/encyclopedia entry."""
    title = (paper.get("title") or "").strip()
    venue = (paper.get("venue") or "").lower().strip()

    if not title:
        return False

    # Title patterns
    for pattern in NON_PAPER_TITLE_PATTERNS:
        if pattern.search(title):
            logger.info(f"   [DocType] Excluded non-paper (title): '{title[:70]}'")
            return False

    # Venue regex patterns (Fix 5)
    for pattern in NON_PAPER_VENUE_PATTERNS:
        if pattern.search(venue):
            logger.info(f"   [DocType] Excluded non-paper venue '{venue[:50]}': '{title[:60]}'")
            return False

    # Exact venue blocklist
    if venue in NON_PAPER_VENUES_EXACT:
        logger.info(f"   [DocType] Excluded blocklisted venue '{venue[:40]}': '{title[:60]}'")
        return False

    return True


def filter_non_papers(papers: List[dict]) -> List[dict]:
    before = len(papers)
    result = [p for p in papers if is_genuine_paper(p)]
    if len(result) < before:
        logger.info(f"   [DocType] Filtered {before} → {len(result)} "
                    f"({before - len(result)} non-papers removed)")
    return result


# ═══════════════════════════════════════════════════════════════════════
# Year-aware pre-quality filter (Fix 3)
# ═══════════════════════════════════════════════════════════════════════

YEAR_NULL_MIN_CITES = 500   # undatable papers kept only with strong cite evidence


def has_valid_metadata(paper: dict) -> bool:
    """
    Reject papers whose metadata is too broken to reason about:
      - year is 0/None/< 1800 AND citations < 500
      - seed papers always pass
    """
    if paper.get("_is_seed", False):
        return True

    year = paper.get("year")
    cites = int(paper.get("citation_count", 0) or 0)

    if not year or year < 1800 or year > CURRENT_YEAR + 1:
        if cites < YEAR_NULL_MIN_CITES:
            title = (paper.get("title", "") or "")[:60]
            logger.debug(f"   [Metadata] Excluded year-null low-cite paper "
                         f"(year={year}, cites={cites}): '{title}'")
            return False
        # High-cite year-null: keep but flag
        title = (paper.get("title", "") or "")[:60]
        logger.warning(f"   [Metadata] Keeping year-null paper on cite evidence "
                       f"({cites} cites): '{title}'")
        return True

    return True


def filter_invalid_metadata(papers: List[dict]) -> List[dict]:
    before = len(papers)
    result = [p for p in papers if has_valid_metadata(p)]
    if len(result) < before:
        logger.info(f"   [Metadata] Filtered {before} → {len(result)} "
                    f"({before - len(result)} invalid-metadata papers removed)")
    return result


# ═══════════════════════════════════════════════════════════════════════
# Fingerprint-based deduplication (Fix 4: Roman numerals)
# ═══════════════════════════════════════════════════════════════════════

_STOPWORDS = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with"}

# Roman numeral regex — matches I, II, III, IV ... up to about LXXXIX
_ROMAN_RE = re.compile(
    r"\bvol(?:ume)?\.?\s*[ivxlcdmIVXLCDM]+\b",
    re.IGNORECASE,
)
_ARABIC_RE = re.compile(r"\bvol(?:ume)?\.?\s*\d+\b", re.IGNORECASE)
_PART_RE = re.compile(r"\bpart\s+[\divxlcdmIVXLCDM]+\b", re.IGNORECASE)
_EDITION_NUM_RE = re.compile(r"\b\d+(?:st|nd|rd|th)?\s+ed(?:ition)?\b", re.IGNORECASE)
_EDITION_WORD_RE = re.compile(
    r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+edition\b",
    re.IGNORECASE,
)
_REVISED_RE = re.compile(r"\brevised\s+edition\b", re.IGNORECASE)


def _normalize_title_for_fingerprint(title: str) -> str:
    """Strip subtitles, volume markers (Arabic AND Roman), editions, punctuation."""
    if not title:
        return ""
    t = title.lower()

    # Fix 4: strip BOTH Arabic and Roman volume markers
    t = _ARABIC_RE.sub("", t)
    t = _ROMAN_RE.sub("", t)
    t = _PART_RE.sub("", t)

    # Edition markers
    t = _EDITION_NUM_RE.sub("", t)
    t = _EDITION_WORD_RE.sub("", t)
    t = _REVISED_RE.sub("", t)

    # Subtitle (drop everything after first colon/semicolon)
    t = re.split(r"[:;]", t, maxsplit=1)[0]

    # Punctuation → whitespace, then collapse
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    tokens = [w for w in t.split() if w and w not in _STOPWORDS]
    return " ".join(tokens).strip()


def _first_author_key(paper: dict) -> str:
    authors = paper.get("authors") or []
    if not authors:
        return ""
    raw = authors[0]
    if isinstance(raw, dict):
        raw = raw.get("name", "") or ""
    raw = str(raw).strip()
    if not raw:
        return ""
    return raw.split()[-1].lower()


def make_fingerprint(paper: dict) -> str:
    """Dedup key: normalized_title + first_author_last_name."""
    norm_title = _normalize_title_for_fingerprint(paper.get("title") or "")
    first_author = _first_author_key(paper)
    key = f"{norm_title}|{first_author}"
    return hashlib.md5(key.encode()).hexdigest()


def deduplicate_papers(papers: List[dict]) -> List[dict]:
    """Dedup by fingerprint, keeping earliest-year (canonical) version."""
    groups: dict[str, List[dict]] = {}
    for p in papers:
        fp = make_fingerprint(p)
        if not fp:
            continue
        groups.setdefault(fp, []).append(p)

    result = []
    dropped = 0
    for fp, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
            continue

        def _rank_key(p):
            year = int(p.get("year", 0) or 0) or 9999
            cites = int(p.get("citation_count", 0) or 0)
            return (year, -cites)

        group.sort(key=_rank_key)
        result.append(group[0])
        dropped += len(group) - 1
        dropped_titles = [g.get("title", "")[:60] for g in group[1:]]
        logger.info(f"   [Dedup] Kept '{group[0].get('title', '')[:60]}' "
                    f"(year={group[0].get('year', '?')}), "
                    f"dropped {len(group) - 1} dup(s): {dropped_titles}")

    if dropped > 0:
        logger.info(f"   [Dedup] {len(papers)} → {len(result)} after fingerprint dedup "
                    f"({dropped} duplicates removed)")
    return result


# ═══════════════════════════════════════════════════════════════════════
# Semantic domain coherence (Fix 1: uses shared safe_normalize)
# ═══════════════════════════════════════════════════════════════════════

DOMAIN_ANCHOR_TEXTS = {
    "psychology": [
        "human cognition emotion behavior mental processes",
        "psychological theory experimental social cognitive research",
        "perception learning memory personality development",
        "clinical psychology behavioral intervention mental health",
    ],
    "computer science": [
        "algorithms computation software systems programming",
        "machine learning neural networks artificial intelligence",
        "distributed systems databases operating systems",
    ],
    "biology": [
        "cellular molecular organism evolution genetics",
        "biological processes ecosystems species physiology",
        "biochemistry protein structure gene expression",
    ],
    "physics": [
        "quantum mechanics classical physics relativity",
        "particle physics condensed matter thermodynamics",
        "electromagnetism optics field theory",
    ],
    "medicine": [
        "clinical treatment disease patient diagnosis",
        "medical therapy pharmacology pathology",
        "epidemiology public health randomized controlled trial",
    ],
    "economics": [
        "economic theory markets monetary fiscal policy",
        "microeconomics macroeconomics econometrics",
        "trade growth inflation labor markets",
    ],
    "mathematics": [
        "mathematical theorem proof algebra topology",
        "analysis geometry number theory",
        "differential equations probability statistics",
    ],
}

DOMAIN_THRESHOLDS = {
    "psychology":       0.25,
    "computer science": 0.22,
    "biology":          0.25,
    "physics":          0.25,
    "medicine":         0.25,
    "economics":        0.25,
    "mathematics":      0.25,
}

DEFAULT_DOMAIN_THRESHOLD = 0.20


def build_domain_anchor(domain: str) -> Optional[np.ndarray]:
    """Build domain centroid embedding using shared safe_normalize."""
    if not domain:
        return None
    key = domain.lower().strip()
    texts = DOMAIN_ANCHOR_TEXTS.get(key)
    if not texts:
        return None

    try:
        from core import specter_ranker
        if not specter_ranker.is_available():
            return None
        embs = specter_ranker._embed_texts(texts)
        if embs.shape[0] == 0:
            return None
        centroid = embs.mean(axis=0, keepdims=True)  # (1, 768)
        normed, valid = safe_normalize(centroid)
        if not valid[0]:
            return None
        return normed
    except Exception as e:
        logger.debug(f"   [DomainFilter] Failed to build anchor for '{domain}': {e}")
        return None


def semantic_domain_filter(
    papers: List[dict],
    paper_embeddings: np.ndarray,
    domain: str,
    seed_titles: Optional[List[str]] = None,
) -> Tuple[List[dict], np.ndarray]:
    """
    Filter papers whose embedding is too far from domain centroid.
    Uses shared safe_normalize — NO divide-by-zero warnings.
    """
    if paper_embeddings is None or paper_embeddings.shape[0] == 0:
        return papers, paper_embeddings
    if len(papers) != paper_embeddings.shape[0]:
        logger.warning(f"   [DomainFilter] Size mismatch: {len(papers)} papers vs "
                       f"{paper_embeddings.shape[0]} embeddings — skipping")
        return papers, paper_embeddings

    anchor = build_domain_anchor(domain)
    if anchor is None:
        logger.info(f"   [DomainFilter] No anchor for domain '{domain}' — skipping")
        return papers, paper_embeddings

    threshold = DOMAIN_THRESHOLDS.get((domain or "").lower().strip(), DEFAULT_DOMAIN_THRESHOLD)

    # Fix 1: use shared safe_normalize — no ad-hoc matmul normalization
    normed, valid_paper_mask = safe_normalize(paper_embeddings)
    # anchor is already normalized by build_domain_anchor
    sims = safe_cosine_sim(normed, anchor).squeeze(axis=-1)

    # Invalid (zero-vector) papers get similarity 0 → will fail threshold
    sims[~valid_paper_mask] = 0.0

    seed_title_set = set()
    if seed_titles:
        seed_title_set = {(t or "").lower().strip() for t in seed_titles if t}

    kept_idx = []
    dropped_titles = []
    for i, (paper, sim) in enumerate(zip(papers, sims)):
        title_lower = (paper.get("title", "") or "").lower().strip()
        is_seed = paper.get("_is_seed", False) or title_lower in seed_title_set

        if is_seed or sim >= threshold:
            kept_idx.append(i)
        else:
            dropped_titles.append((paper.get("title", "")[:60], float(sim)))

    if dropped_titles:
        logger.info(f"   [DomainFilter] Domain='{domain}', threshold={threshold:.2f}, "
                    f"dropped {len(dropped_titles)}/{len(papers)} off-domain papers")
        for title, sim in dropped_titles[:5]:
            logger.info(f"      ✂️  [{sim:.3f}] {title}")
        if len(dropped_titles) > 5:
            logger.info(f"      ... and {len(dropped_titles) - 5} more")

    kept_papers = [papers[i] for i in kept_idx]
    kept_embs = paper_embeddings[kept_idx] if kept_idx else paper_embeddings[:0]
    return kept_papers, kept_embs