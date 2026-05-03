"""Phase 1: LLM-based paper discovery and metadata verification."""

import logging
import time

from models.paper import Paper
from core.llm_service import LLMService
from core.database_searcher import DatabaseSearcher
from core.config import Config

logger = logging.getLogger(__name__)


class PaperDiscovery:
    def __init__(self, llm_service: LLMService, db_searcher: DatabaseSearcher):
        self.llm = llm_service
        self.db = db_searcher

    async def discover(self, topic: str, context: str = "") -> list[Paper]:
        logger.info(f"[Phase1] LLM discovery for topic: {topic}")
        suggestions = await self.llm.suggest_paper_names(topic, context)
        logger.info(f"[Phase1] LLM suggestions: {len(suggestions)}")

        verified: list[Paper] = []
        for idx, title in enumerate(suggestions):
            logger.info(f"[Phase1] Verifying {idx+1}/{len(suggestions)}: {title[:80]}")
            paper = self.db.search_by_title(title)
            if paper:
                paper.discovery_phase = "phase1_llm"
                if paper.source == "":
                    paper.source = "llm_suggested"
                verified.append(paper)
            else:
                logger.warning(f"[Phase1] Could not verify: {title[:120]}")
                verified.append(Paper(
                    title=title,
                    source="llm_unverified",
                    discovery_phase="phase1_llm",
                ))
            time.sleep(Config.API_DELAY_SECONDS)

        logger.info(f"[Phase1] Verified papers: {len(verified)}")
        return verified