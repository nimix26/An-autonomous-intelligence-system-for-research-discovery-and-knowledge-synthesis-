"""
core/chunked_processor.py — 2-3 page chunks with rolling context.
Separate extraction of figures, equations, graphs. Groups similar visuals.
"""

import hashlib
import logging
from typing import List, Dict

from core.llm_service import LLMService
from core.pdf_parser import PDFParser
from core.pdf_downloader import PDFDownloader

logger = logging.getLogger(__name__)


class ChunkedProcessor:
    def __init__(self):
        self.llm = LLMService()
        self.pdf_parser = PDFParser()
        self.pdf_downloader = PDFDownloader()

    async def process_paper(self, paper: dict, context: dict, pdf_url: str = None) -> dict:
        pages = self._get_pages(paper, pdf_url)
        if not pages:
            logger.warning(f"      ⚠️ No pages for '{paper.get('title', '')[:50]}'")
            return self._empty_result(pdf_url)

        chunks = self._create_chunks(pages)
        logger.info(f"         ↳ {len(pages)} pages → {len(chunks)} chunks")

        chunk_summaries = []
        all_visuals = []
        all_equations = []
        all_graphs = []
        rolling_context = ""

        for i, chunk in enumerate(chunks):
            logger.info(f"         Processing chunk {i+1}/{len(chunks)} (pages {chunk['page_range']})")
            result = await self.llm.summarize_chunk(
                chunk_text=chunk["text"][:25000],
                paper_title=paper.get("title", "Unknown") or "Unknown",
                chunk_info={"page_range": chunk["page_range"], "previous_summary": rolling_context[-800:]},
                context=context,
            )

            page_range = chunk["page_range"]
            first_page = chunk["page_numbers"][0] if chunk["page_numbers"] else 1

            for v in result.get("visual_elements", []) or []:
                if "page_number" not in v or not v["page_number"]:
                    v["page_number"] = first_page
                v["source_pages"] = page_range
                all_visuals.append(v)

            for e in result.get("mathematical_content", []) or []:
                if "page_number" not in e or not e["page_number"]:
                    e["page_number"] = first_page
                e["source_pages"] = page_range
                all_equations.append(e)

            for g in result.get("graph_elements", []) or []:
                if "page_number" not in g or not g["page_number"]:
                    g["page_number"] = first_page
                g["source_pages"] = page_range
                all_graphs.append(g)

            chunk_summaries.append({
                "chunk_id": i,
                "pages": chunk["page_numbers"],
                "page_range": page_range,
                "section_type": result.get("section_type", "content") or "content",
                "summary": result.get("summary", "") or "",
                "key_points": result.get("key_points", []) or [],
                "importance": result.get("importance", "medium") or "medium",
            })

            rolling_context += f"\n[Pages {page_range}] {result.get('summary', '')[:300]}"
            if len(rolling_context) > 6000:
                rolling_context = rolling_context[-6000:]

        # Combine summaries
        combined = await self.llm.combine_summaries(
            chunk_summaries, paper.get("title", "Unknown") or "Unknown", context
        )

        # Group visual elements
        logger.info(f"         Grouping {len(all_visuals)} figures, {len(all_equations)} equations, {len(all_graphs)} graphs")
        visual_groups = await self.llm.group_visual_elements(
            all_visuals, all_equations, all_graphs,
            paper_title=paper.get("title", "Unknown") or "Unknown",
            context=context,
        )

        # PDF hash — for local API URLs, extract hash directly; otherwise try download
        effective_url = pdf_url or paper.get("pdf_url", "") or ""
        pdf_hash = ""
        if effective_url:
            import re as _re
            local_match = _re.search(r'/pdf/([a-f0-9]{32})$', effective_url)
            if local_match:
                pdf_hash = local_match.group(1)
            else:
                _, pdf_hash = self.pdf_downloader.get_or_download(paper)
                if not pdf_hash:
                    pdf_hash = hashlib.md5(effective_url.encode()).hexdigest()

        total_items = sum(len(g.get("items", [])) for g in visual_groups)
        logger.info(f"         ✅ {len(visual_groups)} visual groups, {total_items} total items")

        return {
            "summary": combined.get("summary", "") or "",
            "key_insights": combined.get("key_insights", []) or [],
            "methodology": combined.get("methodology", "") or "",
            "results": combined.get("results", "") or "",
            "limitations": combined.get("limitations", "") or "",
            "visual_groups": visual_groups,
            "chunk_summaries": chunk_summaries,
            "total_chunks": len(chunks),
            "pages_processed": len(pages),
            "pdf_url": effective_url,
            "pdf_hash": pdf_hash,
            "title": paper.get("title", "") or "",
        }

    def _empty_result(self, pdf_url: str = "") -> dict:
        return {
            "summary": "", "key_insights": [], "methodology": "",
            "results": "", "limitations": "",
            "visual_groups": [],
            "chunk_summaries": [], "total_chunks": 0, "pages_processed": 0,
            "pdf_url": pdf_url or "", "pdf_hash": "", "title": "",
        }

    def _get_pages(self, paper: dict, pdf_url: str = None) -> List[dict]:
        url = pdf_url or paper.get("pdf_url", "") or ""

        if url:
            # Check if this is a local API URL (e.g. http://localhost:8000/pdf/<hash>)
            # If so, resolve to the actual file on disk instead of re-downloading
            import re as _re
            local_match = _re.search(r'/pdf/([a-f0-9]{32})$', url)
            if local_match:
                import os
                from core.config import Config
                local_path = os.path.join(Config.PDF_DIR, f"{local_match.group(1)}.pdf")
                if os.path.exists(local_path):
                    parsed = self.pdf_parser.parse_from_local(local_path)
                    if parsed.get("pages"):
                        return parsed["pages"]

            # Otherwise try as a remote URL
            parsed = self.pdf_parser.parse_from_pdf_url(url)
            if parsed.get("pages"):
                return parsed["pages"]

        text = paper.get("full_text", "") or paper.get("abstract", "") or ""
        if not text:
            return []
        return [{"page_number": i // 3000 + 1, "text": text[i:i+3000]}
                for i in range(0, len(text), 3000) if text[i:i+3000].strip()]

    def _create_chunks(self, pages: List[dict]) -> List[dict]:
        chunks, i = [], 0
        while i < len(pages):
            chunk_pages, chunk_text, chunk_nums = [], "", []
            max_pages = 3 if len(pages[i]["text"]) < 1500 else 2
            while (i < len(pages) and len(chunk_pages) < max_pages
                   and len(chunk_text) + len(pages[i]["text"]) <= 28000):
                chunk_pages.append(pages[i])
                chunk_text += f"\n\n--- PAGE {pages[i]['page_number']} ---\n{pages[i]['text']}"
                chunk_nums.append(pages[i]["page_number"])
                i += 1
            if chunk_pages:
                page_range = f"{chunk_nums[0]}-{chunk_nums[-1]}" if len(chunk_nums) > 1 else str(chunk_nums[0])
                chunks.append({
                    "pages": chunk_pages, "text": chunk_text.strip(),
                    "page_numbers": chunk_nums, "page_range": page_range,
                })
        return chunks