"""Central configuration."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # LLM providers (all env-driven)
    TEXT_API_KEY = os.getenv("TEXT_API_KEY", "")
    TEXT_BASE_URL = os.getenv("TEXT_BASE_URL", "")
    TEXT_MODEL = os.getenv("TEXT_MODEL", "")

    DISCOVERY_API_KEY = os.getenv("DISCOVERY_API_KEY", "")
    DISCOVERY_BASE_URL = os.getenv("DISCOVERY_BASE_URL", "")
    DISCOVERY_MODEL = os.getenv("DISCOVERY_MODEL", "")

    JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "")
    JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "")
    JUDGE_MODEL = os.getenv("JUDGE_MODEL", "")

    CODE_API_KEY = os.getenv("CODE_API_KEY", "")
    CODE_BASE_URL = os.getenv("CODE_BASE_URL", "")
    CODE_MODEL = os.getenv("CODE_MODEL", "")

    IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
    IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "")
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "")

    GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")
    GRAPH_BASE_URL = os.getenv("GRAPH_BASE_URL", "")
    GRAPH_MODEL = os.getenv("GRAPH_MODEL", "")

    EQUATION_API_KEY = os.getenv("EQUATION_API_KEY", "")
    EQUATION_BASE_URL = os.getenv("EQUATION_BASE_URL", "")
    EQUATION_MODEL = os.getenv("EQUATION_MODEL", "")

    # External search APIs
    SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "")
    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
    CORE_API_KEY = os.getenv("CORE_API_KEY", "")

    # Overridable base URLs for non-LLM APIs
    SEMANTIC_SCHOLAR_BASE_URL = os.getenv("SEMANTIC_SCHOLAR_BASE_URL", "https://api.semanticscholar.org/graph/v1")
    UNPAYWALL_BASE_URL = os.getenv("UNPAYWALL_BASE_URL", "https://api.unpaywall.org/v2")
    PMC_BASE_URL = os.getenv("PMC_BASE_URL", "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0")

    # App runtime
    APP_NAME = os.getenv("APP_NAME", "CogniView.AI API")
    APP_VERSION = os.getenv("APP_VERSION", "9.0.0")
    SERVICE_NAME = os.getenv("SERVICE_NAME", "CogniView.AI")
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; CogniViewBot/1.0)")

    # Pipeline knobs
    MAX_LLM_SUGGESTIONS = int(os.getenv("MAX_LLM_SUGGESTIONS", "20"))
    MAX_DB_RESULTS = int(os.getenv("MAX_DB_RESULTS", "50"))
    MAX_KEYWORDS = int(os.getenv("MAX_KEYWORDS", "10"))
    TOP_N_PAPERS = int(os.getenv("TOP_N_PAPERS", "10"))
    MAX_DATABASE_RESULTS_PER_KEYWORD = int(os.getenv("MAX_DATABASE_RESULTS_PER_KEYWORD", "15"))
    API_DELAY_SECONDS = float(os.getenv("API_DELAY", "1.0"))

    # Persona top-N (total papers shown: guaranteed + ranked)
    TOP_N_STUDENT = int(os.getenv("TOP_N_STUDENT", "10"))
    TOP_N_EDUCATOR = int(os.getenv("TOP_N_EDUCATOR", "15"))
    TOP_N_RESEARCHER = int(os.getenv("TOP_N_RESEARCHER", "20"))

    # Number of LLM seed papers guaranteed in output
    GUARANTEED_COUNT = int(os.getenv("GUARANTEED_COUNT", "3"))

    # Hybrid pipeline knobs (legacy)
    MAX_LLM_SEED_PAPERS = int(os.getenv("MAX_LLM_SEED_PAPERS", "3"))
    HEURISTIC_POOL_SIZE = int(os.getenv("HEURISTIC_POOL_SIZE", "120"))
    SPECTER_POOL_SIZE = int(os.getenv("SPECTER_POOL_SIZE", "30"))
    PAPERS_PER_KEYWORD = int(os.getenv("PAPERS_PER_KEYWORD", "40"))

    # Scoring weights (legacy — kept for backward compat with DiscoveryPipeline)
    WEIGHT_CITATIONS = float(os.getenv("WEIGHT_CITATIONS", "0.50"))
    WEIGHT_VENUE = float(os.getenv("WEIGHT_VENUE", "0.30"))
    WEIGHT_RECENCY = float(os.getenv("WEIGHT_RECENCY", "0.20"))

    # Storage
    DATA_DIR = os.getenv("DATA_DIR", "data")
    PDF_DIR = os.getenv("PDF_DOWNLOAD_DIR", "downloaded_pdfs")
    RAW_PAPERS_DIR = os.path.join(DATA_DIR, "raw_papers")
    FINAL_DIR = os.path.join(DATA_DIR, "final")

    # ────────────────────────────────────────────────────────────────
    # Universal Discovery Pipeline v2 (NEW)
    # ────────────────────────────────────────────────────────────────

    # Stage 1
    STAGE1_MIN_SEEDS = int(os.getenv("STAGE1_MIN_SEEDS", "2"))
    STAGE1_MAX_SEEDS = int(os.getenv("STAGE1_MAX_SEEDS", "6"))

    # Stage 2A
    STAGE2A_PAPERS_PER_KEYWORD = int(os.getenv("STAGE2A_PAPERS_PER_KEYWORD", "25"))
    STAGE2A_MAX_SEARCH_TERMS   = int(os.getenv("STAGE2A_MAX_SEARCH_TERMS",   "20"))
    STAGE2A_CONCEPT_COUNT      = int(os.getenv("STAGE2A_CONCEPT_COUNT",      "5"))

    # Stage 2B
    STAGE2B_MAX_REFS_PER_SEED  = int(os.getenv("STAGE2B_MAX_REFS_PER_SEED",  "30"))
    STAGE2B_MAX_CITES_PER_SEED = int(os.getenv("STAGE2B_MAX_CITES_PER_SEED", "80"))
    STAGE2B_MAX_CO_CITATIONS   = int(os.getenv("STAGE2B_MAX_CO_CITATIONS",   "20"))
    STAGE2B_API_TIMEOUT        = int(os.getenv("STAGE2B_API_TIMEOUT",        "25"))

    # Stage 2C — Semantic Retrieval (gap-fill addition)
    STAGE2C_TOP_K       = int(os.getenv("STAGE2C_TOP_K",       "200"))
    STAGE2C_API_TIMEOUT = int(os.getenv("STAGE2C_API_TIMEOUT", "25"))

    # Stage 3
    STAGE3_MIN_RESULTS        = int(os.getenv("STAGE3_MIN_RESULTS",        "30"))
    STAGE3_RECENT_YEAR_CUTOFF = int(os.getenv("STAGE3_RECENT_YEAR_CUTOFF", "2"))
    STAGE3_MAX_RELAX_ATTEMPTS = int(os.getenv("STAGE3_MAX_RELAX_ATTEMPTS", "3"))
    LATEST_PAPER_YEAR_WINDOW  = int(os.getenv("LATEST_PAPER_YEAR_WINDOW",  "2"))

    # Stage 4
    STAGE4_TOP_FOR_MMR = int(os.getenv("STAGE4_TOP_FOR_MMR", "100"))

    # Stage 5
    STAGE5_MMR_POOL_SIZE = int(os.getenv("STAGE5_MMR_POOL_SIZE", "30"))

    # Stage 6
    STAGE6_FALLBACK_ON_FAIL = os.getenv("STAGE6_FALLBACK_ON_FAIL", "true").lower() == "true"

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.DATA_DIR, cls.PDF_DIR, cls.RAW_PAPERS_DIR, cls.FINAL_DIR]:
            os.makedirs(d, exist_ok=True)

    @classmethod
    def get_top_n(cls, persona: str) -> int:
        mapping = {
            "Student":    cls.TOP_N_STUDENT,
            "Learner":    cls.TOP_N_STUDENT,
            "Educator":   cls.TOP_N_EDUCATOR,
            "Professor":  cls.TOP_N_EDUCATOR,
            "Researcher": cls.TOP_N_RESEARCHER,
        }
        return mapping.get(persona, cls.TOP_N_RESEARCHER)


def normalize_context(request) -> dict:
    if hasattr(request, "model_dump"):
        return request.model_dump()
    elif hasattr(request, "dict"):
        return request.dict()
    elif isinstance(request, dict):
        return request
    return {}
