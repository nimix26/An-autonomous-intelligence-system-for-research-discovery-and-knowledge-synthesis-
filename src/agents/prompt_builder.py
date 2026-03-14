"""
Agent 2 — Context Prompt Builder
Builds a dynamic master prompt for summarization based on user context.

Controls:
  - Persona → tone, emphasis, what to avoid
  - Depth → base word count, required sections, instruction style
  - Time Budget → word count multiplier, summary style
  - Knowledge Level → vocabulary, context, examples
  - Goal → focus, extras, whether to generate gaps/ideas
  - Output Format → structure (bullets/structured/report)
"""

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    topic: str
    persona: str       # Learner | Educator | Researcher
    depth: str          # Skim | Understand | DeepDive
    knowledge_level: str  # Beginner | Intermediate | Advanced
    time_budget: str    # Quick | Focused | DeepResearch
    goal: str           # Learn | Teach | Publish
    output_format: str  # Bullet | Structured | Report


# ═══════════════════════════════════════════════════════════
#  PERSONA MAP — Controls tone
# ═══════════════════════════════════════════════════════════

PERSONA_MAP = {
    "Learner": {
        "tone": "friendly, approachable, encouraging",
        "emphasis": "clear explanations, intuitive analogies, step-by-step breakdowns",
        "avoid": "dense jargon without explanation, assumed background knowledge",
    },
    "Educator": {
        "tone": "informative, authoritative yet accessible",
        "emphasis": "teachable frameworks, key takeaways for students, pedagogical structure",
        "avoid": "overly simplified content, missing nuance",
    },
    "Researcher": {
        "tone": "precise, academic, rigorous",
        "emphasis": "methodology analysis, statistical validity, novel contributions, limitations",
        "avoid": "oversimplification, missing citations, vague claims",
    },
}

# ═══════════════════════════════════════════════════════════
#  DEPTH MAP — Controls BASE word count and sections
# ═══════════════════════════════════════════════════════════

DEPTH_MAP = {
    "Skim": {
        "base_min_words": 200,
        "base_max_words": 400,
        "sections": ["Key Findings", "Quick Takeaways"],
        "instruction": "Provide a high-level executive summary. Focus on the 3-5 most important points.",
    },
    "Understand": {
        "base_min_words": 600,
        "base_max_words": 1200,
        "sections": ["Overview", "Key Findings", "Methodology Summary", "Implications", "Key Insights"],
        "instruction": "Provide a thorough yet digestible summary. Explain methodologies at a conceptual level.",
    },
    "DeepDive": {
        "base_min_words": 1500,
        "base_max_words": 3500,
        "sections": [
            "Comprehensive Overview",
            "Detailed Methodology Analysis",
            "Results & Statistical Findings",
            "Critical Analysis",
            "Cross-Paper Synthesis",
        ],
        "instruction": "Provide an exhaustive analysis. Critically evaluate methods, compare findings across papers, identify contradictions.",
    },
}

# ═══════════════════════════════════════════════════════════
#  TIME BUDGET MAP — Controls word count MULTIPLIER and style
#
#  Final word count = base_words × time_multiplier
#
#  Example: Skim (200-400) × Quick (0.7) = 140-280 words
#  Example: Skim (200-400) × DeepResearch (1.5) = 300-600 words
#  Example: DeepDive (1500-3500) × DeepResearch (1.5) = 2250-5250 words
# ═════���═════════════════════════════════════════════════════

TIME_BUDGET_MAP = {
    "Quick": {
        "time_multiplier": 0.7,
        "summary_style": "concise bullet points",
        "instruction": "Be extremely concise. Every sentence must carry weight. No filler.",
    },
    "Focused": {
        "time_multiplier": 1.0,
        "summary_style": "structured paragraphs with clear headers",
        "instruction": "Balance thoroughness with clarity. Use headers to organize.",
    },
    "DeepResearch": {
        "time_multiplier": 1.5,
        "summary_style": "comprehensive academic report with full detail",
        "instruction": "Be exhaustive. Include all relevant details, nuances, and cross-references.",
    },
}

# ═══════════════════════════════════════════════════════════
#  KNOWLEDGE MAP — Controls vocabulary level
# ═══════════════════════════════════════════════════════════

KNOWLEDGE_MAP = {
    "Beginner": {
        "vocabulary": "Use simple language. Define all technical terms on first use.",
        "context": "Provide background context for the field before diving into specifics.",
        "examples": "Include concrete examples and real-world analogies.",
    },
    "Intermediate": {
        "vocabulary": "Use standard domain terminology. Define only specialized or novel terms.",
        "context": "Briefly contextualize within the broader field.",
        "examples": "Include examples for complex concepts only.",
    },
    "Advanced": {
        "vocabulary": "Use full technical vocabulary without definitions unless novel.",
        "context": "Assume deep domain familiarity. Focus on novel contributions.",
        "examples": "Skip basic examples. Focus on edge cases and nuances.",
    },
}

# ═══════════════════════════════════════════════════════════
#  GOAL MAP — Controls focus and extras
# ═══════════════════════════════════════════════════════════

GOAL_MAP = {
    "Learn": {
        "focus": "understanding the landscape, building mental models",
        "extras": ["learning roadmap", "recommended next readings"],
    },
    "Teach": {
        "focus": "clear explanations, transferable frameworks, teaching angles",
        "extras": ["discussion questions", "key concepts to emphasize", "common misconceptions"],
    },
    "Publish": {
        "focus": "research gaps, novel angles, methodological improvements, positioning",
        "extras": ["potential research questions", "methodology suggestions", "positioning strategy"],
    },
}

# ═══════════════════════════════════════════════════════════
#  FORMAT MAP — Controls output structure
# ═══════════════════════════════════════════════════════════

FORMAT_MAP = {
    "Bullet": {
        "structure": "Use bullet points and short phrases. Group by theme.",
        "style": "- Point 1\n- Point 2\n  - Sub-point",
    },
    "Structured": {
        "structure": "Use clear section headers (##) with 2-4 sentence paragraphs per point.",
        "style": "## Section Header\nConcise paragraph explaining the point.\n",
    },
    "Report": {
        "structure": "Full academic report format with numbered sections, introduction, body, conclusion.",
        "style": "1. Introduction\n1.1 Background\n...\n2. Analysis\n...\n3. Conclusion",
    },
}


class PromptBuilder:
    """Agent 2: Builds dynamic master prompts based on user context."""

    def _calculate_word_range(self, context: UserContext) -> str:
        """
        Calculate final word count range.
        Formula: base_words (from depth) × time_multiplier (from time_budget)
        """
        depth_config = DEPTH_MAP.get(context.depth, DEPTH_MAP["Understand"])
        time_config = TIME_BUDGET_MAP.get(context.time_budget, TIME_BUDGET_MAP["Focused"])

        base_min = depth_config["base_min_words"]
        base_max = depth_config["base_max_words"]
        multiplier = time_config["time_multiplier"]

        final_min = int(base_min * multiplier)
        final_max = int(base_max * multiplier)

        logger.info(
            f"[PromptBuilder] Word count: "
            f"{base_min}-{base_max} (depth={context.depth}) "
            f"x {multiplier} (time={context.time_budget}) "
            f"= {final_min}-{final_max} words"
        )

        return f"{final_min}-{final_max} words"

    def build_prompt(
        self,
        context: UserContext,
        paper_count: int,
        has_full_text: bool,
        sections_to_generate: list = None,
    ) -> str:
        """Build the master summarization prompt."""

        if sections_to_generate is None:
            sections_to_generate = ["summary", "insights"]

        logger.info(
            f"[PromptBuilder] Building prompt: persona={context.persona}, "
            f"depth={context.depth}, time={context.time_budget}, "
            f"goal={context.goal}, sections={sections_to_generate}"
        )

        persona = PERSONA_MAP.get(context.persona, PERSONA_MAP["Learner"])
        depth = DEPTH_MAP.get(context.depth, DEPTH_MAP["Understand"])
        time_cfg = TIME_BUDGET_MAP.get(context.time_budget, TIME_BUDGET_MAP["Focused"])
        knowledge = KNOWLEDGE_MAP.get(context.knowledge_level, KNOWLEDGE_MAP["Intermediate"])
        goal = GOAL_MAP.get(context.goal, GOAL_MAP["Learn"])
        fmt = FORMAT_MAP.get(context.output_format, FORMAT_MAP["Structured"])

        deep_analysis = self._is_deep_analysis(context)
        analysis_mode = (
            "FULL-TEXT DEEP ANALYSIS"
            if (deep_analysis and has_full_text)
            else "ABSTRACT-BASED ANALYSIS"
        )

        # Calculate word range using depth × time_budget
        word_range = self._calculate_word_range(context)

        # Build required sections list
        required_sections = list(depth["sections"])

        should_generate_gaps = "gaps" in sections_to_generate
        should_generate_ideas = "ideas" in sections_to_generate

        if should_generate_gaps and "Research Gaps" not in required_sections:
            required_sections.append("Research Gaps")
        if should_generate_ideas and "Future Directions" not in required_sections:
            required_sections.append("Future Directions")

        # Build JSON output instructions
        json_instructions = self._build_json_instructions(sections_to_generate)

        # Build restriction notice
        restriction_notice = ""
        if not should_generate_gaps and not should_generate_ideas:
            restriction_notice = (
                "\n=== IMPORTANT: RESTRICTED OUTPUT ===\n"
                "DO NOT generate research gaps or research ideas sections.\n"
                "DO NOT include json_gaps or json_ideas blocks.\n"
                "The user only needs a summary and key insights.\n"
                "Focus entirely on explaining and synthesizing the content clearly.\n"
            )
        elif should_generate_gaps and not should_generate_ideas:
            restriction_notice = (
                "\n=== IMPORTANT: RESTRICTED OUTPUT ===\n"
                "DO NOT generate research ideas.\n"
                "DO NOT include a json_ideas block.\n"
                "You SHOULD identify research gaps.\n"
            )

        sections_str = "\n".join(f"- {s}" for s in required_sections)
        extras_str = "\n".join(f"- {e}" for e in goal["extras"])

        prompt = (
            f'You are an expert research synthesizer. Analyze the provided research papers '
            f'on the topic: "{context.topic}".\n\n'
            f'=== ANALYSIS MODE: {analysis_mode} ===\n'
            f'=== PAPERS PROVIDED: {paper_count} ===\n\n'
            f'=== YOUR ROLE ===\n'
            f'You are addressing a {context.persona} audience.\n'
            f'Tone: {persona["tone"]}\n'
            f'Emphasis: {persona["emphasis"]}\n'
            f'Avoid: {persona["avoid"]}\n\n'
            f'=== DEPTH & LENGTH ===\n'
            f'Target length: {word_range}\n'
            f'{depth["instruction"]}\n'
            f'{time_cfg["instruction"]}\n\n'
            f'=== VOCABULARY & CONTEXT ===\n'
            f'{knowledge["vocabulary"]}\n'
            f'{knowledge["context"]}\n'
            f'{knowledge["examples"]}\n\n'
            f'=== OUTPUT FORMAT ===\n'
            f'{fmt["structure"]}\n\n'
            f'=== REQUIRED SECTIONS ===\n'
            f'{sections_str}\n\n'
            f'=== GOAL-SPECIFIC ADDITIONS ===\n'
            f'Focus: {goal["focus"]}\n'
            f'Also include:\n'
            f'{extras_str}\n'
            f'{restriction_notice}\n'
            f'=== INSTRUCTIONS ===\n'
            f'1. Synthesize across papers — don\'t just summarize each paper individually.\n'
            f'2. Identify agreements and contradictions between papers.\n'
            f'3. You are analyzing {paper_count} papers. Use all of them.\n'
            f'4. Present findings as {time_cfg["summary_style"]}.\n'
            f'5. IMPORTANT: Keep your response within {word_range}. '
            f'Do not exceed the maximum word count.\n'
            f'{json_instructions}\n\n'
            f'=== PAPERS TO ANALYZE ===\n'
        )

        return prompt

    def _build_json_instructions(self, sections_to_generate: list) -> str:
        """Build JSON block instructions based on what sections are needed."""
        lines = []
        lines.append("")
        lines.append("6. At the END of your response, provide the following JSON blocks:")
        lines.append("")

        lines.append("A block named json_insights containing a JSON array of key insight strings:")
        lines.append('Example: ```json_insights')
        lines.append('["insight 1", "insight 2", "insight 3"]')
        lines.append('```')

        if "gaps" in sections_to_generate:
            lines.append("")
            lines.append("A block named json_gaps containing a JSON array of research gap strings:")
            lines.append('Example: ```json_gaps')
            lines.append('["gap 1", "gap 2", "gap 3"]')
            lines.append('```')

        if "ideas" in sections_to_generate:
            lines.append("")
            lines.append("A block named json_ideas containing a JSON array of research idea strings:")
            lines.append('Example: ```json_ideas')
            lines.append('["idea 1", "idea 2", "idea 3"]')
            lines.append('```')

        if "gaps" not in sections_to_generate:
            lines.append("")
            lines.append("DO NOT include a json_gaps block.")
        if "ideas" not in sections_to_generate:
            lines.append("")
            lines.append("DO NOT include a json_ideas block.")

        return "\n".join(lines)

    def _is_deep_analysis(self, context: UserContext) -> bool:
        """Check if full-text deep analysis should be triggered."""
        return (
            context.persona == "Researcher"
            and context.depth == "DeepDive"
            and context.time_budget == "DeepResearch"
            and context.goal == "Publish"
        )

    def format_papers_for_prompt(
        self, papers: list[dict], context: UserContext, has_full_text: bool
    ) -> str:
        """Format paper data for inclusion in the prompt."""
        deep_analysis = self._is_deep_analysis(context) and has_full_text
        formatted = []

        for i, paper in enumerate(papers, 1):
            entry = f"\n--- Paper {i} of {len(papers)} ---\n"
            entry += f"Title: {paper['title']}\n"

            if paper.get("authors"):
                entry += f"Authors: {', '.join(paper['authors'][:3])}\n"
            if paper.get("year"):
                entry += f"Year: {paper['year']}\n"
            if paper.get("citation_count"):
                entry += f"Citations: {paper['citation_count']}\n"

            entry += f"Source: {paper['source']}\n"

            if deep_analysis and paper.get("full_text"):
                text = paper["full_text"][:8000]
                entry += f"\nFull Text:\n{text}\n"
            else:
                entry += f"\nAbstract:\n{paper.get('abstract', 'No abstract available')}\n"

            formatted.append(entry)

        return "\n".join(formatted)