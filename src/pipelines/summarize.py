"""Summarization pipeline for top papers produced by DiscoveryPipeline."""

import logging
from models.paper import Paper
from core.llm_service import LLMService

logger = logging.getLogger(__name__)


class SummarizePipeline:
    def __init__(self):
        self.llm = LLMService()

    async def run(self, context, paper: dict, sections: list, visible_tabs: list, use_chunked: bool = True) -> dict:
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        full_text = paper.get("full_text", "")
        topic = getattr(context, "topic", "") if hasattr(context, "topic") else context.get("topic", "")

        s = await self.llm.summarize_paper(
            paper_title=title,
            paper_abstract=abstract,
            paper_text=full_text,
            topic=topic,
        )

        return {
            "summary": s.get("summary", ""),
            "key_insights": s.get("key_findings", []),
            "gaps": [s.get("limitations", "")] if s.get("limitations") else [],
            "ideas": [s.get("future_work", "")] if s.get("future_work") else [],
            "papers_found": 1,
            "analysis_mode": "single_paper_summary",
            "papers_metadata": [{
                "title": title,
                "authors": paper.get("authors", []),
                "year": paper.get("year"),
                "source": paper.get("source", ""),
                "citation_count": paper.get("citation_count", 0),
                "pdf_url": paper.get("pdf_url"),
            }],
            "visible_tabs": visible_tabs or ["summary", "insights", "papers"],
            "evidence": [],
            "visual_elements": [],
            "visual_groups": [],
            "datasets": [],
            "chunk_summaries": [],
            "implementation": {},
        }

    async def summarize_results(self, discovery_results: dict) -> dict:
        topic = discovery_results["topic"]
        top_papers = [Paper.from_dict(p) for p in discovery_results.get("top_papers", [])]

        summaries = []
        for p in top_papers:
            if not p.abstract:
                continue
            sd = await self.llm.summarize_paper(
                paper_title=p.title,
                paper_abstract=p.abstract,
                paper_text=p.full_text,
                topic=topic
            )
            summaries.append({
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "score": p.overall_score,
                **sd
            })

        synthesis = await self._synthesize(topic, summaries)
        return {
            "topic": topic,
            "individual_summaries": summaries,
            "synthesis": synthesis
        }

    async def _synthesize(self, topic: str, summaries: list[dict]) -> str:
        compact = "\n".join(
            f"{i+1}. {s.get('title','')}: {(s.get('summary','') or '')[:300]}"
            for i, s in enumerate(summaries)
        )
        prompt = f"""You are an expert research synthesizer.
Topic: {topic}

Paper summaries:
{compact}

Provide a coherent synthesis with themes, disagreements, and gaps."""
        return await self.llm.call_text(prompt)