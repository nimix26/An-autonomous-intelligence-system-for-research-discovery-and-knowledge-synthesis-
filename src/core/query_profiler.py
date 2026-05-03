"""
core/query_profiler.py — Stage 0: Query Profiling

Classifies the user's query along dimensions that drive every downstream
threshold. Replaces ALL hardcoded domain/field assumptions.
"""

import logging
from dataclasses import dataclass, field
from typing import List

from core.llm_service import LLMService

logger = logging.getLogger(__name__)


@dataclass
class QueryProfile:
    query: str = ""
    primary_domain: str = ""
    sub_domain: str = ""
    query_type: str = "broad_field"
    breadth: float = 0.5
    expected_paper_count: str = "medium"
    temporal_focus: str = "any"
    interdisciplinary: bool = False
    adjacent_domains: List[str] = field(default_factory=list)
    alternative_phrasings: List[str] = field(default_factory=list)
    paradigms: List[str] = field(default_factory=list)

    # Derived thresholds
    quality_percentile: int = 30
    mmr_lambda: float = 0.7
    target_seed_count: int = 4
    weight_recency: float = 0.15
    weight_cite_velocity: float = 0.25

    # NEW: relevance mode flag
    relevance_mode: bool = True  # True = kill recency, False = normal

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "primary_domain": self.primary_domain,
            "sub_domain": self.sub_domain,
            "query_type": self.query_type,
            "breadth": self.breadth,
            "temporal_focus": self.temporal_focus,
            "interdisciplinary": self.interdisciplinary,
            "adjacent_domains": self.adjacent_domains,
            "alternative_phrasings": self.alternative_phrasings,
            "paradigms": self.paradigms,
        }


class QueryProfiler:
    def __init__(self, llm_service: LLMService = None):
        self.llm = llm_service or LLMService()

    async def profile(
        self,
        query: str,
        relevance_mode: bool = True,
        user_field: str = "",
    ) -> QueryProfile:
        if not query or not query.strip():
            return QueryProfile(query=query or "", relevance_mode=relevance_mode)

        field_clause = ""
        if user_field:
            field_clause = (
                f'\nThe user selected this field of study: "{user_field}". '
                "Interpret ambiguous terms inside this field unless the query explicitly says otherwise."
            )

        prompt = f"""Analyze this research query: "{query}"{field_clause}

Return ONLY JSON with this exact schema:
{{
  "primary_domain": "the main academic field",
  "sub_domain": "more specific area within the field",
  "query_type": "one of: broad_field, specific_method, application, phenomenon, open_problem",
  "breadth": 0.0-1.0,
  "expected_paper_count": "one of: small, medium, large",
  "temporal_focus": "one of: historical, contemporary, cutting_edge, any",
  "interdisciplinary": true/false,
  "adjacent_domains": ["field1", "field2"],
  "alternative_phrasings": ["synonym1", "synonym2", "abbreviation"],
  "paradigms": ["paradigm1", "paradigm2", "paradigm3"]
}}

Guidelines:
- breadth: "transformers" = 0.9 (very broad), "BERT fine-tuning on biomedical NER" = 0.2 (narrow)
- paradigms: 2-7 natural sub-angles IN THIS FIELD. Do NOT force ML-style categories.
  For biology: mechanism, technique, model organism, disease context
  For math: foundational, computational, applications
  For humanities: period, methodology, region
- alternative_phrasings: 3-6 other ways researchers phrase the same concept
- Return ONLY valid JSON, no markdown."""

        parsed = None
        try:
            raw = await self.llm._call_api("discovery", prompt, temperature=0.2, max_tokens=2048)
            parsed = self.llm._extract_json(raw)
        except Exception as e:
            logger.warning(f"   [Stage0] LLM profiling failed: {e}")

        profile = QueryProfile(query=query)
        profile.relevance_mode = relevance_mode
        if user_field:
            profile.primary_domain = user_field

        if isinstance(parsed, dict):
            profile.primary_domain = user_field or str(parsed.get("primary_domain", "") or "")
            profile.sub_domain = str(parsed.get("sub_domain", "") or "")
            profile.query_type = str(parsed.get("query_type", "broad_field") or "broad_field")
            try:
                profile.breadth = max(0.0, min(1.0, float(parsed.get("breadth", 0.5))))
            except (ValueError, TypeError):
                profile.breadth = 0.5
            profile.expected_paper_count = str(parsed.get("expected_paper_count", "medium") or "medium")
            profile.temporal_focus = str(parsed.get("temporal_focus", "any") or "any")
            profile.interdisciplinary = bool(parsed.get("interdisciplinary", False))
            profile.adjacent_domains = [str(x) for x in (parsed.get("adjacent_domains", []) or []) if x][:5]
            profile.alternative_phrasings = [str(x) for x in (parsed.get("alternative_phrasings", []) or []) if x][:6]
            profile.paradigms = [str(x) for x in (parsed.get("paradigms", []) or []) if x][:7]

        # Override cutting_edge → any for broad queries
        if profile.breadth > 0.65 and profile.query_type in ("broad_field", "broad"):
            if profile.temporal_focus == "cutting_edge":
                logger.info("   [Stage0] Overriding temporal_focus: cutting_edge → any")
                profile.temporal_focus = "any"

        self._derive_thresholds(profile)

        logger.info(f"   [Stage0] domain={profile.primary_domain!r}, "
                    f"breadth={profile.breadth:.2f}, paradigms={len(profile.paradigms)}, "
                    f"temporal={profile.temporal_focus}, relevance_mode={profile.relevance_mode}")
        return profile

    @staticmethod
    def _derive_thresholds(p: QueryProfile):
        # Quality percentile based on breadth
        if p.breadth > 0.7:
            p.quality_percentile = 50
        elif p.breadth > 0.3:
            p.quality_percentile = 30
        else:
            p.quality_percentile = 10

        # MMR lambda
        if p.breadth > 0.7:
            p.mmr_lambda = 0.5
        elif p.breadth > 0.3:
            p.mmr_lambda = 0.7
        else:
            p.mmr_lambda = 0.85

        p.target_seed_count = max(2, min(6, len(p.paradigms) or 4))

        # Temporal weights
        if p.relevance_mode:
            # RELEVANCE MODE: recency is irrelevant.
            p.weight_recency = 0.0
            p.weight_cite_velocity = 0.35
            logger.info("   [Stage0] Relevance mode: weight_recency=0.0, "
                        "weight_cite_velocity=0.35")
        else:
            if p.temporal_focus == "cutting_edge":
                p.weight_recency = 0.30
                p.weight_cite_velocity = 0.15
            elif p.temporal_focus == "historical":
                p.weight_recency = 0.05
                p.weight_cite_velocity = 0.35
            else:
                p.weight_recency = 0.15
                p.weight_cite_velocity = 0.25
