# src/core/citation_graph.py

import httpx
import time
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class CitationGraphExpander:
    SS_BASE = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0,
                 max_retries: int = 3, rate_limit_sleep: float = 1.1):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_sleep = rate_limit_sleep
        self._client = httpx.Client(timeout=timeout)

    def _headers(self) -> Dict[str, str]:
        h = {"User-Agent": "CogniView.AI/1.0"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _ss_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Resilient Semantic Scholar GET with retry + backoff.
        Returns parsed JSON or None on failure.
        """
        url = f"{self.SS_BASE}{path}"
        for attempt in range(self.max_retries):
            try:
                r = self._client.get(url, params=params or {}, headers=self._headers())
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    wait = self.rate_limit_sleep * (2 ** attempt)
                    logger.warning(f"   [SS] 429 rate-limited, sleeping {wait:.1f}s")
                    time.sleep(wait)
                    continue
                if r.status_code in (404, 400):
                    logger.debug(f"   [SS] {r.status_code} for {path}")
                    return None
                logger.warning(f"   [SS] HTTP {r.status_code} for {path}")
            except (httpx.TimeoutException, httpx.RequestError) as e:
                logger.warning(f"   [SS] attempt {attempt+1} failed: {e}")
            time.sleep(self.rate_limit_sleep * (attempt + 1))
        return None

    def expand(self, seeds: List[Any], limit_refs: int = 30,
               limit_cits: int = 30, limit_co_citations: int = 20) -> List[Dict]:
        """
        Expand from seed papers via references, citations, and lightweight
        co-citation evidence. Accepts Semantic Scholar IDs, Paper objects, or
        paper dictionaries.
        """
        collected: Dict[str, Dict] = {}
        for seed in seeds:
            pid = self._paper_id(seed)
            if not pid:
                title = self._paper_title(seed)
                pid = self._resolve_by_title(title) if title else ""
            if not pid:
                continue

            refs = self._ss_get(
                f"/paper/{pid}/references",
                {"limit": limit_refs,
                 "fields": "paperId,title,abstract,year,citationCount,venue,authors,externalIds,openAccessPdf"}
            )
            cits = self._ss_get(
                f"/paper/{pid}/citations",
                {"limit": limit_cits,
                 "fields": "paperId,title,abstract,year,citationCount,venue,authors,externalIds,openAccessPdf"}
            )
            for bucket in (refs, cits):
                if not bucket or "data" not in bucket:
                    continue
                for row in bucket["data"]:
                    p = row.get("citedPaper") or row.get("citingPaper") or {}
                    self._add_paper(collected, p)

            for ref in ((refs or {}).get("data", []) or [])[:limit_co_citations]:
                ref_paper = ref.get("citedPaper") or {}
                ref_pid = ref_paper.get("paperId")
                if not ref_pid:
                    continue
                co_cits = self._ss_get(
                    f"/paper/{ref_pid}/citations",
                    {"limit": 10,
                     "fields": "paperId,title,abstract,year,citationCount,venue,authors,externalIds,openAccessPdf"}
                )
                for row in ((co_cits or {}).get("data", []) or []):
                    self._add_paper(collected, row.get("citingPaper") or {})

            time.sleep(self.rate_limit_sleep)
        return list(collected.values())

    def _add_paper(self, collected: Dict[str, Dict], paper: Dict[str, Any]):
        pid = paper.get("paperId")
        if pid and pid not in collected and paper.get("title"):
            collected[pid] = self._normalize_paper(paper)

    def _paper_id(self, seed: Any) -> str:
        if isinstance(seed, str):
            return seed
        if isinstance(seed, dict):
            return seed.get("paper_id") or seed.get("paperId") or ""
        return getattr(seed, "paper_id", "") or getattr(seed, "paperId", "") or ""

    def _paper_title(self, seed: Any) -> str:
        if isinstance(seed, dict):
            return seed.get("title", "") or ""
        return getattr(seed, "title", "") or ""

    def _resolve_by_title(self, title: str) -> str:
        data = self._ss_get(
            "/paper/search/match",
            {"query": title[:200], "fields": "paperId,title"},
        )
        rows = (data or {}).get("data", []) or []
        return rows[0].get("paperId", "") if rows else ""

    @staticmethod
    def _normalize_paper(paper: Dict[str, Any]) -> Dict[str, Any]:
        ext = paper.get("externalIds") or {}
        authors = [
            a.get("name", "") for a in (paper.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        oa = paper.get("openAccessPdf") or {}
        pdf_url = oa.get("url", "") if isinstance(oa, dict) else ""
        arxiv_id = ext.get("ArXiv", "") or ""
        if not pdf_url and arxiv_id:
            clean = arxiv_id.replace("arXiv:", "").replace("arxiv:", "").strip()
            pdf_url = f"https://arxiv.org/pdf/{clean}.pdf"
        return {
            "paper_id": paper.get("paperId", "") or "",
            "title": paper.get("title", "") or "",
            "authors": authors,
            "abstract": paper.get("abstract", "") or "",
            "year": paper.get("year", 0) or 0,
            "citation_count": paper.get("citationCount", 0) or 0,
            "venue": paper.get("venue", "") or "",
            "doi": ext.get("DOI", "") or "",
            "arxiv_id": arxiv_id,
            "pdf_url": pdf_url,
            "source": "semantic_scholar_citation_graph",
            "discovery_phase": "stage2b_citation_graph",
        }
