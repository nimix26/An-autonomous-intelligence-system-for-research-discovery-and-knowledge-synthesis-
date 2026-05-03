import logging
from pipelines.summarize import SummarizePipeline
from core.llm_service import LLMService
from prompts import build_implementation_prompt
from schemas import UserContext

log = logging.getLogger(__name__)


class ImplementPipeline:
    def __init__(self):
        self.summarize = SummarizePipeline()
        self.llm = LLMService()

    async def run(self, context: UserContext, paper: dict) -> dict:
        sections = ["summary", "insights"]
        visible_tabs = ["summary", "insights", "evidence", "visuals", "datasets", "implementation", "papers"]
        result = await self.summarize.run(context, paper, sections, visible_tabs, use_chunked=True)

        text = paper.get("full_text", "") or paper.get("abstract", "")
        title = paper.get("title", "")
        impl_data = await self.llm.call_text_json(build_implementation_prompt(text, title))

        result["implementation"] = {
            "model_intuition": impl_data.get("model_intuition", ""),
            "architecture_steps": impl_data.get("architecture_steps", []),
            "hyperparameters": impl_data.get("hyperparameters", {}),
            "training_pipeline": impl_data.get("training_pipeline", []),
            "code_hints": impl_data.get("code_hints", []),
            "dependencies": impl_data.get("dependencies", []),
            "implementation_notes": impl_data.get("implementation_notes", ""),
        }
        result["analysis_mode"] = "implementation_" + result.get("analysis_mode", "")
        return result