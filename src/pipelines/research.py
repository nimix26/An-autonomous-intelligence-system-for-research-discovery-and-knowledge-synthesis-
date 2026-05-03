"""Research pipeline wrapping the new DiscoveryPipeline."""

import logging
from typing import Optional
from pipelines.discovery_pipeline import DiscoveryPipeline

logger = logging.getLogger(__name__)


class ResearchPipeline:
    def __init__(self):
        self.discovery = DiscoveryPipeline()

    async def run(self, context, paper: Optional[dict] = None) -> dict:
        """
        Backward-compatible async API.
        Ignores `paper` and performs new strict discovery pipeline by topic/context.
        """
        result = await self.discovery.run(
            topic=context.topic,
            context=context.goal,
            top_n=10,
            use_llm_relevance=True,
            summarize=True,
        )

        top = result.get("top_papers", [])
        best = top[0] if top else {}

        # Normalize to existing AnalyzeResponse-like shape
        return {
            "summary": best.get("summary", "No summary available."),
            "key_insights": best.get("key_findings", []),
            "gaps": [],
            "ideas": [],
            "papers_found": result.get("total_papers_found", 0),
            "analysis_mode": "research_discovery_pipeline",
            "papers_metadata": [
                {
                    "title": p.get("title", ""),
                    "authors": p.get("authors", []),
                    "year": p.get("year"),
                    "source": p.get("source", ""),
                    "citation_count": p.get("citation_count", 0),
                    "pdf_url": p.get("pdf_url"),
                }
                for p in top
            ],
            "visible_tabs": ["summary", "insights", "papers"],
            "evidence": [],
            "visual_elements": [],
            "visual_groups": [],
            "datasets": [],
            "chunk_summaries": [],
            "implementation": {},
            "pipeline_details": {
                "keywords_used": result.get("keywords_used", []),
                "phase1_count": result.get("phase1_count", 0),
                "top_n": result.get("top_n", 10),
            },
        }