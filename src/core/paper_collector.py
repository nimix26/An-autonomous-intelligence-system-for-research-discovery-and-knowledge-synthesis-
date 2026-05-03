"""Phase 3: Search databases with generated keywords and collect/deduplicate papers."""

import logging
import time

from models.paper import Paper
from core.database_searcher import DatabaseSearcher
from core.config import Config

logger = logging.getLogger(__name__)


class PaperCollector:
    def __init__(self, db_searcher: DatabaseSearcher):
        self.db = db_searcher

    def collect(self, keywords: list[str], phase1_papers: list[Paper]) -> list[Paper]:
        logger.info(f"[Phase3] Collecting using {len(keywords)} keywords")
        papers_map: dict[str, Paper] = {}

        for p in phase1_papers:
            key = (p.title or "").lower().strip()
            if key and len(key) > 10:
                papers_map[key] = p

        total_raw = 0

        for i, kw in enumerate(keywords):
            logger.info(f"[Phase3] Keyword {i+1}/{len(keywords)}: {kw}")

            ss = self.db.search_semantic_scholar(kw, limit=Config.MAX_DATABASE_RESULTS_PER_KEYWORD)
            total_raw += len(ss)
            for p in ss:
                p.discovery_phase = "phase2_keyword_search"
                p.relevance_keywords.append(kw)
                self._add_or_merge(papers_map, p)
            time.sleep(Config.API_DELAY_SECONDS)

            arx = self.db.search_arxiv(kw, max_results=Config.MAX_DATABASE_RESULTS_PER_KEYWORD)
            total_raw += len(arx)
            for p in arx:
                p.discovery_phase = "phase2_keyword_search"
                p.relevance_keywords.append(kw)
                self._add_or_merge(papers_map, p)
            time.sleep(Config.API_DELAY_SECONDS)

        final = list(papers_map.values())
        logger.info(f"[Phase3] Raw found={total_raw} | unique={len(final)}")
        return final

    def _add_or_merge(self, papers_map: dict[str, Paper], paper: Paper):
        key = (paper.title or "").lower().strip()
        if not key or len(key) < 10:
            return

        if key not in papers_map:
            papers_map[key] = paper
            return

        existing = papers_map[key]
        self._merge(existing, paper)

    def _merge(self, existing: Paper, new: Paper):
        if new.citation_count > existing.citation_count:
            existing.citation_count = new.citation_count

        if not existing.abstract and new.abstract:
            existing.abstract = new.abstract
        if not existing.doi and new.doi:
            existing.doi = new.doi
        if not existing.arxiv_id and new.arxiv_id:
            existing.arxiv_id = new.arxiv_id
        if not existing.pdf_url and new.pdf_url:
            existing.pdf_url = new.pdf_url
        if not existing.venue and new.venue:
            existing.venue = new.venue
        if not existing.year and new.year:
            existing.year = new.year
        if not existing.publication_date and new.publication_date:
            existing.publication_date = new.publication_date
        if not existing.authors and new.authors:
            existing.authors = new.authors

        existing.references = list(set(existing.references + new.references))
        existing.cited_by = list(set(existing.cited_by + new.cited_by))
        existing.relevance_keywords = list(set(existing.relevance_keywords + new.relevance_keywords))