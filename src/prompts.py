import logging
from schemas import UserContext

logger = logging.getLogger(__name__)

PERSONA_MAP = {
    "Learner": {
        "tone": "friendly, approachable, encouraging",
        "emphasis": "clear explanations, intuitive analogies, step-by-step breakdowns",
        "avoid": "dense jargon without explanation, assumed background knowledge"
    },
    "Educator": {
        "tone": "informative, authoritative yet accessible",
        "emphasis": "teachable frameworks, key takeaways for students, pedagogical structure",
        "avoid": "overly simplified content, missing nuance"
    },
    "Researcher": {
        "tone": "precise, academic, rigorous",
        "emphasis": "methodology analysis, statistical validity, novel contributions, limitations",
        "avoid": "oversimplification, missing citations, vague claims"
    },
}

DEPTH_MAP = {
    "Skim": {
        "base_min_words": 300, "base_max_words": 500,
        "sections": ["Key Findings", "Quick Takeaways"],
        "instruction": "Provide a high-level executive summary. Focus on the 3-5 most important points. Use headings and bullet points for clarity."
    },
    "Understand": {
        "base_min_words": 800, "base_max_words": 1500,
        "sections": ["Overview", "Key Findings", "Methodology Summary", "Implications", "Key Insights"],
        "instruction": "Provide a thorough yet digestible summary. Explain methodologies at a conceptual level. Structure with ## headings and use - bullet points for key details."
    },
    "DeepDive": {
        "base_min_words": 1800, "base_max_words": 4000,
        "sections": ["Comprehensive Overview", "Detailed Methodology Analysis", "Results & Statistical Findings", "Critical Analysis", "Cross-Paper Synthesis"],
        "instruction": "Provide an exhaustive analysis. Critically evaluate methods, compare findings across papers, identify contradictions. Use ## headings for each section and ### sub-headings. Use - bullet points to enumerate specific findings."
    },
}

TIME_BUDGET_MAP = {
    "Quick": {
        "time_multiplier": 0.7,
        "summary_style": "concise bullet points",
        "instruction": "Be extremely concise. Every sentence must carry weight. No filler."
    },
    "Focused": {
        "time_multiplier": 1.0,
        "summary_style": "structured paragraphs with clear headers",
        "instruction": "Balance thoroughness with clarity. Use headers to organize."
    },
    "DeepResearch": {
        "time_multiplier": 1.5,
        "summary_style": "comprehensive academic report with full detail",
        "instruction": "Be exhaustive. Include all relevant details, nuances, and cross-references."
    },
}

KNOWLEDGE_MAP = {
    "Beginner": {
        "vocabulary": "Use simple language. Define all technical terms on first use.",
        "context": "Provide background context for the field before diving into specifics.",
        "examples": "Include concrete examples and real-world analogies."
    },
    "Intermediate": {
        "vocabulary": "Use standard domain terminology. Define only specialized or novel terms.",
        "context": "Briefly contextualize within the broader field.",
        "examples": "Include examples for complex concepts only."
    },
    "Advanced": {
        "vocabulary": "Use full technical vocabulary without definitions unless novel.",
        "context": "Assume deep domain familiarity. Focus on novel contributions.",
        "examples": "Skip basic examples. Focus on edge cases and nuances."
    },
}

GOAL_MAP = {
    "Learn": {"focus": "understanding the landscape, building mental models", "extras": ["learning roadmap", "recommended next readings"]},
    "Teach": {"focus": "clear explanations, transferable frameworks, teaching angles", "extras": ["discussion questions", "key concepts to emphasize", "common misconceptions"]},
    "Publish": {"focus": "research gaps, novel angles, methodological improvements, positioning", "extras": ["potential research questions", "methodology suggestions", "positioning strategy"]},
    "Build": {"focus": "implementation details, architecture, code structure, practical steps", "extras": ["implementation checklist", "required dependencies", "code patterns"]},
    "Implement": {"focus": "implementation details, architecture, code structure, practical steps", "extras": ["implementation checklist", "required dependencies", "code patterns"]},
    "Apply": {"focus": "practical application, deployment considerations, integration steps", "extras": ["deployment checklist", "integration patterns", "performance considerations"]},
}

FORMAT_MAP = {
    "Bullet": {"structure": "Use bullet points and short phrases. Group by theme. Use ## headings for each theme.", "style": "## Theme\n- Point 1\n- Point 2\n  - Sub-point"},
    "Structured": {"structure": "Use clear section headers (##) with 2-4 sentence paragraphs per point, followed by - bullet points listing specific details. Every section must have both a paragraph AND bullet points.", "style": "## Section Header\nConcise paragraph.\n- Detail 1\n- Detail 2"},
    "Report": {"structure": "Full academic report format with numbered sections, introduction, body, conclusion. Use ## and ### headings with bullet points for findings.", "style": "## 1. Introduction\n### 1.1 Background\nParagraph.\n- Point 1\n..."},
}


class PromptBuilder:
    def _calculate_word_range(self, context: UserContext) -> str:
        d = DEPTH_MAP.get(context.depth, DEPTH_MAP["Understand"])
        t = TIME_BUDGET_MAP.get(context.time_budget, TIME_BUDGET_MAP["Focused"])
        return f"{int(d['base_min_words'] * t['time_multiplier'])}-{int(d['base_max_words'] * t['time_multiplier'])} words"

    def _is_deep_analysis(self, context: UserContext) -> bool:
        return (
            context.persona == "Researcher"
            and context.depth == "DeepDive"
            and context.time_budget == "DeepResearch"
            and context.goal == "Publish"
        )

    def build_prompt(self, context: UserContext, paper_count: int, has_full_text: bool, sections_to_generate: list = None) -> str:
        if sections_to_generate is None:
            sections_to_generate = ["summary", "insights"]

        persona = PERSONA_MAP.get(context.persona, PERSONA_MAP["Learner"])
        depth = DEPTH_MAP.get(context.depth, DEPTH_MAP["Understand"])
        time_cfg = TIME_BUDGET_MAP.get(context.time_budget, TIME_BUDGET_MAP["Focused"])
        knowledge = KNOWLEDGE_MAP.get(context.knowledge_level, KNOWLEDGE_MAP["Intermediate"])
        goal = GOAL_MAP.get(context.goal, GOAL_MAP["Learn"])
        fmt = FORMAT_MAP.get(context.output_format, FORMAT_MAP["Structured"])
        word_range = self._calculate_word_range(context)

        analysis_mode = "FULL-TEXT DEEP ANALYSIS" if (self._is_deep_analysis(context) and has_full_text) else "ABSTRACT-BASED ANALYSIS"

        required_sections = list(depth["sections"])
        should_gaps = "gaps" in sections_to_generate
        should_ideas = "ideas" in sections_to_generate

        if should_gaps and "Research Gaps" not in required_sections:
            required_sections.append("Research Gaps")
        if should_ideas and "Future Directions" not in required_sections:
            required_sections.append("Future Directions")

        json_instructions = self._build_json_instructions(sections_to_generate)
        restriction = ""
        if not should_gaps and not should_ideas:
            restriction = "\n=== IMPORTANT ===\nDO NOT generate research gaps or ideas. DO NOT include json_gaps or json_ideas blocks.\n"

        sections_str = "\n".join(f"- {s}" for s in required_sections)
        extras_str = "\n".join(f"- {e}" for e in goal["extras"])

        return (
            f'You are an expert research synthesizer on "{context.topic}".\n\n'
            f'=== ANALYSIS MODE: {analysis_mode} === PAPERS: {paper_count} ===\n\n'
            f'=== ROLE ===\nAudience: {context.persona}\nTone: {persona["tone"]}\nEmphasis: {persona["emphasis"]}\nAvoid: {persona["avoid"]}\n\n'
            f'=== DEPTH ===\nTarget: {word_range}\n{depth["instruction"]}\n{time_cfg["instruction"]}\n\n'
            f'=== VOCABULARY ===\n{knowledge["vocabulary"]}\n{knowledge["context"]}\n{knowledge["examples"]}\n\n'
            f'=== FORMAT ===\n{fmt["structure"]}\n\n'
            f'=== SECTIONS ===\n{sections_str}\n\n'
            f'=== GOAL ===\nFocus: {goal["focus"]}\nAlso include:\n{extras_str}\n'
            f'{restriction}\n=== INSTRUCTIONS ===\n'
            f'1. Synthesize across papers.\n'
            f'2. Identify agreements/contradictions.\n'
            f'3. Analyzing {paper_count} papers.\n'
            f'4. Style: {time_cfg["summary_style"]}.\n'
            f'5. Keep within {word_range}.\n'
            f'{json_instructions}\n\n=== PAPERS ===\n'
        )

    def _build_json_instructions(self, sections: list) -> str:
        lines = [
            "\n6. At the END provide these JSON blocks:",
            "",
            'A block named json_insights:\n```json_insights\n["insight 1"]\n```'
        ]
        if "gaps" in sections:
            lines.append('\nA block named json_gaps:\n```json_gaps\n["gap 1"]\n```')
        if "ideas" in sections:
            lines.append('\nA block named json_ideas:\n```json_ideas\n["idea 1"]\n```')
        if "gaps" not in sections:
            lines.append("\nDO NOT include json_gaps.")
        if "ideas" not in sections:
            lines.append("\nDO NOT include json_ideas.")
        return "\n".join(lines)

    def format_papers_for_prompt(self, papers: list, context: UserContext, has_full_text: bool) -> str:
        deep = self._is_deep_analysis(context) and has_full_text
        parts = []
        for i, p in enumerate(papers, 1):
            e = f"\n--- Paper {i}/{len(papers)} ---\nTitle: {p['title']}\n"
            if p.get("authors"):
                e += f"Authors: {', '.join(p['authors'][:3])}\n"
            if p.get("year"):
                e += f"Year: {p['year']}\n"
            if p.get("citation_count"):
                e += f"Citations: {p['citation_count']}\n"
            e += f"Source: {p['source']}\n"
            if deep and p.get("full_text"):
                e += f"\nFull Text:\n{p['full_text'][:8000]}\n"
            else:
                e += f"\nAbstract:\n{p.get('abstract', 'No abstract')}\n"
            parts.append(e)
        return "\n".join(parts)


def build_evidence_prompt(claims: list, paper_text: str) -> str:
    claims_str = "\n".join(f"- {c}" for c in claims if c)
    return f"""You are an evidence mapping assistant.
Given these claims from a summary:
{claims_str}
Find the EXACT sentence or data in the paper that supports each claim.
Return a JSON object with key "items" containing a list where each item has:
- claim: the original claim text
- evidence_text: the EXACT quote from the paper (copy word-for-word)
- section: which section (Abstract, Method, Results, etc.)
- page_number: estimated page number
- source_type: "text" or "table" or "figure" or "equation"
- confidence: 0.0 to 1.0

Paper text:
{paper_text[:8000]}
Return ONLY valid JSON."""


def build_visual_prompt(items_text: str, paper_text: str) -> str:
    return f"""Explain each figure, table, and equation in simple language.
Items found in the paper:
{items_text}
Context:
{paper_text[:4000]}
Return a JSON object with key "items" where each item has:
- label: "Figure 1" or "Table 2" or "Eq. (3)"
- item_type: "figure" or "table" or "equation"
- explanation: simple plain-English explanation of what it shows and why it matters
Return ONLY valid JSON."""


def build_implementation_prompt(paper_text: str, title: str = "") -> str:
    return f"""You are an implementation assistant for research papers.
Paper: {title}
Extract everything a developer needs to implement this. Return JSON with:
- model_intuition: plain explanation of what the model does and WHY it works
- architecture_steps: ordered list of steps to build it
- hyperparameters: dict of parameter names to values
- training_pipeline: ordered list of training steps
- code_hints: list of library names, function names, pseudocode snippets
- dependencies: list of required packages
- implementation_notes: any other useful notes
Paper text:
{paper_text[:8000]}
Return ONLY valid JSON."""