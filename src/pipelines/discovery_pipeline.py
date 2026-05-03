"""
Main Discovery Pipeline
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from core.config import Config
from core.llm_service import LLMService
from core.database_searcher import DatabaseSearcher
from core.paper_discovery import PaperDiscovery
from core.keyword_generator import KeywordGenerator
from core.paper_collector import PaperCollector
from core.scoring import PaperScorer
from core.pdf_enricher import PDFEnricher

logger = logging.getLogger(__name__)


class DiscoveryPipeline:
    def __init__(self):
        Config.ensure_dirs()

        self.llm_service = LLMService()
        self.db_searcher = DatabaseSearcher()
        self.paper_discovery = PaperDiscovery(self.llm_service, self.db_searcher)
        self.keyword_generator = KeywordGenerator(self.llm_service)
        self.paper_collector = PaperCollector(self.db_searcher)
        self.paper_scorer = PaperScorer(self.llm_service)
        self.pdf_enricher = PDFEnricher()

    async def run(
        self,
        topic: str,
        context: str = "",
        top_n: Optional[int] = None,
        use_llm_relevance: bool = True,
        summarize: bool = True,
    ) -> dict:
        top_n = top_n or Config.TOP_N_PAPERS
        timestamp = datetime.now().isoformat()

        logger.info("=" * 70)
        logger.info(f"DISCOVERY PIPELINE START | Topic: {topic}")
        logger.info("=" * 70)

        phase1_papers = await self.paper_discovery.discover(topic, context)
        self._save_phase_results("phase1", phase1_papers, topic)

        keywords = await self.keyword_generator.generate(topic, phase1_papers)

        all_papers = self.paper_collector.collect(keywords, phase1_papers)
        self._save_phase_results("phase3_all", all_papers, topic)

        scored = await self.paper_scorer.score_all(
            papers=all_papers,
            topic=topic,
            context=context,
            use_llm_relevance=use_llm_relevance
        )

        top_papers = scored[:top_n]

        await self.pdf_enricher.enrich_top_papers_with_fulltext(top_papers)

        if summarize:
            for p in top_papers:
                s = await self.llm_service.summarize_paper(
                    paper_title=p.title,
                    paper_abstract=p.abstract,
                    paper_text=p.full_text,
                    topic=topic
                )
                p.summary = s.get("summary", "")
                p.key_findings = s.get("key_findings", [])
                p.methodology = s.get("methodology", "")

        result = {
            "topic": topic,
            "context": context,
            "timestamp": timestamp,
            "keywords_used": keywords,
            "phase1_count": len(phase1_papers),
            "total_papers_found": len(all_papers),
            "top_n": top_n,
            "top_papers": [p.to_dict() for p in top_papers],
            "all_scored_papers": [
                {
                    "title": p.title,
                    "overall_score": p.overall_score,
                    "year": p.year,
                    "citations": p.citation_count,
                    "source": p.source,
                }
                for p in scored
            ]
        }

        self._save_final_results(result, topic)
        self._print_summary(result)
        return result

    def _save_phase_results(self, phase_name: str, papers: list, topic: str):
        filename = f"{phase_name}_{self._sanitize(topic)}.json"
        filepath = os.path.join(Config.RAW_PAPERS_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([p.to_dict() for p in papers], f, indent=2, ensure_ascii=False)
            logger.info(f"[Save] {phase_name} -> {filepath}")
        except Exception as e:
            logger.warning(f"[Save] Could not save {phase_name}: {e}")

    def _save_final_results(self, result: dict, topic: str):
        filename = f"results_{self._sanitize(topic)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(Config.FINAL_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"[Save] final -> {filepath}")
        except Exception as e:
            logger.warning(f"[Save] Could not save final results: {e}")

    def _print_summary(self, result: dict):
        print("\n" + "=" * 72)
        print("RESEARCH PAPER DISCOVERY RESULTS")
        print("=" * 72)
        print(f"Topic: {result['topic']}")
        print(f"Phase-1 verified: {result['phase1_count']}")
        print(f"Total found: {result['total_papers_found']}")
        print(f"Top returned: {len(result['top_papers'])}")
        print("-" * 72)
        for i, p in enumerate(result["top_papers"], 1):
            print(f"{i:02d}. [{p.get('overall_score', 0):.3f}] {p.get('title', '')[:95]}")
        print("=" * 72 + "\n")

    @staticmethod
    def _sanitize(text: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)[:60]