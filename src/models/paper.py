"""
models/paper.py — Paper dataclass with None-safe defaults.
"""

from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class Paper:
    paper_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    citation_count: int = 0
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    publication_date: str = ""
    references: List[str] = field(default_factory=list)
    cited_by: List[str] = field(default_factory=list)
    pdf_url: str = ""
    source: str = ""

    full_text: str = ""
    pdf_path: str = ""
    discovery_phase: str = ""
    relevance_keywords: List[str] = field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    methodology: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return sanitize_dict(d)

    @classmethod
    def from_dict(cls, d: dict) -> "Paper":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known_fields}
        return cls(**filtered)


def sanitize_dict(d: dict) -> dict:
    result = {}
    for k, v in d.items():
        if v is None:
            if k in ("year", "citation_count", "overall_score"):
                result[k] = 0
            elif k in ("authors", "references", "cited_by", "relevance_keywords", "key_findings"):
                result[k] = []
            else:
                result[k] = ""
        else:
            result[k] = v
    return result