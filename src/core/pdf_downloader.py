"""
core/pdf_downloader.py — DOI-first PDF pipeline.

Pipeline order (per spec):
  Start with metadata (SS/OA) → DOI is single source of truth
  Tier 1: Publisher via DOI redirect, Unpaywall
  Tier 2: Semantic Scholar openAccessPdf, OpenAlex oa_url
  Tier 3: arXiv (preprint fallback)

Every download is validated for:
  1. HTTP Content-Type header (rejects text/html)
  2. PDF magic bytes (%PDF-)
  3. Minimum file size (10KB)
  4. Post-download HTML-sniff
  5. PDF metadata verification (title/author match where possible)
"""

import os
import logging
import hashlib
import requests
import time
import re
from typing import Optional, List, Tuple
from urllib.parse import quote

from core.config import Config

logger = logging.getLogger(__name__)

PDF_MAGIC = b'%PDF-'
MIN_PDF_SIZE = 10_240
MAX_PDF_SIZE = 100 * 1024 * 1024

_HTML_SIGNATURES = [
    b'<!doctype html', b'<!DOCTYPE html', b'<html', b'<HTML',
    b'<head', b'<HEAD', b'<?xml version', b'{"error', b'{"message',
    b'Access Denied', b'403 Forbidden', b'404 Not Found', b'Page Not Found',
]


def _looks_like_html(data: bytes) -> bool:
    if not data:
        return True
    header = data[:2048]
    for bom in [b'\xef\xbb\xbf', b'\xff\xfe', b'\xfe\xff']:
        if header.startswith(bom):
            header = header[len(bom):]
    header_stripped = header.lstrip()
    for sig in _HTML_SIGNATURES:
        if header_stripped.startswith(sig) or header_stripped[:512].find(sig) != -1:
            return True
    return False


def _norm_title(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _title_overlap(a: str, b: str) -> float:
    sa, sb = set(_norm_title(a).split()), set(_norm_title(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class PDFDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; ResearchPipeline/3.0; mailto:research@pipeline.org)"
        })
        if Config.SEMANTIC_SCHOLAR_API_KEY:
            self.session.headers["x-api-key"] = Config.SEMANTIC_SCHOLAR_API_KEY

        self.download_dir = Config.PDF_DIR
        os.makedirs(self.download_dir, exist_ok=True)
        self.unpaywall_email = Config.UNPAYWALL_EMAIL

    # ── Public API ────────────────────────────────────────────────────

    def download_pdf(self, paper: dict) -> Optional[str]:
        """
        DOI-first tiered PDF acquisition.

        Order:
          Tier 1: Unpaywall (requires DOI, returns publisher/OA best link)
                  Publisher via DOI redirect
          Tier 2: Semantic Scholar openAccessPdf (paper['pdf_url'])
                  OpenAlex oa_url (paper['openalex_oa_url'])
          Tier 3: arXiv (preprint only)
        """
        sources = self._build_sources(paper)
        expected_title = paper.get("title", "") or ""

        for name, url in sources:
            if not url or not url.strip():
                continue
            logger.info(f"   📥 Trying {name}: {url[:80]}")
            filepath = self._try_download(url, name)
            if filepath:
                # Verify the downloaded PDF
                if self._verify_pdf(filepath, expected_title):
                    logger.info(f"   ✅ PDF from {name} (verified)")
                    return filepath
                else:
                    logger.info(f"   ⚠️ PDF from {name} failed verification — removing")
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
            logger.info(f"   ❌ {name} failed")
            time.sleep(0.3)

        logger.warning(f"   ⛔ All sources failed for '{(expected_title or '')[:60]}'")
        return None

    def get_pdf_url(self, paper: dict) -> Optional[str]:
        """Return the first URL that resolves to a plausible PDF (HEAD-probed)."""
        sources = self._build_sources(paper)
        for name, url in sources:
            if not url or not url.strip():
                continue
            # Resolve Unpaywall/arXiv-search to concrete URLs first
            concrete = self._resolve_concrete_url(url, name)
            if concrete and self._validate_remote(concrete):
                return concrete
            time.sleep(0.2)
        return None

    def validate_existing(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                header = f.read(2048)
                if not header.startswith(PDF_MAGIC):
                    logger.info(f"   🗑️ Removing non-PDF cached file: {filepath}")
                    os.remove(filepath)
                    return False
                f.seek(0, 2)
                size = f.tell()
                if size < MIN_PDF_SIZE:
                    logger.info(f"   🗑️ Removing too-small file ({size}B): {filepath}")
                    os.remove(filepath)
                    return False
                if _looks_like_html(header):
                    logger.info(f"   🗑️ Removing HTML-disguised-as-PDF: {filepath}")
                    os.remove(filepath)
                    return False
            return True
        except Exception:
            return False

    def get_or_download(self, paper: dict) -> Tuple[Optional[str], str]:
        pdf_url = paper.get("pdf_url", "") or ""
        pdf_hash = hashlib.md5((pdf_url or paper.get("title", "")).encode()).hexdigest()
        cached = os.path.join(self.download_dir, f"{pdf_hash}.pdf")

        if self.validate_existing(cached):
            return cached, pdf_hash

        filepath = self.download_pdf(paper)
        if filepath:
            h = os.path.splitext(os.path.basename(filepath))[0]
            return filepath, h
        return None, ""

    # ── Source ordering (DOI-first tiered) ────────────────────────────

    def _build_sources(self, paper: dict) -> List[Tuple[str, str]]:
        sources = []
        doi          = paper.get("doi", "") or ""
        ss_pdf       = paper.get("pdf_url", "") or ""
        openalex_pdf = paper.get("openalex_oa_url", "") or ""
        arxiv_id     = paper.get("arxiv_id", "") or ""
        title        = paper.get("title", "") or ""

        # ── Tier 1: DOI-based authoritative sources ──
        if doi and self.unpaywall_email:
            sources.append(("Unpaywall", f"unpaywall://{doi}"))
        if doi:
            sources.append(("Publisher (DOI)", f"https://doi.org/{doi}"))

        # ── Tier 2: Metadata-provider OA links ──
        if ss_pdf and self._is_plausible(ss_pdf):
            sources.append(("Semantic Scholar OA", ss_pdf))
        if openalex_pdf and self._is_plausible(openalex_pdf):
            sources.append(("OpenAlex OA", openalex_pdf))

        # ── Tier 3: arXiv (preprint fallback) ──
        if arxiv_id:
            clean = arxiv_id.replace("arXiv:", "").replace("arxiv:", "").strip()
            sources.append(("ArXiv Direct", f"https://arxiv.org/pdf/{clean}.pdf"))
        if title and not arxiv_id:
            sources.append(("ArXiv Title Search", f"arxivsearch://{title}"))

        return sources

    # ── Download / URL resolution ─────────────────────────────────────

    def _try_download(self, url: str, source_name: str) -> Optional[str]:
        if url.startswith("unpaywall://"):
            return self._try_unpaywall(url.replace("unpaywall://", ""))
        if url.startswith("arxivsearch://"):
            return self._try_arxiv_search(url.replace("arxivsearch://", ""))

        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True, stream=True)
            if resp.status_code != 200:
                return None

            ct = resp.headers.get("content-type", "").lower()
            if "text/html" in ct:
                logger.debug(f"   [PDF] Rejected HTML from {url[:60]}")
                return None
            if any(bad in ct for bad in ["text/xml", "text/plain", "application/json"]):
                logger.debug(f"   [PDF] Rejected non-PDF '{ct}' from {url[:60]}")
                return None

            initial = next(resp.iter_content(chunk_size=4096), b"")
            if not initial.startswith(PDF_MAGIC):
                if _looks_like_html(initial):
                    logger.debug(f"   [PDF] HTML disguised as PDF from {url[:60]}")
                return None

            chunks = [initial]
            total = len(initial)
            for chunk in resp.iter_content(chunk_size=65536):
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_PDF_SIZE:
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

    def _resolve_concrete_url(self, url: str, name: str) -> Optional[str]:
        """Resolve protocol-prefixed pseudo-URLs to concrete HTTPS URLs for HEAD probes."""
        if url.startswith("unpaywall://"):
            doi = url.replace("unpaywall://", "")
            return self._unpaywall_best_url(doi)
        if url.startswith("arxivsearch://"):
            return None  # resolved only when downloading
        return url

    def _validate_remote(self, url: str) -> bool:
        try:
            resp = self.session.head(url, timeout=10, allow_redirects=True)
            if resp.status_code != 200:
                return False
            ct = resp.headers.get("content-type", "").lower()
            if "text/html" in ct:
                return False
            if any(bad in ct for bad in ["text/xml", "text/plain", "application/json"]):
                return False
            if "pdf" in ct:
                return True
            resp2 = self.session.get(url, timeout=15, allow_redirects=True,
                                     headers={"Range": "bytes=0-64"})
            if resp2.status_code in (200, 206):
                data = resp2.content
                if data.startswith(PDF_MAGIC) and not _looks_like_html(data):
                    return True
        except Exception:
            pass
        return False

    # ── Unpaywall ─────────────────────────────────────────────────────

    def _unpaywall_best_url(self, doi: str) -> Optional[str]:
        if not self.unpaywall_email:
            return None
        try:
            resp = self.session.get(
                f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                params={"email": self.unpaywall_email}, timeout=15
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf", "") or ""
            if pdf_url:
                return pdf_url
            for loc in data.get("oa_locations", []) or []:
                pdf_url = loc.get("url_for_pdf", "") or ""
                if pdf_url:
                    return pdf_url
        except Exception:
            pass
        return None

    def _try_unpaywall(self, doi: str) -> Optional[str]:
        if not self.unpaywall_email:
            return None
        try:
            resp = self.session.get(
                f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                params={"email": self.unpaywall_email}, timeout=15
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf", "") or ""
            if pdf_url:
                result = self._try_download(pdf_url, "Unpaywall Best")
                if result:
                    return result
            for loc in data.get("oa_locations", []) or []:
                pdf_url = loc.get("url_for_pdf", "") or ""
                if pdf_url:
                    result = self._try_download(pdf_url, "Unpaywall OA")
                    if result:
                        return result
        except Exception:
            pass
        return None

    # ── arXiv title search ────────────────────────────────────────────

    def _try_arxiv_search(self, title: str) -> Optional[str]:
        import xml.etree.ElementTree as ET
        try:
            resp = self.session.get(
                "http://export.arxiv.org/api/query",
                params={"search_query": f"all:{quote(title)}", "max_results": 3,
                        "sortBy": "relevance"},
                timeout=20
            )
            if resp.status_code != 200:
                return None
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                entry_id = entry.find("atom:id", ns)
                if entry_id is None or not entry_id.text:
                    continue
                arxiv_id = entry_id.text.split("/abs/")[-1] if "/abs/" in entry_id.text else ""
                if arxiv_id:
                    result = self._try_download(f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                                                "ArXiv Search")
                    if result:
                        return result
        except Exception:
            pass
        return None

    # ── PDF verification (title check) ────────────────────────────────

    def _verify_pdf(self, filepath: str, expected_title: str) -> bool:
        """
        Verify a downloaded PDF matches the expected paper.
        Checks PDF metadata title against expected title (Jaccard overlap).
        Falls back to first-page text scan if metadata missing.
        """
        if not expected_title or len(expected_title) < 10:
            # Can't verify — accept if file is a valid PDF
            return True

        try:
            import fitz  # PyMuPDF
            doc = fitz.open(filepath)
            try:
                meta_title = (doc.metadata or {}).get("title", "") or ""
                if meta_title and _title_overlap(meta_title, expected_title) >= 0.5:
                    return True

                # Fallback: scan first page for title tokens
                if len(doc) > 0:
                    first_page_text = doc[0].get_text("text") or ""
                    # Use first 500 chars (typical title region)
                    head = first_page_text[:500].lower()
                    expected_words = set(_norm_title(expected_title).split())
                    # Need at least 40% of expected title words on page 1
                    if expected_words:
                        hits = sum(1 for w in expected_words if len(w) > 3 and w in head)
                        overlap = hits / len(expected_words)
                        if overlap >= 0.4:
                            return True
                        logger.debug(f"   [Verify] Title overlap too low ({overlap:.2f}) "
                                     f"for '{expected_title[:50]}'")
                        return False
            finally:
                doc.close()
        except Exception as e:
            logger.debug(f"   [Verify] PDF verification error: {e}")
            # If verification fails due to library error, don't reject
            return True

        return False

    # ── URL plausibility ──────────────────────────────────────────────

    @staticmethod
    def _is_plausible(url: str) -> bool:
        if not url:
            return False
        u = url.lower()

        bad = [
            "scholar.google",
            "researchgate.net/profile",
            "researchgate.net/publication",
            "ieee.org/abstract",
            "dl.acm.org/doi/abs",
            "dl.acm.org/doi/10.",
            "semanticscholar.org/paper/",
            "semanticscholar.org/reader/",
            "sciencedirect.com/science/article",
            "springer.com/article",
            "wiley.com/doi/abs",
            "tandfonline.com/doi/abs",
            "login",
            "signin",
            "subscribe",
        ]
        if any(d in u for d in bad):
            return False

        good = [
            "arxiv.org/pdf",
            "aclweb.org",
            "openreview.net/pdf",
            "proceedings.mlr.press",
            "jmlr.org",
            "nature.com/articles",
            "pnas.org/doi/pdf",
            "ncbi.nlm.nih.gov/pmc/articles",
            "doi.org",
        ]
        if any(d in u for d in good):
            return True
        if u.endswith(".pdf"):
            return True

        return True