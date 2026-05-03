import logging
from core.llm_service import LLMService
from prompts import PromptBuilder, PERSONA_MAP, DEPTH_MAP, TIME_BUDGET_MAP, KNOWLEDGE_MAP, FORMAT_MAP
from schemas import UserContext

log = logging.getLogger(__name__)


class ComparePipeline:
    def __init__(self):
        self.llm = LLMService()
        self.prompt_builder = PromptBuilder()

    async def run(self, context: UserContext, papers: list[dict], sections: list, visible_tabs: list) -> dict:
        has_full_text = any(p.get("full_text", "").strip() for p in papers)
        master_prompt = self._build_comparison_prompt(context, papers, has_full_text, sections)
        papers_text = self.prompt_builder.format_papers_for_prompt(
            papers=papers, context=context, has_full_text=has_full_text
        )
        result = await self.llm.summarize(master_prompt, papers_text)
        result["papers_found"] = len(papers)
        result["analysis_mode"] = "comparison"
        result["papers_metadata"] = [
            {
                "title": p.get("title", ""),
                "authors": p.get("authors", []),
                "year": p.get("year"),
                "source": p.get("source", ""),
                "citation_count": p.get("citation_count", 0),
                "pdf_url": p.get("pdf_url"),
            }
            for p in papers
        ]
        result["visible_tabs"] = visible_tabs
        result["evidence"] = []
        result["visual_elements"] = []
        result["visual_groups"] = []
        result["datasets"] = []
        result["chunk_summaries"] = []
        result["implementation"] = {}
        return result

    def _build_comparison_prompt(self, context: UserContext, papers: list, has_full_text: bool, sections: list) -> str:
        persona_cfg = PERSONA_MAP.get(context.persona, PERSONA_MAP["Learner"])
        depth_cfg = DEPTH_MAP.get(context.depth, DEPTH_MAP["Understand"])
        time_cfg = TIME_BUDGET_MAP.get(context.time_budget, TIME_BUDGET_MAP["Focused"])
        knowledge_cfg = KNOWLEDGE_MAP.get(context.knowledge_level, KNOWLEDGE_MAP["Intermediate"])
        fmt_cfg = FORMAT_MAP.get(context.output_format, FORMAT_MAP["Structured"])

        m = time_cfg["time_multiplier"]
        word_range = f"{int(depth_cfg['base_min_words'] * m)}-{int(depth_cfg['base_max_words'] * m)} words"

        should_gaps = "gaps" in sections
        should_ideas = "ideas" in sections
        json_blocks = ['A block named json_insights:\n```json_insights\n["insight 1"]\n```']
        if should_gaps:
            json_blocks.append('A block named json_gaps:\n```json_gaps\n["gap 1"]\n```')
        if should_ideas:
            json_blocks.append('A block named json_ideas:\n```json_ideas\n["idea 1"]\n```')
        json_inst = "\n\n".join(json_blocks)

        prompt = (
            f'You are comparing {len(papers)} papers on "{context.topic}".\n\n'
            f'=== COMPARISON MODE ===\nProduce a STRUCTURED COMPARISON.\n\n'
            f'=== ROLE ===\nAudience: {context.persona}\nTone: {persona_cfg["tone"]}\n'
            f'Emphasis: {persona_cfg["emphasis"]}\nAvoid: {persona_cfg["avoid"]}\n\n'
            f'=== DEPTH ===\nTarget: {word_range}\n{depth_cfg["instruction"]}\n{time_cfg["instruction"]}\n\n'
            f'=== VOCABULARY ===\n{knowledge_cfg["vocabulary"]}\n{knowledge_cfg["context"]}\n\n'
            f'=== FORMAT ===\n{fmt_cfg["structure"]}\n\n'
            f'=== SECTIONS ===\n'
            f'1. **Overview** — Brief description of each paper\n'
            f'2. **Methodology Comparison**\n'
            f'3. **Key Findings Comparison**\n'
            f'4. **Strengths & Weaknesses**\n'
            f'5. **Synthesis**\n'
        )
        if should_gaps:
            prompt += '6. **Research Gaps**\n'
        if should_ideas:
            prompt += '7. **Future Directions**\n'

        prompt += (
            f'\n=== COMPARISON TABLE ===\n'
            f'| Aspect | Paper 1 | Paper 2 | ... |\nCover: Year, Method, Key Finding, Dataset, Limitations\n\n'
            f'=== INSTRUCTIONS ===\n1. COMPARE, don\'t just summarize.\n'
            f'2. Identify agreements/disagreements.\n'
            f'3. Keep within {word_range}.\n'
            f'4. At the END provide:\n\n{json_inst}\n\n=== PAPERS ===\n'
        )
        return prompt