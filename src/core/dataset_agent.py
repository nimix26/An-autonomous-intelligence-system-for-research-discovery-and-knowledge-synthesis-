import logging
import re
from typing import List

from core.llm_service import LLMService
from core.pdf_parser import PDFParser

logger = logging.getLogger(__name__)


class DatasetAgent:
    def __init__(self):
        self.llm = LLMService()
        self.pdf_parser = PDFParser()

    async def extract_datasets(self, paper: dict) -> List[dict]:
        text = paper.get("full_text", "") or paper.get("abstract", "")
        if not text or len(text.strip()) < 100:
            return []

        regex_datasets = self._regex_find_datasets(text)
        llm_datasets = await self._llm_extract_datasets(text, paper.get("title", ""))
        all_datasets = self._merge_datasets(regex_datasets, llm_datasets)

        parsed = self._get_parsed_pages(paper)
        if parsed.get("pages"):
            all_datasets = self._add_page_numbers(all_datasets, parsed["pages"])

        logger.info(f"[DatasetAgent] Found {len(all_datasets)} datasets")
        return all_datasets

    def _regex_find_datasets(self, text: str) -> List[dict]:
        datasets = []
        patterns = [
            r'(?:the\s+)?([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)\s+dataset',
            r'(?:trained|evaluated|tested|benchmarked)\s+on\s+(?:the\s+)?([A-Z][A-Za-z0-9\-/]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)',
            r'([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)\s+benchmark',
            r'\b(MNIST|CIFAR[-\s]?\d+|ImageNet|COCO|SQuAD|GLUE|SuperGLUE|WikiText[-\s]?\d*|Penn\s+Treebank|PTB|WMT[-\s]?\d+|Common\s+Crawl|WebText|BookCorpus|OpenWebText|LAMA|Natural\s+Questions|TriviaQA|MS\s+MARCO|VOC\s*\d*|ADE20K|Cityscapes|KITTI|ShapeNet|ModelNet|LibriSpeech|CommonVoice|AudioSet|VoxCeleb|MovieLens|Yelp|Amazon\s+Reviews|SST[-\s]?\d*)\b',
        ]

        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = match.group(1).strip() if match.group(1) else match.group(0).strip()
                name_lower = name.lower()
                if name_lower not in seen and len(name) > 2:
                    seen.add(name_lower)
                    start = max(0, match.start() - 100)
                    end = min(len(text), match.end() + 200)
                    context = text[start:end].strip()
                    datasets.append({
                        "name": name,
                        "description": context,
                        "url": "",
                        "size": "",
                        "domain": "",
                        "format": "",
                        "source_section": "",
                        "confidence": 0.7,
                    })
        return datasets

    async def _llm_extract_datasets(self, text: str, title: str) -> List[dict]:
        prompt = f"""You are a dataset extraction specialist analyzing a research paper.

Paper title: {title}

Extract ALL datasets mentioned in this paper. For each dataset, provide:
- name
- description
- url
- size
- domain
- format
- source_section
- usage

Paper text:
{text[:12000]}

Return a JSON object:
{{
    "datasets": [
        {{
            "name": "Dataset Name",
            "description": "What it contains",
            "url": "https://...",
            "size": "50K samples",
            "domain": "Computer Vision",
            "format": "Images",
            "source_section": "Experiments",
            "usage": "evaluation"
        }}
    ]
}}

Return ONLY valid JSON. If none, return {{"datasets": []}}"""
        result = await self.llm.call_text_json(prompt)
        return result.get("datasets", [])

    def _merge_datasets(self, regex_ds: List[dict], llm_ds: List[dict]) -> List[dict]:
        merged = {}

        for ds in llm_ds:
            name = ds.get("name", "").strip()
            if name:
                key = re.sub(r'[^a-z0-9]', '', name.lower())
                merged[key] = ds

        for ds in regex_ds:
            name = ds.get("name", "").strip()
            if name:
                key = re.sub(r'[^a-z0-9]', '', name.lower())
                if key not in merged:
                    merged[key] = ds
                else:
                    for field in ["url", "size", "domain", "format"]:
                        if not merged[key].get(field) and ds.get(field):
                            merged[key][field] = ds[field]
        return list(merged.values())

    def _add_page_numbers(self, datasets: List[dict], pages: List[dict]) -> List[dict]:
        for ds in datasets:
            name = ds.get("name", "")
            for page in pages:
                if name.lower() in page["text"].lower():
                    ds["page_number"] = page["page_number"]
                    break
        return datasets

    def _get_parsed_pages(self, paper: dict) -> dict:
        pdf_url = paper.get("pdf_url", "")
        if pdf_url:
            parsed = self.pdf_parser.parse_from_pdf_url(pdf_url)
            if parsed.get("pages"):
                return parsed
        text = paper.get("full_text", "") or paper.get("abstract", "")
        if text:
            return self.pdf_parser.parse_from_text(text)
        return {"pages": [], "sections": [], "visual_items": []}