import os
import asyncio
import hashlib
import logging
from typing import Optional
from dataclasses import dataclass, field, asdict

import httpx
import fitz

from core.config import Config

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_BASE = Config.SEMANTIC_SCHOLAR_BASE_URL
UNPAYWALL_BASE = Config.UNPAYWALL_BASE_URL
PMC_BASE = Config.PMC_BASE_URL

PDF_DIR = Config.PDF_DIR
SEMANTIC_SCHOLAR_API_KEY = Config.SEMANTIC_SCHOLAR_API_KEY
UNPAYWALL_EMAIL = Config.UNPAYWALL_EMAIL
USER_AGENT = Config.USER_AGENT


@dataclass
class Paper:
    title: str = ""
    abstract: str = ""
    full_text: str = ""
    source: str = ""
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    corpus_id: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_source: str = ""
    semantic_scholar_url: Optional[str] = None
    year: Optional[int] = None
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None
    venue: str = ""
    journal: str = ""
    publication_date: Optional[str] = None
    fields_of_study: list[str] = field(default_factory=list)
    is_open_access: bool = False
    tldr: str = ""
    authors: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class PaperFinder:
    def __init__(self):
        os.makedirs(PDF_DIR, exist_ok=True)
        self.ss_headers = {"User-Agent": USER_AGENT}
        if SEMANTIC_SCHOLAR_API_KEY:
            self.ss_headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    async def find_papers(self, topic: str, max_results: int = 10) -> list[Paper]:
        logger.info(f"[PaperFinder] Searching: '{topic}' (max {max_results})")
        papers = await self._search_semantic_scholar(topic, max_results)
        return papers

    async def _search_semantic_scholar(self, topic: str, max_results: int) -> list[Paper]:
        papers = []
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                params = {
                    "query": topic,
                    "limit": min(max_results, 20),
                    "fields": (
                        "title,abstract,year,authors,citationCount,referenceCount,"
                        "externalIds,openAccessPdf,url,venue,journal,"
                        "publicationDate,fieldsOfStudy,isOpenAccess,tldr"
                    ),
                }
                resp = await client.get(
                    f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
                    params=params,
                    headers=self.ss_headers
                )
                if resp.status_code != 200:
                    logger.warning(f"[PaperFinder] Semantic Scholar returned {resp.status_code}")
                    return []
                data = resp.json()
                for item in data.get("data", []):
                    title = item.get("title", "")
                    if not title:
                        continue
                    ext_ids = item.get("externalIds") or {}
                    authors = [a.get("name", "") for a in (item.get("authors") or [])[:5] if a.get("name")]
                    oa_pdf = item.get("openAccessPdf") or {}
                    pdf_url = oa_pdf.get("url", "") if isinstance(oa_pdf, dict) else ""
                    papers.append(Paper(
                        title=title.strip(),
                        abstract=(item.get("abstract", "") or "").strip(),
                        source="semantic_scholar",
                        doi=ext_ids.get("DOI"),
                        arxiv_id=ext_ids.get("ArXiv"),
                        pubmed_id=ext_ids.get("PubMed"),
                        corpus_id=str(ext_ids.get("CorpusId", "")) if ext_ids.get("CorpusId") else None,
                        pdf_url=pdf_url or None,
                        pdf_source="semantic_scholar_oa" if pdf_url else "",
                        semantic_scholar_url=item.get("url", ""),
                        year=item.get("year"),
                        citation_count=item.get("citationCount", 0),
                        reference_count=item.get("referenceCount", 0),
                        venue=item.get("venue", "") or "",
                        journal=(item.get("journal") or {}).get("name", "") if isinstance(item.get("journal"), dict) else "",
                        publication_date=item.get("publicationDate"),
                        fields_of_study=item.get("fieldsOfStudy") or [],
                        is_open_access=bool(item.get("isOpenAccess", False)),
                        tldr=(item.get("tldr") or {}).get("text", "") if isinstance(item.get("tldr"), dict) else "",
                        authors=authors,
                    ))
        except Exception as e:
            logger.warning(f"[PaperFinder] Semantic Scholar error: {e}")
        return papers