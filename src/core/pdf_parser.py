"""
core/pdf_parser.py — PDF text extraction with validated downloads.

Post-extraction validation rejects extracted text that looks like
an error page rather than a real research paper.
"""

import os
import logging
import hashlib
import re
from typing import Optional

from core.pdf_downloader import PDFDownloader, _looks_like_html, PDF_MAGIC, MIN_PDF_SIZE
from core.config import Config

logger = logging.getLogger(__name__)

# Patterns that indicate extracted text is from an error page, not a paper
_ERROR_PAGE_PATTERNS = [
    re.compile(r'(access\s+denied|403\s+forbidden|404\s+not\s+found)', re.IGNORECASE),
    re.compile(r'(page\s+not\s+found|file\s+not\s+found)', re.IGNORECASE),
    re.compile(r'(sign\s+in\s+to|log\s+in\s+to|create\s+an?\s+account)', re.IGNORECASE),
    re.compile(r'(cookies?\s+(are\s+)?required|enable\s+javascript)', re.IGNORECASE),
    re.compile(r'(subscription\s+required|purchase\s+this\s+article)', re.IGNORECASE),
    re.compile(r'(request\s+unsuccessful|too\s+many\s+requests|rate\s+limit)', re.IGNORECASE),
    re.compile(r'<html|<head|<body|<div\s|<script', re.IGNORECASE),
]


def _is_error_page_text(text: str) -> bool:
    """Check if extracted PDF text is actually from an error/paywall page."""
    if not text or len(text.strip()) < 50:
        return True  # Too little text = likely not a real paper

    # Check first 2000 chars for error patterns
    sample = text[:2000]
    matches = sum(1 for pat in _ERROR_PAGE_PATTERNS if pat.search(sample))
    if matches >= 2:
        return True

    # If it has HTML tags in the extracted text, it's an HTML page saved as PDF
    html_tag_count = len(re.findall(r'<[a-z]+[\s>]', sample, re.IGNORECASE))
    if html_tag_count > 5:
        return True

    return False


class PDFParser:
    def __init__(self):
        self.downloader = PDFDownloader()
        self.download_dir = Config.PDF_DIR
        os.makedirs(self.download_dir, exist_ok=True)

    def parse_from_pdf_url(self, url: str) -> dict:
        if not url or not url.strip():
            return {"pages": [], "sections": [], "visual_items": []}

        pdf_hash = hashlib.md5(url.encode()).hexdigest()
        local_path = os.path.join(self.download_dir, f"{pdf_hash}.pdf")

        if self.downloader.validate_existing(local_path):
            logger.info(f"   ♻️ Cached: {pdf_hash}.pdf")
        else:
            filepath = self._download_validated(url)
            if not filepath:
                return {"pages": [], "sections": [], "visual_items": []}
            local_path = filepath

        result = self._extract(local_path)

        # Post-extraction validation: reject error pages saved as PDF
        if result.get("pages"):
            full_text = " ".join(p.get("text", "") for p in result["pages"][:3])
            if _is_error_page_text(full_text):
                logger.warning(f"   🗑️ Extracted text looks like error page, rejecting: {url[:60]}")
                # Remove the bad cached file
                try:
                    os.remove(local_path)
                except OSError:
                    pass
                return {"pages": [], "sections": [], "visual_items": []}

        return result

    def parse_from_local(self, filepath: str) -> dict:
        if not self.downloader.validate_existing(filepath):
            return {"pages": [], "sections": [], "visual_items": []}

        result = self._extract(filepath)

        # Post-extraction validation
        if result.get("pages"):
            full_text = " ".join(p.get("text", "") for p in result["pages"][:3])
            if _is_error_page_text(full_text):
                logger.warning(f"   🗑️ Local file looks like error page: {filepath}")
                return {"pages": [], "sections": [], "visual_items": []}

        return result

    def parse_from_text(self, text: str) -> dict:
        if not text or not text.strip():
            return {"pages": [], "sections": [], "visual_items": []}
        pages = []
        for i in range(0, len(text), 3000):
            chunk = text[i:i+3000].strip()
            if chunk:
                pages.append({"page_number": i // 3000 + 1, "text": chunk})
        return {"pages": pages, "sections": [], "visual_items": []}

    def _download_validated(self, url: str) -> Optional[str]:
        import requests
        try:
            resp = requests.get(url, timeout=30, allow_redirects=True, stream=True,
                                headers={"User-Agent": "Mozilla/5.0 (compatible; ResearchPipeline/2.0)"})
            if resp.status_code != 200:
                return None

            ct = resp.headers.get("content-type", "").lower()
            # Reject HTML pages
            if "text/html" in ct:
                logger.debug(f"   [PDFParser] Rejected HTML from {url[:60]}")
                return None
            # Reject other non-PDF types
            if any(bad in ct for bad in ["text/xml", "text/plain", "application/json"]):
                logger.debug(f"   [PDFParser] Rejected non-PDF type '{ct}' from {url[:60]}")
                return None

            initial = next(resp.iter_content(chunk_size=4096), b"")
            if not initial.startswith(PDF_MAGIC):
                if _looks_like_html(initial):
                    logger.debug(f"   [PDFParser] Rejected HTML disguised as PDF from {url[:60]}")
                return None

            chunks = [initial]
            total = len(initial)
            for chunk in resp.iter_content(chunk_size=65536):
                chunks.append(chunk)
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    return None
            content = b"".join(chunks)
            if len(content) < MIN_PDF_SIZE:
                return None

            pdf_hash = hashlib.md5(url.encode()).hexdigest()
            filepath = os.path.join(self.download_dir, f"{pdf_hash}.pdf")
            with open(filepath, "wb") as f:
                f.write(content)
            return filepath
        except Exception:
            return None

    def _extract(self, filepath: str) -> dict:
        pages = []
        sections = []
        visual_items = []
        try:
            import fitz
            doc = fitz.open(filepath)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text").strip()
                images = page.get_images(full=True)
                for img_idx, img in enumerate(images):
                    visual_items.append({
                        "type": "figure", "page_number": page_num + 1, "index": img_idx,
                    })
                if text:
                    pages.append({"page_number": page_num + 1, "text": text})
                    section = self._detect_section(text)
                    if section:
                        sections.append({"type": section, "page_number": page_num + 1})
            doc.close()
            logger.info(f"   📄 Parsed {len(pages)} pages, {len(visual_items)} visuals")
        except Exception as e:
            logger.error(f"   ⚠️ PDF parse error: {e}")
        return {"pages": pages, "sections": sections, "visual_items": visual_items}

    @staticmethod
    def _detect_section(text: str) -> Optional[str]:
        lower = text.lower()[:500]
        for kw, name in [("abstract", "abstract"), ("introduction", "introduction"),
                         ("method", "methodology"), ("methodology", "methodology"),
                         ("result", "results"), ("conclusion", "conclusion"),
                         ("reference", "references")]:
            if kw in lower:
                return name
        return None