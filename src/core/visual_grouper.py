import logging
import os
import hashlib
import base64
from typing import List, Dict, Optional

from core.llm_service import LLMService
from core.pdf_parser import PDFParser

logger = logging.getLogger(__name__)
PDF_DIR = os.getenv("PDF_DOWNLOAD_DIR", "./downloaded_pdfs")


class VisualGrouperAgent:
    def __init__(self):
        self.llm = LLMService()
        self.pdf_parser = PDFParser()

    async def group_visuals(self, paper: dict, visual_items: List[dict]) -> List[dict]:
        if not visual_items:
            return []

        figures = [v for v in visual_items if v.get("item_type") == "figure"]
        tables = [v for v in visual_items if v.get("item_type") == "table"]
        equations = [v for v in visual_items if v.get("item_type") == "equation"]

        groups = []
        pdf_images = await self._extract_images_from_pdf(paper)

        if figures:
            groups.extend(await self._group_by_similarity(figures, "figure", paper, pdf_images))
        if tables:
            groups.extend(await self._group_by_similarity(tables, "table", paper, pdf_images))
        if equations:
            groups.extend(await self._group_equations(equations, paper))

        logger.info(f"[VisualGrouper] Created {len(groups)} visual groups")
        return groups

    async def _extract_images_from_pdf(self, paper: dict) -> Dict[int, List[dict]]:
        images_by_page = {}
        pdf_url = paper.get("pdf_url", "")
        if not pdf_url:
            return images_by_page

        filename = hashlib.md5(pdf_url.encode()).hexdigest() + ".pdf"
        filepath = os.path.join(PDF_DIR, filename)
        if not os.path.exists(filepath):
            return images_by_page

        try:
            import fitz
            doc = fitz.open(filepath)
            for page_num in range(min(len(doc), 30)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                page_images = []

                for img in image_list[:5]:
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        if base_image:
                            img_bytes = base_image["image"]
                            img_ext = base_image.get("ext", "png")
                            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                            if len(img_bytes) > 5000:
                                page_images.append({
                                    "image_base64": img_b64,
                                    "mime_type": f"image/{img_ext}",
                                    "page_number": page_num + 1,
                                    "width": base_image.get("width", 0),
                                    "height": base_image.get("height", 0),
                                })
                    except Exception:
                        continue

                if page_images:
                    images_by_page[page_num + 1] = page_images
            doc.close()
        except Exception as e:
            logger.warning(f"[VisualGrouper] Image extraction failed: {e}")

        return images_by_page

    async def _group_by_similarity(self, items: List[dict], item_type: str, paper: dict, pdf_images: Dict[int, List[dict]]) -> List[dict]:
        if len(items) <= 2:
            group = await self._create_group(items, item_type, 0, paper, pdf_images)
            return [group] if group else []

        items_desc = "\n".join(
            f"- {v.get('label', 'Unknown')}: {v.get('caption', v.get('explanation', ''))[:100]}"
            for v in items
        )

        prompt = f"""You are grouping {item_type}s from a research paper by semantic similarity.

Items:
{items_desc}

Group these into logical clusters based on what they show/represent.

Return JSON:
{{
    "groups": [
        {{
            "group_label": "Performance Comparison",
            "item_labels": ["Figure 1", "Figure 3"],
            "reason": "Both show performance metrics across methods"
        }}
    ]
}}

Return ONLY valid JSON."""

        if item_type == "figure":
            result = await self.llm.call_image_json(prompt)
        elif item_type == "table":
            result = await self.llm.call_graph_json(prompt)
        else:
            result = await self.llm.call_text_json(prompt)

        raw_groups = result.get("groups", [])
        if not raw_groups:
            group = await self._create_group(items, item_type, 0, paper, pdf_images)
            return [group] if group else []

        groups = []
        used_items = set()

        for gi, rg in enumerate(raw_groups):
            group_labels = set(l.lower() for l in rg.get("item_labels", []))
            group_items = [
                item for item in items
                if item.get("label", "").lower() in group_labels
            ]
            if not group_items:
                for item in items:
                    label = item.get("label", "").lower()
                    if any(gl in label or label in gl for gl in group_labels):
                        group_items.append(item)

            for item in group_items:
                used_items.add(id(item))

            if group_items:
                group = await self._create_group(
                    group_items, item_type, gi, paper, pdf_images,
                    label=rg.get("group_label", "")
                )
                if group:
                    groups.append(group)

        ungrouped = [item for item in items if id(item) not in used_items]
        if ungrouped:
            group = await self._create_group(
                ungrouped, item_type, len(groups), paper, pdf_images,
                label=f"Other {item_type.title()}s"
            )
            if group:
                groups.append(group)

        return groups

    async def _group_equations(self, equations: List[dict], paper: dict) -> List[dict]:
        if not equations:
            return []

        eq_desc = "\n".join(
            f"- {e.get('label', 'Unknown')}: {e.get('caption', '')[:80]}"
            for e in equations
        )

        prompt = f"""Group these mathematical equations from a research paper:

{eq_desc}

Group by purpose: "loss functions", "model equations", "constraints",
"optimization objectives", "metrics", etc.

Return JSON:
{{
    "groups": [
        {{
            "group_label": "Loss Functions",
            "item_labels": ["Eq. (1)", "Eq. (3)"],
            "summary": "These equations define the training objectives"
        }}
    ]
}}

Return ONLY valid JSON."""

        result = await self.llm.call_equation_json(prompt)
        raw_groups = result.get("groups", [])

        groups = []
        if not raw_groups:
            groups.append({
                "group_id": "eq_group_0",
                "group_type": "equations",
                "group_label": "Mathematical Formulations",
                "group_summary": "Equations used in the paper",
                "items": equations,
                "item_count": len(equations),
            })
        else:
            for gi, rg in enumerate(raw_groups):
                group_labels = set(l.lower() for l in rg.get("item_labels", []))
                group_items = [eq for eq in equations if eq.get("label", "").lower() in group_labels]
                if not group_items:
                    for eq in equations:
                        label = eq.get("label", "").lower()
                        if any(gl in label for gl in group_labels):
                            group_items.append(eq)
                if group_items:
                    groups.append({
                        "group_id": f"eq_group_{gi}",
                        "group_type": "equations",
                        "group_label": rg.get("group_label", f"Equation Group {gi+1}"),
                        "group_summary": rg.get("summary", ""),
                        "items": group_items,
                        "item_count": len(group_items),
                    })
        return groups

    async def _create_group(self, items, item_type, group_idx, paper, pdf_images, label=""):
        if not items:
            return None

        image_analyses = []
        if item_type == "figure" and pdf_images:
            for item in items:
                page_num = item.get("page_number", item.get("anchor", {}).get("page_number"))
                if page_num and page_num in pdf_images:
                    for img in pdf_images[page_num][:1]:
                        try:
                            analysis = await self.llm.call_image_with_base64(
                                f"Describe this scientific figure. Context: {item.get('caption', '')[:100]}",
                                img["image_base64"],
                                img["mime_type"]
                            )
                            if analysis:
                                item["vision_analysis"] = analysis
                                image_analyses.append(analysis)
                        except Exception as e:
                            logger.debug(f"Image analysis failed: {e}")

        items_text = "\n".join(
            f"- {v.get('label', 'Unknown')}: "
            f"{v.get('vision_analysis', v.get('explanation', v.get('caption', '')))[:150]}"
            for v in items
        )

        if item_type == "figure":
            group_summary = await self.llm.call_image(
                f"Summarize this group of figures:\n{items_text}\nWhat do they collectively show? 1-2 sentences."
            )
        elif item_type == "table":
            group_summary = await self.llm.call_graph(
                f"Summarize this group of tables:\n{items_text}\nWhat data do they present? 1-2 sentences."
            )
        elif item_type == "equation":
            group_summary = await self.llm.call_equation(
                f"Summarize this group of equations:\n{items_text}\nWhat do they define mathematically? 1-2 sentences."
            )
        else:
            group_summary = await self.llm.call_text(f"Summarize these visual elements:\n{items_text}")

        for item in items:
            if "anchor" not in item:
                item["anchor"] = {
                    "page_number": item.get("page_number", 1),
                    "match_text": item.get("match_text", item.get("label", "")),
                    "item_type": item_type,
                    "label": item.get("label", ""),
                }

        return {
            "group_id": f"{item_type}_group_{group_idx}",
            "group_type": f"{item_type}s",
            "group_label": label or f"{item_type.title()} Group {group_idx + 1}",
            "group_summary": group_summary.strip() if group_summary else "",
            "items": items,
            "item_count": len(items),
        }