from config import get_logger

log = get_logger("locator")


class Locator:
    def locate_fact(self, claim: str, evidence_text: str, pages: list, idx: int = 0) -> dict:
        best_page, best_snippet = 1, evidence_text[:80] if evidence_text else claim[:80]
        for page in pages:
            if evidence_text and evidence_text[:50] in page["text"]:
                best_page = page["page_number"]
                pos = page["text"].index(evidence_text[:50])
                best_snippet = page["text"][pos:pos+80].strip()
                break
            words = set(claim.lower().split())
            overlap = sum(1 for w in words if w in page["text"].lower())
            if words and overlap > len(words) * 0.6:
                best_page = page["page_number"]
        return {
            "anchor_id": f"fact_{idx:03d}",
            "page_number": best_page,
            "match_text": best_snippet,
            "item_type": "fact",
            "label": claim[:60],
        }

    def locate_visual(self, item: dict, pages: list, idx: int = 0) -> dict:
        label = item.get("label", "")
        match_text = item.get("match_text", item.get("caption", "")[:80])
        page_number = item.get("page_number", 1)
        for page in pages:
            if label.lower() in page["text"].lower():
                page_number = page["page_number"]
                pos = page["text"].lower().find(label.lower())
                if pos >= 0:
                    match_text = page["text"][pos:pos+80].strip()
                break
        return {
            "anchor_id": f"{item.get('item_type', 'vis')}_{idx:03d}",
            "page_number": page_number,
            "match_text": match_text,
            "item_type": item.get("item_type", "visual"),
            "label": label,
        }

    def add_anchors_to_evidence(self, evidence_items: list, pages: list) -> list:
        for i, item in enumerate(evidence_items):
            item["anchor"] = self.locate_fact(
                item.get("claim", ""), item.get("evidence_text", ""), pages, i
            )
        return evidence_items

    def add_anchors_to_visuals(self, visual_items: list, pages: list) -> list:
        for i, item in enumerate(visual_items):
            item["anchor"] = self.locate_visual(item, pages, i)
        return visual_items