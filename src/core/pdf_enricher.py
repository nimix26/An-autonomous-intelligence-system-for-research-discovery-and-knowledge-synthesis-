import os
import asyncio
import hashlib
import logging
from typing import Optional

import httpx
import fitz

from models.paper import Paper
from core.config import Config
from core.pdf_downloader import _looks_like_html

logger = logging.getLogger(__name__)

PDF_MAGIC = b'%PDF-'
MIN_PDF_SIZE = 10_240

PDF_DIR = Config.PDF_DIR
UNPAYWALL_EMAIL = Config.UNPAYWALL_EMAIL
UNPAYWALL_BASE = Config.UNPAYWALL_BASE_URL
USER_AGENT = Config.USER_AGENT


class PDFEnricher:
    def __init__(self):
        os.makedirs(PDF_DIR, exist_ok=True)

    async def enrich_top_papers_with_fulltext(self, papers: list[Paper]) -> list[Paper]:
        sem = asyncio.Semaphore(3)

        async def _one(p: Paper):
            async with sem:
                await self._resolve_pdf_if_missing(p)
                await self._download_and_extract(p)

        await asyncio.gather(*[_one(p) for p in papers], return_exceptions=True)
        return papers

    async def _resolve_pdf_if_missing(self, paper: Paper):
        if paper.pdf_url:
            return

        if paper.arxiv_id:
            candidate = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
            if await self._verify_pdf_url(candidate):
                paper.pdf_url = candidate
                return

        if paper.doi and UNPAYWALL_EMAIL:
            up = await self._try_unpaywall(paper.doi)
            if up:
                paper.pdf_url = up

    async def _verify_pdf_url(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
                r = await c.head(url, headers={"User-Agent": USER_AGENT})
                ct = r.headers.get("content-type", "").lower()
                return r.status_code == 200 and ("pdf" in ct or "octet-stream" in ct)
        except Exception:
            return False

    async def _try_unpaywall(self, doi: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
                r = await c.get(f"{UNPAYWALL_BASE}/{doi}", params={"email": UNPAYWALL_EMAIL})
                if r.status_code == 200:
                    best = r.json().get("best_oa_location")
                    if best:
                        return best.get("url_for_pdf")
        except Exception:
            pass
        return None

    async def _download_and_extract(self, paper: Paper):
        if not paper.pdf_url:
            return
        try:
            filename = hashlib.md5(paper.pdf_url.encode()).hexdigest() + ".pdf"
            filepath = os.path.join(PDF_DIR, filename)

            if os.path.exists(filepath) and os.path.getsize(filepath) > MIN_PDF_SIZE:
                # Validate cached file is actually a PDF
                with open(filepath, "rb") as f:
                    header = f.read(64)
                if header.startswith(PDF_MAGIC) and not _looks_like_html(header):
                    paper.pdf_path = filepath
                    paper.full_text = self._extract_text(filepath)
                    return
                else:
                    # Cached file is not a real PDF — delete and re-download
                    logger.info(f"[PDFEnricher] Removing invalid cached file: {filepath}")
                    os.remove(filepath)

            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as c:
                resp = await c.get(paper.pdf_url)
                if resp.status_code != 200 or len(resp.content) < MIN_PDF_SIZE:
                    return
                # Primary check: PDF magic bytes
                is_pdf = resp.content[:5] == PDF_MAGIC
                if not is_pdf:
                    # Check if it's HTML disguised as something else
                    if _looks_like_html(resp.content):
                        logger.debug(f"[PDFEnricher] Rejected HTML error page for {paper.title[:60]}")
                    return

                with open(filepath, "wb") as f:
                    f.write(resp.content)

                paper.pdf_path = filepath
                paper.full_text = self._extract_text(filepath)
        except Exception as e:
            logger.debug(f"[PDFEnricher] failed for {paper.title[:60]}: {e}")

    def _extract_text(self, pdf_path: str) -> str:
        try:
            doc = fitz.open(pdf_path)
            parts = []
            for i in range(min(len(doc), 30)):
                t = doc[i].get_text()
                if t.strip():
                    parts.append(t)
            doc.close()
            return "\n".join(parts)
        except Exception:
            return ""