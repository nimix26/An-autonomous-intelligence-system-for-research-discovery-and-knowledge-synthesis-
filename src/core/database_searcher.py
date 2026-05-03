"""
core/database_searcher.py — Semantic Scholar + ArXiv only.

OpenAlex search is removed per pipeline spec. Semantic Scholar is the
single source for paper discovery. ArXiv remains only as a title-resolution
fallback for `search_by_title`.

Year-filtered searches, deduplication by normalized title.
All parse methods sanitize None values.
"""

import logging
import re
import requests
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import quote
from datetime import datetime

from models.paper import Paper, sanitize_dict
from core.config import Config
from core.pdf_downloader import PDFDownloader

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year


def _normalize_title(title: str) -> str:
    t = (title or "").lower().strip()
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:120]


class DatabaseSearcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ResearchPipeline/2.0"})
        if Config.SEMANTIC_SCHOLAR_API_KEY:
            self.session.headers["x-api-key"] = Config.SEMANTIC_SCHOLAR_API_KEY
        self.pdf_downloader = PDFDownloader()

    # ── Public API ────────────────────────────────────────────────────

    def search_papers(self, query: str, limit: int = 20) -> list:
        """Search Semantic Scholar (single source)."""
        return self.search_semantic_scholar(query, limit)

    def search_papers_with_openalex(self, query: str, limit: int = 20, year_filter: bool = False) -> list:
        """
        NOTE: Name retained for backward compatibility with orchestrator.
        OpenAlex is NO LONGER used. This now calls Semantic Scholar only.
        """
        return self.search_semantic_scholar(query, limit, year_filter=year_filter)

    def search_by_title(self, title: str) -> Optional[Paper]:
        """Resolve a single paper by title. Tries SS first, then ArXiv as fallback."""
        candidates = self.search_semantic_scholar(title, limit=5)
        if candidates:
            tl = title.lower().strip()
            best = sorted(candidates, key=lambda p: self._title_sim(p.title, tl), reverse=True)[0]
            if self._title_sim(best.title, title) >= 0.5:
                return best
            return candidates[0]
        arxiv = self.search_arxiv(title, max_results=5)
        return arxiv[0] if arxiv else None

    def search_pdf_fallback(self, paper: Paper) -> str:
        if not paper or not getattr(paper, 'title', ''):
            return ""
        paper_dict = {
            "title": paper.title if isinstance(paper, Paper) else "",
            "arxiv_id": paper.arxiv_id if isinstance(paper, Paper) else "",
            "doi": paper.doi if isinstance(paper, Paper) else "",
            "pdf_url": paper.pdf_url if isinstance(paper, Paper) else "",
            "authors": paper.authors if isinstance(paper, Paper) else [],
            "year": paper.year if isinstance(paper, Paper) else 0,
        }
        url = self.pdf_downloader.get_pdf_url(paper_dict)
        if url:
            return url
        filepath, _ = self.pdf_downloader.get_or_download(paper_dict)
        if filepath:
            return paper_dict.get("pdf_url", "")
        return ""

    # ── Semantic Scholar ──────────────────────────────────────────────

    def search_semantic_scholar(self, query: str, limit: int = 20, year_filter: bool = False) -> list:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": (
                "paperId,title,authors,abstract,year,citationCount,"
                "referenceCount,venue,externalIds,publicationDate,"
                "openAccessPdf,fieldsOfStudy,isOpenAccess,tldr,journal"
            ),
        }
        if year_filter:
            current_year = datetime.now().year
            min_year = current_year - int(Config.LATEST_PAPER_YEAR_WINDOW)
            params["year"] = f"{min_year}-{current_year}"

        try:
            r = self.session.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json().get("data", [])
            papers = [p for p in (self._parse_ss(x) for x in data) if p]
            pdf_count = sum(1 for p in papers if p.pdf_url)
            logger.info(f"   [SS] '{query[:50]}' → {len(papers)} papers ({pdf_count} with PDF)")
            return papers
        except Exception as e:
            logger.error(f"   [SS] Failed: {str(e)[:100]}")
            return []

    def _parse_ss(self, item: dict) -> Optional[Paper]:
        try:
            ext = item.get("externalIds") or {}
            authors = [a.get("name", "") for a in (item.get("authors") or []) if a.get("name")]

            pdf_url = ""
            oa = item.get("openAccessPdf") or {}
            if isinstance(oa, dict):
                pdf_url = oa.get("url", "") or ""

            arxiv_id = ext.get("ArXiv", "") or ""
            if not pdf_url and arxiv_id:
                clean_id = arxiv_id.replace("arXiv:", "").replace("arxiv:", "").strip()
                pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

            return Paper(
                paper_id=item.get("paperId", "") or "",
                title=item.get("title", "") or "",
                authors=authors,
                abstract=item.get("abstract", "") or "",
                year=item.get("year", 0) or 0,
                citation_count=item.get("citationCount", 0) or 0,
                venue=item.get("venue", "") or "",
                doi=ext.get("DOI", "") or "",
                arxiv_id=arxiv_id,
                publication_date=item.get("publicationDate", "") or "",
                pdf_url=pdf_url,
                source="semantic_scholar",
            )
        except Exception as e:
            logger.debug(f"   [SS] Parse error: {e}")
            return None

    # ── ArXiv (retained only for title-resolution fallback) ───────────

    def search_arxiv(self, query: str, max_results: int = 20) -> list:
        url = "http://export.arxiv.org/api/query"
        params = {"search_query": f"all:{quote(query)}", "start": 0,
                  "max_results": max_results, "sortBy": "relevance"}
        try:
            r = self.session.get(url, params=params, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            return [p for p in (self._parse_arxiv(e, ns) for e in root.findall("atom:entry", ns)) if p]
        except Exception:
            return []

    def _parse_arxiv(self, entry, ns) -> Optional[Paper]:
        try:
            title_el = entry.find("atom:title", ns)
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            summary_el = entry.find("atom:summary", ns)
            abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
            pub_el = entry.find("atom:published", ns)
            pub = (pub_el.text or "")[:10] if pub_el is not None else ""
            year = int(pub[:4]) if pub and pub[:4].isdigit() else 0

            authors = []
            for a in entry.findall("atom:author", ns):
                n = a.find("atom:name", ns)
                if n is not None and n.text:
                    authors.append(n.text)

            entry_id_el = entry.find("atom:id", ns)
            entry_id = entry_id_el.text or "" if entry_id_el is not None else ""
            arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else ""

            pdf_url = ""
            for l in entry.findall("atom:link", ns):
                if l.get("title") == "pdf":
                    pdf_url = l.get("href", "") or ""
                    break
            if not pdf_url and arxiv_id:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            return Paper(
                title=title, authors=authors, abstract=abstract,
                year=year, publication_date=pub, arxiv_id=arxiv_id,
                pdf_url=pdf_url, source="arxiv",
            )
        except Exception:
            return None

    @staticmethod
    def _title_sim(t1: str, t2: str) -> float:
        s1, s2 = set((t1 or "").lower().split()), set((t2 or "").lower().split())
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)
