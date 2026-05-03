"""
core/semantic_retriever.py — Stage 2C: Semantic Retrieval Channel

Uses Semantic Scholar Recommendations API to find papers that are
semantically similar to the seed set WITHOUT relying on keywords.

This is the third independent retrieval channel. It discovers papers that:
  - Citation graph misses  (not citing/cited-by seeds)
  - Keyword search misses  (different vocabulary, cross-domain community)
  - Are nearest neighbours to seeds in S2's internal SPECTER embedding space

Two API calls per run:
  1. Per-seed  → GET  /recommendations/v1/papers/forpaper/{id}
                 finds papers like each seed individually
  2. Batch     → POST /recommendations/v1/papers
                 finds papers like the COMBINATION of all seeds
                 (catches cross-paradigm papers that sit between multiple seeds)
"""

import logging
import re
import time
from typing import List, Optional

import requests

from core.config import Config
from models.paper import Paper

logger = logging.getLogger(__name__)

SS_REC_BASE   = "https://api.semanticscholar.org/recommendations/v1"
SS_GRAPH_BASE = "https://api.semanticscholar.org/graph/v1"

_PAPER_FIELDS = (
    "paperId,title,authors,abstract,year,citationCount,"
    "venue,externalIds,openAccessPdf"
)


class SemanticRetriever:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ResearchPipeline/3.0"})
        if Config.SEMANTIC_SCHOLAR_API_KEY:
            self.session.headers["x-api-key"] = Config.SEMANTIC_SCHOLAR_API_KEY

    # ── Public API ────────────────────────────────────────────────────

    def retrieve(self, seeds: List[Paper]) -> List[Paper]:
        """
        Return papers semantically similar to `seeds`.

        Merges per-seed recommendations with batch recommendations,
        deduplicates by normalised title, tags each paper with
        source="semantic_scholar_recommendations".
        """
        top_k   = Config.STAGE2C_TOP_K
        timeout = Config.STAGE2C_API_TIMEOUT

        papers_map: dict[str, Paper] = {}

        # ── Per-seed recommendations ──────────────────────────────────
        for i, seed in enumerate(seeds):
            seed_id = self._resolve_ss_id(seed, timeout)
            if not seed_id:
                logger.info(
                    f"   [Stage2C] Seed {i+1}: '{(seed.title or '')[:50]}' — "
                    f"no SS ID, skipping"
                )
                continue

            logger.info(
                f"   [Stage2C] Per-seed recs {i+1}/{len(seeds)}: "
                f"'{(seed.title or '')[:60]}'"
            )
            recs = self._get_single_paper_recs(seed_id, limit=50, timeout=timeout)
            for p in recs:
                key = _dedupe_key(p)
                if key and key not in papers_map:
                    p.discovery_phase = "stage2c_semantic"
                    papers_map[key] = p

            time.sleep(Config.API_DELAY_SECONDS)

        # ── Batch recommendations (all seeds as positives) ────────────
        seed_ids = [self._resolve_ss_id(s, timeout) for s in seeds]
        seed_ids = [sid for sid in seed_ids if sid]

        if len(seed_ids) >= 2:
            logger.info(
                f"   [Stage2C] Batch recs for {len(seed_ids)} seeds combined..."
            )
            batch_recs = self._get_batch_recs(seed_ids, limit=100, timeout=timeout)
            for p in batch_recs:
                key = _dedupe_key(p)
                if key and key not in papers_map:
                    p.discovery_phase = "stage2c_semantic"
                    papers_map[key] = p

        result = list(papers_map.values())
        logger.info(
            f"   [Stage2C] Total unique papers from semantic channel: {len(result)}"
        )
        return result[:top_k]

    # ── S2 API calls ──────────────────────────────────────────────────

    def _get_single_paper_recs(
        self, ss_id: str, limit: int, timeout: int
    ) -> List[Paper]:
        """GET /recommendations/v1/papers/forpaper/{paper_id}"""
        try:
            r = self.session.get(
                f"{SS_REC_BASE}/papers/forpaper/{ss_id}",
                params={"fields": _PAPER_FIELDS, "limit": limit},
                timeout=timeout,
            )
            if r.status_code == 404:
                logger.debug(f"   [Stage2C] No recs for {ss_id} (404)")
                return []
            if r.status_code != 200:
                logger.debug(f"   [Stage2C] Single-paper recs {r.status_code}")
                return []
            items = (r.json() or {}).get("recommendedPapers", []) or []
            return [p for p in (_parse_ss_paper(it) for it in items) if p]
        except Exception as e:
            logger.debug(f"   [Stage2C] Single-paper recs error: {e}")
            return []

    def _get_batch_recs(
        self, seed_ids: List[str], limit: int, timeout: int
    ) -> List[Paper]:
        """POST /recommendations/v1/papers — seeds as positives."""
        try:
            r = self.session.post(
                f"{SS_REC_BASE}/papers",
                json={
                    "positivePaperIds": seed_ids[:10],  # API allows max 10
                    "negativePaperIds": [],
                },
                params={"fields": _PAPER_FIELDS, "limit": limit},
                timeout=timeout,
            )
            if r.status_code != 200:
                logger.debug(f"   [Stage2C] Batch recs {r.status_code}")
                return []
            items = (r.json() or {}).get("recommendedPapers", []) or []
            return [p for p in (_parse_ss_paper(it) for it in items) if p]
        except Exception as e:
            logger.debug(f"   [Stage2C] Batch recs error: {e}")
            return []

    def _resolve_ss_id(self, paper: Paper, timeout: int) -> Optional[str]:
        """Resolve a Paper to its Semantic Scholar paper ID."""
        if paper.paper_id and len(paper.paper_id) > 10:
            return paper.paper_id

        # Try DOI
        if paper.doi:
            try:
                r = self.session.get(
                    f"{SS_GRAPH_BASE}/paper/DOI:{paper.doi}",
                    params={"fields": "paperId"},
                    timeout=timeout,
                )
                if r.status_code == 200:
                    pid = (r.json() or {}).get("paperId")
                    if pid:
                        return pid
            except Exception:
                pass

        # Try ArXiv ID
        if paper.arxiv_id:
            try:
                clean = (
                    paper.arxiv_id.replace("arXiv:", "")
                                  .replace("arxiv:", "")
                                  .strip()
                )
                r = self.session.get(
                    f"{SS_GRAPH_BASE}/paper/arXiv:{clean}",
                    params={"fields": "paperId"},
                    timeout=timeout,
                )
                if r.status_code == 200:
                    pid = (r.json() or {}).get("paperId")
                    if pid:
                        return pid
            except Exception:
                pass

        # Try title match
        if paper.title and len(paper.title) > 10:
            try:
                r = self.session.get(
                    f"{SS_GRAPH_BASE}/paper/search/match",
                    params={"query": paper.title[:200], "fields": "paperId,title"},
                    timeout=timeout,
                )
                if r.status_code == 200:
                    data = (r.json() or {}).get("data", [])
                    if data and data[0].get("paperId"):
                        return data[0]["paperId"]
            except Exception:
                pass

        return None


# ── Module-level helpers ──────────────────────────────────────────────

def _parse_ss_paper(item: dict) -> Optional[Paper]:
    if not item or not item.get("title"):
        return None
    ext      = item.get("externalIds") or {}
    authors  = [a.get("name", "") for a in (item.get("authors") or []) if a.get("name")]
    oa       = item.get("openAccessPdf") or {}
    pdf_url  = (oa.get("url", "") or "") if isinstance(oa, dict) else ""
    arxiv_id = ext.get("ArXiv", "") or ""
    if not pdf_url and arxiv_id:
        clean   = arxiv_id.replace("arXiv:", "").replace("arxiv:", "").strip()
        pdf_url = f"https://arxiv.org/pdf/{clean}.pdf"
    return Paper(
        paper_id       = item.get("paperId", "") or "",
        title          = item.get("title",   "") or "",
        authors        = authors[:10],
        abstract       = item.get("abstract", "") or "",
        year           = item.get("year",          0) or 0,
        citation_count = item.get("citationCount", 0) or 0,
        venue          = item.get("venue", "") or "",
        doi            = ext.get("DOI",   "") or "",
        arxiv_id       = arxiv_id,
        pdf_url        = pdf_url,
        source         = "semantic_scholar_recommendations",
    )


def _dedupe_key(p: Paper) -> str:
    t = (p.title or "").lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:120] if len(t) > 5 else ""