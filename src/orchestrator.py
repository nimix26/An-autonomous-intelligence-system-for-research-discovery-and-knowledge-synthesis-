"""
Orchestrator — Coordinates the 3-agent pipeline with FULL context awareness.

Flow:
  1. Agent 1 (Paper Finder) → collect papers (count based on context)
  2. Agent 2 (Prompt Builder) → build context-aware prompt
  3. Agent 3 (Summarizer) → generate synthesis

Context Controls:
  - Persona × Depth × Time Budget → number of papers fetched AND sent to LLM
  - Goal → which sections LLM generates (gaps/ideas only for Publish)
  - Goal → which tabs Dashboard 2 shows (visible_tabs)
"""

import logging
from typing import Optional

from agents.paper_finder import PaperFinder
from agents.prompt_builder import PromptBuilder, UserContext, DEPTH_MAP, TIME_BUDGET_MAP
from agents.summarizer import Summarizer

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  SINGLE SOURCE OF TRUTH: How many papers go to LLM
#  (Persona, Depth, Time Budget) → exact paper count
# ═════════════════════════════════════════════════════���═════

PAPER_LIMIT = {
    # Learner — wants fewer, simpler results
    ("Learner", "Skim", "Quick"): 1,
    ("Learner", "Skim", "Focused"): 2,
    ("Learner", "Skim", "DeepResearch"): 3,
    ("Learner", "Understand", "Quick"): 2,
    ("Learner", "Understand", "Focused"): 3,
    ("Learner", "Understand", "DeepResearch"): 5,
    ("Learner", "DeepDive", "Quick"): 3,
    ("Learner", "DeepDive", "Focused"): 5,
    ("Learner", "DeepDive", "DeepResearch"): 7,

    # Educator — moderate amount, prefers reviews/surveys
    ("Educator", "Skim", "Quick"): 2,
    ("Educator", "Skim", "Focused"): 3,
    ("Educator", "Skim", "DeepResearch"): 5,
    ("Educator", "Understand", "Quick"): 3,
    ("Educator", "Understand", "Focused"): 5,
    ("Educator", "Understand", "DeepResearch"): 8,
    ("Educator", "DeepDive", "Quick"): 5,
    ("Educator", "DeepDive", "Focused"): 8,
    ("Educator", "DeepDive", "DeepResearch"): 10,

    # Researcher — wants maximum coverage
    ("Researcher", "Skim", "Quick"): 3,
    ("Researcher", "Skim", "Focused"): 5,
    ("Researcher", "Skim", "DeepResearch"): 8,
    ("Researcher", "Understand", "Quick"): 5,
    ("Researcher", "Understand", "Focused"): 8,
    ("Researcher", "Understand", "DeepResearch"): 12,
    ("Researcher", "DeepDive", "Quick"): 8,
    ("Researcher", "DeepDive", "Focused"): 10,
    ("Researcher", "DeepDive", "DeepResearch"): 15,
}


def get_paper_limit(persona: str, depth: str, time_budget: str) -> int:
    """Single function to get exact paper count for any context combination."""
    limit = PAPER_LIMIT.get((persona, depth, time_budget))
    if limit is not None:
        return limit
    # Fallback: use a sensible default
    fallback = {
        "Skim": 3,
        "Understand": 5,
        "DeepDive": 8,
    }
    return fallback.get(depth, 5)


# ═══════════════════════════════════════════════════════════
#  Context → Search Query Enhancement
# ═══════════════════════════════════════════════════════════

GOAL_SEARCH_MODIFIERS = {
    "Learn": "",
    "Teach": "survey review tutorial",
    "Publish": "novel method framework analysis",
}

PERSONA_SEARCH_MODIFIERS = {
    "Learner": "introduction fundamentals",
    "Educator": "review survey pedagogy",
    "Researcher": "methodology analysis recent",
}

# ═══════════════════════════════════════════════════════════
#  Context → Visible Tabs (what Dashboard 2 shows)
# ═══════════════════════════════════════════════════════════

VISIBLE_TABS_MAP = {
    "Learn": ["summary", "insights", "papers"],
    "Teach": ["summary", "insights", "papers"],
    "Publish": ["summary", "insights", "gaps", "papers", "ideas"],
}

# ═══════════════════════════════════════════════════════════
#  Context → Sections to Generate (what the LLM produces)
# ═══════════════════════════════════════════════════════════

SECTIONS_MAP = {
    "Learn": ["summary", "insights"],
    "Teach": ["summary", "insights"],
    "Publish": ["summary", "insights", "gaps", "ideas"],
}


class Orchestrator:
    """Coordinates the research pipeline with full context awareness."""

    def __init__(self):
        self.paper_finder = PaperFinder()
        self.prompt_builder = PromptBuilder()
        self.summarizer = Summarizer()

    async def run_pipeline(self, request: dict) -> dict:
        """Execute the full 3-agent pipeline."""
        logger.info(f"[Orchestrator] Starting pipeline for topic: {request['topic']}")

        # ═══════════════════════════════════════════════════
        #  STEP 0: Build User Context & Determine All Rules
        # ═══════════════════════════════════════════════════

        context = UserContext(
            topic=request["topic"],
            persona=request.get("persona", "Learner"),
            depth=request.get("depth", "Understand"),
            knowledge_level=request.get("knowledge_level", "Intermediate"),
            time_budget=request.get("time_budget", "Focused"),
            goal=request.get("goal", "Learn"),
            output_format=request.get("output_format", "Structured"),
        )

        # ── THE paper limit — one number, used everywhere ──
        paper_limit = get_paper_limit(context.persona, context.depth, context.time_budget)
        visible_tabs = VISIBLE_TABS_MAP.get(context.goal, ["summary", "insights", "papers"])
        sections = SECTIONS_MAP.get(context.goal, ["summary", "insights"])

        logger.info(
            f"[Orchestrator] Context: persona={context.persona}, "
            f"depth={context.depth}, knowledge={context.knowledge_level}, "
            f"time={context.time_budget}, goal={context.goal}, "
            f"format={context.output_format}"
        )
        logger.info(
            f"[Orchestrator] Rules: "
            f"paper_limit={paper_limit}, "
            f"tabs={visible_tabs}, "
            f"sections={sections}"
        )

        # ═══════════════════════════════════════════════════
        #  STEP 1: Context-Aware Paper Search
        #  Fetch MORE than needed so ranking has options
        # ═══════════════════════════════════════════════════

        search_query = self._build_search_query(context)

        # Fetch extra papers so ranking can pick the best ones
        # Fetch 2x the limit (min 5, max 25) to give ranking room
        fetch_count = min(max(paper_limit * 2, 5), 25)

        logger.info(
            f"[Orchestrator] Phase 1: Fetching up to {fetch_count} papers "
            f"(will select best {paper_limit}) | Query: '{search_query}'"
        )

        papers = await self.paper_finder.find_papers(
            topic=search_query,
            max_results=fetch_count,
        )
        paper_dicts = [p.to_dict() for p in papers]

        if len(paper_dicts) == 0:
            logger.warning("[Orchestrator] No papers found!")
            return {
                "summary": (
                    "No research papers were found for the given topic. "
                    "Try a different or more specific search term."
                ),
                "key_insights": [],
                "gaps": [],
                "ideas": [],
                "papers_found": 0,
                "analysis_mode": "none",
                "papers_metadata": [],
                "visible_tabs": ["summary"],
            }

        # ═══════════════════════════════════════════════════
        #  STEP 1.5: Rank & Select EXACTLY paper_limit papers
        # ═══════════════════════════════════════════════════

        paper_dicts = self._rank_and_select_papers(paper_dicts, context, paper_limit)

        has_full_text = any(
            p.get("full_text", "").strip() for p in paper_dicts
        )

        logger.info(
            f"[Orchestrator] After ranking: {len(paper_dicts)} papers selected "
            f"(limit was {paper_limit}), full_text={'YES' if has_full_text else 'NO'}"
        )

        # ═══════════════════════════════════════════════════
        #  STEP 2: Context-Aware Prompt Building
        # ═══════════════════════════════════════════════════

        logger.info("[Orchestrator] Phase 2: Building context-aware prompt...")

        master_prompt = self.prompt_builder.build_prompt(
            context=context,
            paper_count=len(paper_dicts),
            has_full_text=has_full_text,
            sections_to_generate=sections,
        )

        papers_text = self.prompt_builder.format_papers_for_prompt(
            papers=paper_dicts,
            context=context,
            has_full_text=has_full_text,
        )

        # Print debug info to terminal
        self._print_debug_info(
            context, master_prompt, papers_text, paper_dicts,
            has_full_text, visible_tabs, sections, paper_limit
        )

        # ═══════════════════════════════════════════════════
        #  STEP 3: Summarization
        # ═══════════════════════════════════════════════════

        logger.info("[Orchestrator] Phase 3: Running Summarizer...")
        result = await self.summarizer.summarize(master_prompt, papers_text)

        # Print LLM response to terminal
        self._print_llm_response(result)

        # ═══════════════════════════════════════════════════
        #  STEP 4: Post-Processing & Enforcement
        # ═══════════════════════════════════════════════════

        result = self._post_process_result(result, context)

        # Enforce: clear arrays if goal doesn't include them
        if "gaps" not in sections:
            result["gaps"] = []
        if "ideas" not in sections:
            result["ideas"] = []

        # Add metadata
        result["papers_found"] = len(paper_dicts)
        result["analysis_mode"] = (
            "full_text"
            if self.prompt_builder._is_deep_analysis(context) and has_full_text
            else "abstract_based"
        )
        result["papers_metadata"] = [
            {
                "title": p.get("title", ""),
                "authors": p.get("authors", []),
                "year": p.get("year"),
                "source": p.get("source", ""),
                "citation_count": p.get("citation_count", 0),
            }
            for p in paper_dicts
        ]
        result["visible_tabs"] = visible_tabs

        logger.info(
            f"[Orchestrator] === Pipeline Complete ===\n"
            f"  Papers sent to LLM: {len(paper_dicts)} (limit: {paper_limit})\n"
            f"  Tabs: {visible_tabs}\n"
            f"  Insights: {len(result.get('key_insights', []))}\n"
            f"  Gaps: {len(result.get('gaps', []))}\n"
            f"  Ideas: {len(result.get('ideas', []))}"
        )

        return result

    # ═══════════════════════════════════════════════════════
    #  DEBUG: Print to Terminal
    # ═══════════════════════════════════════════════════════

    def _print_debug_info(
        self, context, master_prompt, papers_text, paper_dicts,
        has_full_text, visible_tabs, sections, paper_limit
    ):
        """Print all context, prompt, and paper info to terminal."""
        print("\n")
        print("=" * 80)
        print("  CONTEXT RECEIVED FROM USER")
        print("=" * 80)
        print(f"  Topic:           {context.topic}")
        print(f"  Persona:         {context.persona}")
        print(f"  Depth:           {context.depth}")
        print(f"  Knowledge Level: {context.knowledge_level}")
        print(f"  Time Budget:     {context.time_budget}")
        print(f"  Goal:            {context.goal}")
        print(f"  Output Format:   {context.output_format}")
        print(f"  Paper Limit:     {paper_limit}")
        print(f"  Papers Selected: {len(paper_dicts)}")
        print(f"  Visible Tabs:    {visible_tabs}")
        print(f"  Sections to Gen: {sections}")
        print("=" * 80)

        print("\n")
        print("=" * 80)
        print("  PAPERS SENT TO LLM")
        print("=" * 80)
        for i, p in enumerate(paper_dicts):
            has_ft = "FULL TEXT" if p.get("full_text", "").strip() else "ABSTRACT ONLY"
            print(
                f"  [{i+1}] {p.get('title', 'Untitled')[:65]}\n"
                f"       Year: {p.get('year', '?')} | "
                f"Citations: {p.get('citation_count', 0)} | "
                f"Source: {p.get('source', '?')} | {has_ft}"
            )
        print("=" * 80)

        print("\n")
        print("=" * 80)
        print("  GENERATED MASTER PROMPT (sent to LLM)")
        print("=" * 80)
        print(master_prompt)
        print("=" * 80)

        print("\n")
        print("=" * 80)
        print(f"  PAPERS TEXT ({len(paper_dicts)} papers, {len(papers_text)} chars)")
        print("=" * 80)
        print(papers_text[:3000])
        if len(papers_text) > 3000:
            print(f"\n  ... [TRUNCATED — {len(papers_text) - 3000} more chars] ...")
        print("=" * 80)

        print("\n")
        print("=" * 80)
        print("  FULL PROMPT STATS")
        print("=" * 80)
        print(f"  Master prompt:   {len(master_prompt)} chars")
        print(f"  Papers text:     {len(papers_text)} chars")
        print(f"  Total to LLM:    {len(master_prompt) + len(papers_text)} chars")
        print(f"  Papers in prompt: {len(paper_dicts)} (limit: {paper_limit})")
        print(f"  Has full text:   {has_full_text}")
        print("=" * 80)
        print("\n")

    def _print_llm_response(self, result):
        """Print LLM response summary to terminal."""
        print("\n")
        print("=" * 80)
        print("  LLM RAW RESPONSE")
        print("=" * 80)
        print(f"  Summary length: {len(result.get('summary', ''))} chars")
        print(f"  Insights:       {len(result.get('key_insights', []))}")
        print(f"  Gaps:           {len(result.get('gaps', []))}")
        print(f"  Ideas:          {len(result.get('ideas', []))}")
        print("-" * 80)
        summary_preview = result.get("summary", "")[:500]
        print(summary_preview)
        if len(result.get("summary", "")) > 500:
            remaining = len(result.get("summary", "")) - 500
            print(f"\n  ... [TRUNCATED — {remaining} more chars]")
        print("=" * 80)
        print("\n")

    # ═══════════════════════════════════════════════════════
    #  CONTEXT-AWARE SEARCH QUERY
    # ═══════════════════════════════════════════════════════

    def _build_search_query(self, context: UserContext) -> str:
        """Enhance the topic search query based on user context."""
        base_topic = context.topic.strip()

        # goal_mod = GOAL_SEARCH_MODIFIERS.get(context.goal, "")

        # persona_mod = ""
        # if context.depth == "Skim" or context.knowledge_level == "Beginner":
        #     persona_mod = PERSONA_SEARCH_MODIFIERS.get(context.persona, "")

        # parts = [base_topic]
        # if goal_mod:
        #     parts.append(goal_mod)
        # if persona_mod and persona_mod not in goal_mod:
        #     parts.append(persona_mod)

        # enhanced_query = " ".join(parts)

        # if len(enhanced_query) > 100:
        #     enhanced_query = base_topic + " " + goal_mod

        # if len(enhanced_query) > 100:
        #     enhanced_query = base_topic

        # logger.info(
        #     f"[Orchestrator] Search query: '{base_topic}' -> '{enhanced_query}'"
        # )

        return base_topic

    # ═══════════════════════════════════════════════════════
    #  CONTEXT-AWARE PAPER RANKING
    #  Now takes paper_limit as argument — no second lookup
    # ═══════════════════════════════════════════════════════

    def _rank_and_select_papers(
        self, papers: list[dict], context: UserContext, paper_limit: int
    ) -> list[dict]:
        """Rank papers by relevance and select exactly paper_limit papers."""

        for paper in papers:
            score = 0

            # Citation score
            citations = paper.get("citation_count", 0) or 0
            if context.persona == "Researcher":
                if citations > 100:
                    score += 30
                elif citations > 20:
                    score += 20
                elif citations > 5:
                    score += 10
            else:
                if 5 < citations < 500:
                    score += 15
                elif citations >= 500:
                    score += 10

            # Recency score
            year = paper.get("year") or 0
            if year >= 2024:
                score += 25
            elif year >= 2022:
                score += 20
            elif year >= 2020:
                score += 15
            elif year >= 2015:
                score += 5

            if context.depth == "DeepDive" and year < 2015 and citations > 100:
                score += 15

            # Content availability
            has_abstract = bool(paper.get("abstract", "").strip())
            has_full_text = bool(paper.get("full_text", "").strip())

            if has_full_text:
                score += 20
            if has_abstract:
                score += 10

            # Title relevance
            title_lower = paper.get("title", "").lower()
            topic_words = context.topic.lower().split()
            matching_words = sum(1 for w in topic_words if w in title_lower)
            score += matching_words * 5

            # Goal-specific bonuses
            if context.goal == "Teach":
                for keyword in ["review", "survey", "tutorial", "overview", "introduction"]:
                    if keyword in title_lower:
                        score += 15
                        break

            if context.goal == "Publish":
                for keyword in ["novel", "new", "framework", "method", "approach", "improved"]:
                    if keyword in title_lower:
                        score += 10
                        break

            paper["_relevance_score"] = score

        # Sort by score (highest first)
        papers.sort(key=lambda p: p.get("_relevance_score", 0), reverse=True)

        # Log ranking
        for i, p in enumerate(papers):
            selected_marker = " ✓" if i < paper_limit else "  "
            logger.info(
                f"  [Rank {i+1}]{selected_marker} score={p.get('_relevance_score', 0)} | "
                f"{p.get('title', '')[:60]}..."
            )

        # ── SELECT EXACTLY paper_limit PAPERS ──
        selected = papers[:paper_limit]

        # Clean up internal score field from ALL papers
        for p in papers:
            p.pop("_relevance_score", None)

        logger.info(
            f"[Orchestrator] Selected {len(selected)}/{len(papers)} papers "
            f"(limit={paper_limit})"
        )

        return selected

    # ═══════════════════════════════════════════════════════
    #  POST-PROCESSING & VALIDATION
    # ═══════════════════════════════════════════════════════
    def _post_process_result(self, result: dict, context: UserContext) -> dict:
        """Validate that the LLM output matches the requested context."""
        summary = result.get("summary", "")
        insights = result.get("key_insights", [])

        # Length validation using the same formula as prompt builder
        depth_config = DEPTH_MAP.get(context.depth, {})
        time_config = TIME_BUDGET_MAP.get(context.time_budget, {})

        base_min = depth_config.get("base_min_words", 100)
        base_max = depth_config.get("base_max_words", 5000)
        multiplier = time_config.get("time_multiplier", 1.0)

        expected_min = int(base_min * multiplier)
        expected_max = int(base_max * multiplier)

        word_count = len(summary.split())

        if word_count < expected_min * 0.5:
            logger.warning(
                f"[Orchestrator] Summary too short: {word_count} words "
                f"(expected {expected_min}-{expected_max})"
            )
        if word_count > expected_max * 2:
            logger.warning(
                f"[Orchestrator] Summary too long: {word_count} words "
                f"(expected {expected_min}-{expected_max})"
            )

        # Insight count — trim for Skim mode
        if context.depth == "Skim" and len(insights) > 5:
            result["key_insights"] = insights[:5]
            logger.info("[Orchestrator] Trimmed insights to 5 for Skim mode")

        if context.depth == "DeepDive" and len(insights) < 3:
            logger.warning(
                f"[Orchestrator] DeepDive mode but only "
                f"{len(insights)} insights extracted"
            )

        # Goal validation
        if context.goal == "Publish" and not result.get("ideas"):
            logger.warning(
                "[Orchestrator] Goal is Publish but no research ideas generated"
            )

        return result