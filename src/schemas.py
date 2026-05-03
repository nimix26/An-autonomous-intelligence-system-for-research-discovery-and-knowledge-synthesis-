"""
schemas.py — Updated with detailed summary + visual fields.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class PaperInput(BaseModel):
    title: Optional[str] = ""
    abstract: Optional[str] = ""
    authors: Optional[List[str]] = []
    year: Optional[int] = 0
    citation_count: Optional[int] = 0
    venue: Optional[str] = ""
    doi: Optional[str] = ""
    arxiv_id: Optional[str] = ""
    pdf_url: Optional[str] = ""


class DiscoverRequest(BaseModel):
    topic: str
    persona: Optional[str] = "Researcher"
    field_of_study: Optional[str] = ""
    max_results: Optional[int] = 20
    time_filter: Optional[str] = "relevant"


class SummarizeRequest(BaseModel):
    topic: Optional[str] = ""
    persona: Optional[str] = "Researcher"
    field_of_study: Optional[str] = ""
    paper: Optional[PaperInput] = None


class AnalyzeRequest(BaseModel):
    topic: Optional[str] = ""
    persona: Optional[str] = "Researcher"
    field_of_study: Optional[str] = ""
    max_results: Optional[int] = 10


class CompareRequest(BaseModel):
    topic: Optional[str] = ""
    persona: Optional[str] = "Researcher"
    field_of_study: Optional[str] = ""
    papers: Optional[List[Dict[str, Any]]] = []


class ImplementRequest(BaseModel):
    topic: Optional[str] = ""
    persona: Optional[str] = "Learner"
    field_of_study: Optional[str] = ""
    papers: Optional[List[Dict[str, Any]]] = []


class PaperResult(BaseModel):
    paper_id: Optional[str] = ""
    title: Optional[str] = ""
    authors: Optional[List[str]] = []
    abstract: Optional[str] = ""
    year: Optional[int] = 0
    citation_count: Optional[int] = 0
    venue: Optional[str] = ""
    doi: Optional[str] = ""
    arxiv_id: Optional[str] = ""
    pdf_url: Optional[str] = ""
    pdf_hash: Optional[str] = ""
    relevance_score: Optional[float] = 0.0
    source: Optional[str] = ""

    # ── Detailed text summary fields ──────────────────────────────
    summary: Optional[str] = ""
    key_insights: Optional[List[str]] = []
    methodology: Optional[str] = ""
    results: Optional[str] = ""
    limitations: Optional[str] = ""
    research_context: Optional[Dict[str, Any]] = {}
    practical_takeaways: Optional[List[str]] = []

    # ── Detailed visual fields ──────────���─────────────────────────
    visual_groups: Optional[List[Dict[str, Any]]] = []
    detailed_figures: Optional[List[Dict[str, Any]]] = []
    detailed_graphs: Optional[List[Dict[str, Any]]] = []
    detailed_equations: Optional[List[Dict[str, Any]]] = []

    # ── Processing metadata ───────────────────────────────────────
    chunk_summaries: Optional[List[Dict[str, Any]]] = []
    total_chunks: Optional[int] = 0
    pages_processed: Optional[int] = 0


class DiscoverResponse(BaseModel):
    topic: str
    persona: Optional[str] = "Researcher"
    field_of_study: Optional[str] = ""
    papers: Optional[List[PaperResult]] = []
    keywords: Optional[List[str]] = []
    total_found: Optional[int] = 0


class AnalyzeResponse(BaseModel):
    topic: Optional[str] = ""
    persona: Optional[str] = "Researcher"
    field_of_study: Optional[str] = ""
    papers: Optional[List[PaperResult]] = []
    synthesis: Optional[str] = ""
    keywords: Optional[List[str]] = []
    total_analyzed: Optional[int] = 0

    # ── Single-paper analysis fields (returned by summarize_single_paper) ──
    title: Optional[str] = ""
    authors: Optional[List[str]] = []
    year: Optional[int] = 0
    venue: Optional[str] = ""
    doi: Optional[str] = ""
    arxiv_id: Optional[str] = ""
    pdf_url: Optional[str] = ""
    pdf_hash: Optional[str] = ""

    # ── Detailed text summary fields ──
    summary: Optional[str] = ""
    key_insights: Optional[List[str]] = []
    methodology: Optional[str] = ""
    results: Optional[str] = ""
    limitations: Optional[str] = ""

    # ── Visual fields ──
    visual_groups: Optional[List[Dict[str, Any]]] = []

    # ── Processing metadata ──
    chunk_summaries: Optional[List[Dict[str, Any]]] = []
    total_chunks: Optional[int] = 0
    pages_processed: Optional[int] = 0

    # ── Multi-paper / pipeline fields ──
    comparison: Optional[str] = ""
    compared_analyses: Optional[List[Dict[str, Any]]] = []
    implementation: Optional[Dict[str, Any]] = {}
    message: Optional[str] = ""
    mode: Optional[str] = ""

    # ── Compare-specific structured fields ──
    papers_used: Optional[List[Dict[str, Any]]] = []
    paper_contributions: Optional[List[Dict[str, Any]]] = []
    research_gaps: Optional[str] = ""