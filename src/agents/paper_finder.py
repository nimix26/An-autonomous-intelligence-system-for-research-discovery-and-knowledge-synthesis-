"""
Agent 1 — Paper Finder (Optimized)

Single source: Semantic Scholar API
  → Gets full metadata (title, abstract, DOI, ArXiv, PubMed, PDF link)
  → Then resolves PDF from multiple fallback sources
  → Downloads and extracts text with PyMuPDF

PDF Resolution Priority:
  1. Semantic Scholar openAccessPdf (direct link)
  2. ArXiv PDF (constructed from ArXiv ID)
  3. Unpaywall (lookup by DOI)
  4. PubMed Central (lookup by PubMed ID)
  5. DOI redirect (follow DOI → publisher → hope for PDF)
"""

import os
import asyncio
import hashlib
import logging
from typing import Optional
from dataclasses import dataclass, field, asdict

import httpx
import fitz  # PyMuPDF
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
PMC_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0"

PDF_DIR = os.getenv("PDF_DOWNLOAD_DIR", "./downloaded_pdfs")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "")

USER_AGENT = "Mozilla/5.0 (compatible; AuroraResearchBot/2.0; mailto:research@aurora.ai)"


@dataclass
class Paper:
    title: str = ""
    abstract: str = ""
    full_text: str = ""
    source: str = ""
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    corpus_id: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_source: str = ""  # Where we got the PDF from
    semantic_scholar_url: Optional[str] = None
    year: Optional[int] = None
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None
    venue: str = ""
    journal: str = ""
    publication_date: Optional[str] = None
    fields_of_study: list[str] = field(default_factory=list)
    is_open_access: bool = False
    tldr: str = ""
    authors: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class PaperFinder:
    """
    Agent 1: Finds papers via Semantic Scholar, then resolves & downloads PDFs.

    Flow:
      1. Search Semantic Scholar → get metadata + IDs
      2. For each paper, resolve PDF URL (SS → ArXiv → Unpaywall → PMC)
      3. Download PDF → extract text with PyMuPDF
    """

    def __init__(self):
        os.makedirs(PDF_DIR, exist_ok=True)
        self.ss_headers = {"User-Agent": USER_AGENT}
        if SEMANTIC_SCHOLAR_API_KEY:
            self.ss_headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
            logger.info("[PaperFinder] Semantic Scholar API key: SET")
        else:
            logger.info("[PaperFinder] Semantic Scholar API key: NOT SET (public access)")

    # ═══════════════════════════════════════════════════════
    #  MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════

    async def find_papers(self, topic: str, max_results: int = 10) -> list[Paper]:
        """
        Main pipeline:
          1. Search Semantic Scholar
          2. Resolve PDF URLs for each paper
          3. Download & extract text
        """
        logger.info(f"[PaperFinder] ═══ Searching: '{topic}' (max {max_results}) ═══")

        # ── STEP 1: Search Semantic Scholar (ONLY source) ──
        papers = await self._search_semantic_scholar(topic, max_results)

        if not papers:
            logger.warning("[PaperFinder] No papers found from Semantic Scholar")
            return []

        logger.info(f"[PaperFinder] Got {len(papers)} papers from Semantic Scholar")

        # ── STEP 2: Resolve PDF URLs for papers that don't have one ──
        await self._resolve_all_pdf_urls(papers)

        # ── STEP 3: Download PDFs and extract text ──
        await self._download_and_extract_all(papers)

        # ── Final summary ──
        self._log_final_summary(papers)

        return papers

    # ═══════════════════════════════════════════════════════
    #  STEP 1: SEMANTIC SCHOLAR SEARCH
    # ═══════════════════════════════════════════════════════

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=15))
    async def _search_semantic_scholar(self, topic: str, max_results: int) -> list[Paper]:
        """Search Semantic Scholar — our ONLY search source."""
        papers = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            params = {
                "query": topic,
                "limit": min(max_results, 20),
                "fields": (
                    "title,abstract,year,authors,citationCount,referenceCount,"
                    "externalIds,openAccessPdf,url,venue,journal,"
                    "publicationDate,fieldsOfStudy,isOpenAccess,tldr"
                ),
            }

            logger.info(f"[SemanticScholar] Requesting {params['limit']} papers...")

            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
                params=params,
                headers=self.ss_headers,
            )

            # ── Handle rate limiting ──
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "10")
                wait_time = int(retry_after) if retry_after.isdigit() else 10
                logger.warning(f"[SemanticScholar] Rate limited — waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                raise Exception("Rate limited — will retry")

            if resp.status_code != 200:
                logger.error(f"[SemanticScholar] Error {resp.status_code}: {resp.text[:300]}")
                return []

            data = resp.json()
            items = data.get("data", [])
            total = data.get("total", 0)

            logger.info(f"[SemanticScholar] Found {total} total, returned {len(items)}")

            # ── Parse each paper ──
            for item in items:
                paper = self._parse_semantic_scholar_item(item)
                if paper:
                    papers.append(paper)

        logger.info(f"[SemanticScholar] Parsed {len(papers)} valid papers")
        return papers

    def _parse_semantic_scholar_item(self, item: dict) -> Optional[Paper]:
        """Parse a single Semantic Scholar result into a Paper object."""
        title = item.get("title", "")
        if not title or not title.strip():
            return None

        # ── External IDs (the identity card) ──
        ext_ids = item.get("externalIds") or {}
        doi = ext_ids.get("DOI")
        arxiv_id = ext_ids.get("ArXiv")
        pubmed_id = ext_ids.get("PubMed")
        corpus_id = str(ext_ids.get("CorpusId", "")) if ext_ids.get("CorpusId") else None

        # ── PDF URL from Semantic Scholar ──
        pdf_url = None
        pdf_source = ""
        oa_pdf = item.get("openAccessPdf")
        if oa_pdf and isinstance(oa_pdf, dict) and oa_pdf.get("url"):
            pdf_url = oa_pdf["url"]
            pdf_source = "semantic_scholar_oa"

        # ── Venue / Journal ──
        venue = item.get("venue", "") or ""
        journal_info = item.get("journal") or {}
        journal_name = ""
        if isinstance(journal_info, dict):
            journal_name = journal_info.get("name", "") or ""

        # ── TLDR ──
        tldr = ""
        tldr_obj = item.get("tldr")
        if tldr_obj and isinstance(tldr_obj, dict):
            tldr = tldr_obj.get("text", "") or ""

        # ── Authors ──
        authors = [
            a.get("name", "")
            for a in (item.get("authors") or [])[:5]
            if a.get("name")
        ]

        paper = Paper(
            title=title.strip(),
            abstract=(item.get("abstract", "") or "").strip(),
            source="semantic_scholar",
            doi=doi,
            arxiv_id=arxiv_id,
            pubmed_id=pubmed_id,
            corpus_id=corpus_id,
            pdf_url=pdf_url,
            pdf_source=pdf_source,
            semantic_scholar_url=item.get("url", ""),
            year=item.get("year"),
            citation_count=item.get("citationCount", 0),
            reference_count=item.get("referenceCount", 0),
            venue=venue,
            journal=journal_name or venue,
            publication_date=item.get("publicationDate"),
            fields_of_study=item.get("fieldsOfStudy") or [],
            is_open_access=bool(item.get("isOpenAccess", False)),
            tldr=tldr,
            authors=authors,
        )

        # Log what IDs we got
        ids = []
        if doi:
            ids.append(f"DOI")
        if arxiv_id:
            ids.append(f"ArXiv")
        if pubmed_id:
            ids.append(f"PubMed")
        logger.info(
            f"  [Paper] {title[:55]}... | "
            f"IDs: [{', '.join(ids) or 'none'}] | "
            f"PDF: {'YES' if pdf_url else 'NO'} | "
            f"OA: {paper.is_open_access}"
        )

        return paper

    # ═══════════════════════════════════════════════════════
    #  STEP 2: RESOLVE PDF URLs
    #  For papers without a PDF, try multiple sources
    # ═══════════════════════════════════════════════════════

    async def _resolve_all_pdf_urls(self, papers: list[Paper]):
        """Resolve PDF URLs for all papers that don't have one yet."""
        papers_needing_pdf = [p for p in papers if not p.pdf_url]
        papers_with_pdf = len(papers) - len(papers_needing_pdf)

        logger.info(
            f"[PaperFinder] PDF status: "
            f"{papers_with_pdf} have PDF, "
            f"{len(papers_needing_pdf)} need resolution"
        )

        if not papers_needing_pdf:
            return

        sem = asyncio.Semaphore(3)

        async def _resolve_one(paper: Paper):
            async with sem:
                await self._resolve_pdf_url(paper)

        await asyncio.gather(
            *[_resolve_one(p) for p in papers_needing_pdf],
            return_exceptions=True,
        )

        # Count how many we resolved
        resolved = sum(1 for p in papers_needing_pdf if p.pdf_url)
        logger.info(f"[PaperFinder] Resolved {resolved}/{len(papers_needing_pdf)} additional PDF URLs")

    async def _resolve_pdf_url(self, paper: Paper):
        """
        Try to find a PDF URL using the paper's IDs.
        Priority order:
          1. ArXiv (if paper has ArXiv ID — always free)
          2. Unpaywall (if paper has DOI — finds open access versions)
          3. PubMed Central (if paper has PubMed ID)
        """

        # ── Priority 1: ArXiv ──
        if paper.arxiv_id:
            arxiv_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
            if await self._verify_pdf_url(arxiv_url):
                paper.pdf_url = arxiv_url
                paper.pdf_source = "arxiv"
                logger.info(f"  [Resolve] ArXiv PDF found for: {paper.title[:40]}...")
                return

        # ── Priority 2: Unpaywall ──
        if paper.doi and UNPAYWALL_EMAIL:
            unpaywall_url = await self._try_unpaywall(paper.doi)
            if unpaywall_url:
                paper.pdf_url = unpaywall_url
                paper.pdf_source = "unpaywall"
                logger.info(f"  [Resolve] Unpaywall PDF found for: {paper.title[:40]}...")
                return

        # ── Priority 3: PubMed Central ──
        if paper.pubmed_id:
            pmc_url = await self._try_pubmed_central(paper.pubmed_id)
            if pmc_url:
                paper.pdf_url = pmc_url
                paper.pdf_source = "pmc"
                logger.info(f"  [Resolve] PMC PDF found for: {paper.title[:40]}...")
                return

        logger.debug(f"  [Resolve] No PDF found for: {paper.title[:40]}...")

    async def _verify_pdf_url(self, url: str) -> bool:
        """Quick HEAD request to check if a URL actually serves a PDF."""
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.head(url, headers={"User-Agent": USER_AGENT})
                content_type = resp.headers.get("content-type", "").lower()
                return (
                    resp.status_code == 200
                    and ("pdf" in content_type or "octet-stream" in content_type)
                )
        except Exception:
            return False

    async def _try_unpaywall(self, doi: str) -> Optional[str]:
        """Look up DOI on Unpaywall to find open access PDF."""
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(
                    f"{UNPAYWALL_BASE}/{doi}",
                    params={"email": UNPAYWALL_EMAIL},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    best_oa = data.get("best_oa_location")
                    if best_oa:
                        pdf_url = best_oa.get("url_for_pdf")
                        if pdf_url:
                            return pdf_url
                        # Some entries have landing page but no direct PDF
                        landing = best_oa.get("url_for_landing_page")
                        if landing and landing.endswith(".pdf"):
                            return landing
        except Exception as e:
            logger.debug(f"  [Unpaywall] Failed for DOI {doi}: {e}")
        return None

    async def _try_pubmed_central(self, pubmed_id: str) -> Optional[str]:
        """Convert PubMed ID to PMC ID, then construct PDF URL."""
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # First: convert PubMed ID to PMC ID
                resp = await client.get(
                    PMC_BASE,
                    params={
                        "ids": pubmed_id,
                        "format": "json",
                        "tool": "aurora_research",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    records = data.get("records", [])
                    if records:
                        pmcid = records[0].get("pmcid")
                        if pmcid:
                            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                            return pdf_url
        except Exception as e:
            logger.debug(f"  [PMC] Failed for PubMed {pubmed_id}: {e}")
        return None

    # ═══════════════════════════════════════════════════════
    #  STEP 3: DOWNLOAD & EXTRACT TEXT
    # ═══════════════════════════════════════════════════════

    async def _download_and_extract_all(self, papers: list[Paper]):
        """Download PDFs and extract text concurrently."""
        papers_with_pdf = [p for p in papers if p.pdf_url]

        logger.info(
            f"[PaperFinder] Downloading {len(papers_with_pdf)}/{len(papers)} papers with PDF URLs"
        )

        if not papers_with_pdf:
            return

        sem = asyncio.Semaphore(3)

        async def _process(paper: Paper):
            async with sem:
                await self._download_and_extract(paper)

        await asyncio.gather(
            *[_process(p) for p in papers_with_pdf],
            return_exceptions=True,
        )

        extracted = sum(1 for p in papers if len(p.full_text.strip()) > 500)
        logger.info(f"[PaperFinder] Extracted text from {extracted}/{len(papers_with_pdf)} PDFs")

    async def _download_and_extract(self, paper: Paper):
        """Download a single PDF and extract its text."""
        if not paper.pdf_url:
            return

        try:
            # Use URL hash as filename for caching
            filename = hashlib.md5(paper.pdf_url.encode()).hexdigest() + ".pdf"
            filepath = os.path.join(PDF_DIR, filename)

            # Use cached version if exists
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                paper.full_text = self._extract_text(filepath)
                if paper.full_text.strip():
                    logger.info(
                        f"  [Cache] {paper.title[:40]}... | "
                        f"{len(paper.full_text)} chars"
                    )
                    return

            # Download
            async with httpx.AsyncClient(
                timeout=60.0,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                resp = await client.get(paper.pdf_url)

                if resp.status_code != 200:
                    logger.debug(
                        f"  [Download] HTTP {resp.status_code} for {paper.title[:40]}..."
                    )
                    return

                content = resp.content

                # Verify it's actually a PDF
                if len(content) < 1000:
                    logger.debug(f"  [Download] Too small ({len(content)} bytes): {paper.title[:40]}...")
                    return

                content_type = resp.headers.get("content-type", "").lower()
                is_pdf = (
                    content[:5] == b"%PDF-"
                    or "pdf" in content_type
                    or "octet-stream" in content_type
                )

                if not is_pdf:
                    logger.debug(
                        f"  [Download] Not a PDF (type={content_type}): {paper.title[:40]}..."
                    )
                    return

                # Save to disk
                with open(filepath, "wb") as f:
                    f.write(content)

                # Extract text
                paper.full_text = self._extract_text(filepath)

                if paper.full_text.strip():
                    logger.info(
                        f"  [Downloaded] {paper.title[:40]}... | "
                        f"from={paper.pdf_source} | "
                        f"{len(paper.full_text)} chars"
                    )
                else:
                    logger.debug(
                        f"  [Download] PDF downloaded but no text extracted: {paper.title[:40]}..."
                    )

        except Exception as e:
            logger.debug(f"  [Download] Failed for '{paper.title[:40]}...': {e}")

    def _extract_text(self, pdf_path: str) -> str:
        """Extract text from PDF using PyMuPDF."""
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            max_pages = min(len(doc), 30)

            for page_num in range(max_pages):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

            doc.close()
            return "\n".join(text_parts)
        except Exception as e:
            logger.debug(f"  [PyMuPDF] Failed: {e}")
            return ""

    # ═══════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════

    def _log_final_summary(self, papers: list[Paper]):
        """Print final summary to logs."""
        total = len(papers)
        with_text = sum(1 for p in papers if len(p.full_text.strip()) > 500)
        with_abstract = sum(1 for p in papers if p.abstract.strip())
        with_pdf = sum(1 for p in papers if p.pdf_url)

        logger.info(f"[PaperFinder] ═══ FINAL SUMMARY ═══")
        logger.info(f"  Total papers:     {total}")
        logger.info(f"  With PDF URL:     {with_pdf}")
        logger.info(f"  With full text:   {with_text}")
        logger.info(f"  With abstract:    {with_abstract}")
        logger.info(f"  Abstract only:    {with_abstract - with_text}")

        # Per-paper detail
        for i, p in enumerate(papers):
            text_status = "FULL TEXT" if len(p.full_text.strip()) > 500 else (
                "PARTIAL" if p.full_text.strip() else "ABSTRACT ONLY"
            )

            ids = []
            if p.doi:
                ids.append("DOI")
            if p.arxiv_id:
                ids.append("ArXiv")
            if p.pubmed_id:
                ids.append("PubMed")

            logger.info(
                f"  [{i+1}] {p.title[:50]}...\n"
                f"       Year={p.year} | Cited={p.citation_count} | "
                f"IDs=[{','.join(ids)}]\n"
                f"       PDF={p.pdf_source or 'NONE'} | Text={text_status}"
            )

        # Print to terminal too
        print("\n")
        print("=" * 80)
        print(f"  PAPERS COLLECTED ({total} total)")
        print("=" * 80)
        for i, p in enumerate(papers):
            text_len = len(p.full_text.strip())
            text_status = f"FULL TEXT ({text_len} chars)" if text_len > 500 else (
                f"PARTIAL ({text_len} chars)" if text_len > 0 else "ABSTRACT ONLY"
            )
            print(
                f"  [{i+1}] {p.title[:60]}\n"
                f"       Year: {p.year} | Citations: {p.citation_count} | "
                f"Source: {p.pdf_source or 'no-pdf'}\n"
                f"       DOI: {p.doi or '-'} | ArXiv: {p.arxiv_id or '-'} | "
                f"PubMed: {p.pubmed_id or '-'}\n"
                f"       Content: {text_status}"
            )
        print("=" * 80)
        print("\n")