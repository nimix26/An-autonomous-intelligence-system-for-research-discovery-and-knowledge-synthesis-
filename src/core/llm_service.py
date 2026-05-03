"""
core/llm_service.py — LLM Service with robust DeepSeek-R1 think-tag handling.
Preserves latest fixes + uses env/config everywhere (no hardcoded model/url names).
"""

import json
import logging
import re
import asyncio
import httpx
from core.config import Config

logger = logging.getLogger(__name__)


def _required(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required env variable: {name}")
    return value


API_CONFIGS = {
    "text": {
        "key":    Config.TEXT_API_KEY,
        "url":    _required("TEXT_BASE_URL",      Config.TEXT_BASE_URL),
        "model":  _required("TEXT_MODEL",          Config.TEXT_MODEL),
        "system": "You are an expert research paper analyst. Return ONLY valid JSON.",
    },
    "discovery": {
        "key":    Config.DISCOVERY_API_KEY,
        "url":    _required("DISCOVERY_BASE_URL",  Config.DISCOVERY_BASE_URL),
        "model":  _required("DISCOVERY_MODEL",     Config.DISCOVERY_MODEL),
        "system": (
            "You are an expert research librarian. "
            "Think in <think> tags, then output ONLY valid JSON."
        ),
    },
    "judge": {
        "key":    Config.JUDGE_API_KEY,
        "url":    _required("JUDGE_BASE_URL",      Config.JUDGE_BASE_URL),
        "model":  _required("JUDGE_MODEL",         Config.JUDGE_MODEL),
        "system": (
            "You are a strict research-paper relevance judge. "
            "Think in <think> tags, then output ONLY valid JSON."
        ),
    },
    "code": {
        "key":    Config.CODE_API_KEY,
        "url":    _required("CODE_BASE_URL",       Config.CODE_BASE_URL),
        "model":  _required("CODE_MODEL",          Config.CODE_MODEL),
        "system": (
            "You are an expert code architect. "
            "Think in <think> tags, then output ONLY valid JSON."
        ),
    },
    "image": {
        "key":    Config.IMAGE_API_KEY,
        "url":    _required("IMAGE_BASE_URL",      Config.IMAGE_BASE_URL),
        "model":  _required("IMAGE_MODEL",         Config.IMAGE_MODEL),
        "system": "You are an expert at describing figures. Return ONLY valid JSON.",
    },
    "graph": {
        "key":    Config.GRAPH_API_KEY,
        "url":    _required("GRAPH_BASE_URL",      Config.GRAPH_BASE_URL),
        "model":  _required("GRAPH_MODEL",         Config.GRAPH_MODEL),
        "system": "You are an expert at describing graphs. Return ONLY valid JSON.",
    },
    "equation": {
        "key":    Config.EQUATION_API_KEY,
        "url":    _required("EQUATION_BASE_URL",   Config.EQUATION_BASE_URL),
        "model":  _required("EQUATION_MODEL",      Config.EQUATION_MODEL),
        "system": "You are an expert at describing equations. Return ONLY valid JSON.",
    },
}


class LLMService:
    def __init__(self):
        self.configs = API_CONFIGS

    # ── Raw API call ──────────────────────────────────────────────────

    async def _call_api(
        self,
        config_name: str,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 5,
    ) -> str:
        cfg = self.configs.get(config_name)
        if not cfg:
            raise RuntimeError(f"Unknown config_name: {config_name}")
        if not cfg["key"]:
            raise RuntimeError(f"Missing API key for '{config_name}' in env")

        url = f"{cfg['url'].rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type":  "application/json",
        }
        payload = {
            "model":       cfg["model"],
            "messages":    [
                {"role": "system", "content": cfg["system"]},
                {"role": "user",   "content": prompt},
            ],
            "temperature": temperature,
            "top_p":       0.9,
            "max_tokens":  max_tokens,
        }

        last_err = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)

                    if resp.status_code == 429:
                        # Respect Retry-After header if present
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait = min(float(retry_after), 60)
                            except (ValueError, TypeError):
                                wait = min(3 * (2 ** attempt), 30)
                        else:
                            wait = min(3 * (2 ** attempt), 30)
                        # Add jitter to prevent thundering herd
                        import random
                        wait += random.uniform(0.5, 2.0)
                        logger.warning(f"   ⏳ Rate-limited ({config_name}), retry {attempt+1}/{max_retries} in {wait:.1f}s")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code >= 500:
                        wait = 2 ** attempt
                        logger.warning(f"   ⚠️ Server {resp.status_code} ({config_name}), retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code != 200:
                        raise RuntimeError(f"API {resp.status_code}: {resp.text[:300]}")

                    data    = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise RuntimeError("No choices in response")

                    msg  = choices[0].get("message", {})
                    text = msg.get("content", "") or ""

                    if not text.strip():
                        reasoning = msg.get("reasoning_content", "") or ""
                        if reasoning.strip():
                            logger.debug(f"   [{config_name}] content empty, using reasoning_content ({len(reasoning)} chars)")
                            text = reasoning
                        else:
                            msg_keys = list(msg.keys()) if isinstance(msg, dict) else str(type(msg))
                            logger.warning(f"   [{config_name}] Empty content. Message keys: {msg_keys}, finish_reason: {choices[0].get('finish_reason')}")
                            raise RuntimeError("Empty response content")

                    if not text or not text.strip():
                        raise RuntimeError("Empty response content")
                    return text

            except (httpx.TimeoutException, httpx.ConnectError, asyncio.CancelledError) as e:
                last_err = e
                wait = 2 ** attempt
                logger.warning(f"   ⏳ {type(e).__name__} ({config_name}), retry {attempt+1}/{max_retries} in {wait}s")
                await asyncio.sleep(wait)
            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                logger.warning(f"   ⚠️ {type(e).__name__} ({config_name}), retry {attempt+1}/{max_retries} in {wait}s: {str(e)[:100]}")
                await asyncio.sleep(wait)

        raise RuntimeError(f"API {config_name} failed after {max_retries} retries: {last_err}")

    # ── JSON extraction helpers ───────────────────────────────────────

    @staticmethod
    def _find_json_at(text: str, start: int):
        if start >= len(text):
            return None
        open_ch = text[start]
        if open_ch == "{":
            close_ch = "}"
        elif open_ch == "[":
            close_ch = "]"
        else:
            return None

        depth     = 0
        in_string = False
        escape    = False

        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    @staticmethod
    def _strip_think_tags(raw: str) -> str:
        if not raw or not raw.strip():
            return raw or ""

        text = raw.strip()

        close_pattern = re.compile(r"</think\s*>", re.IGNORECASE)
        matches = list(close_pattern.finditer(text))
        if matches:
            after = text[matches[-1].end():].strip()
            if after:
                after = re.sub(r"^```(?:json)?\s*", "", after)
                after = re.sub(r"\s*```\s*$",        "", after)
                return after.strip()

        cleaned = re.sub(
            r"<think(?:ing)?\s*>.*?</think(?:ing)?\s*>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        if cleaned:
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```\s*$",        "", cleaned)
            return cleaned.strip()

        open_match = re.search(r"<think(?:ing)?\s*>", text, re.IGNORECASE)
        if open_match:
            for i, ch in enumerate(text):
                if ch in ("{", "["):
                    obj = LLMService._find_json_at(text, i)
                    if obj:
                        return obj

        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$",        "", text)
        return text.strip()

    @staticmethod
    def _extract_json(raw: str):
        if not raw or not raw.strip():
            return None

        cleaned = LLMService._strip_think_tags(raw)
        if not cleaned:
            return None

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        for i, ch in enumerate(cleaned):
            if ch in ("{", "["):
                obj_str = LLMService._find_json_at(cleaned, i)
                if obj_str:
                    try:
                        return json.loads(obj_str)
                    except json.JSONDecodeError:
                        pass
                break

        for i, ch in enumerate(raw):
            if ch in ("{", "["):
                obj_str = LLMService._find_json_at(raw, i)
                if obj_str:
                    try:
                        return json.loads(obj_str)
                    except json.JSONDecodeError:
                        pass
                break

        return None

    @staticmethod
    def _is_placeholder(s: str) -> bool:
        low = s.lower().strip()
        bad_patterns = [
            r"^(exact|real|actual|sample|example)\s+(paper|title)",
            r"^paper\s*(title)?\s*\d",
            r"^title\s*\d",
            r"^keyword\s*\d",
            r"^term\s*\d",
            r"^step\s*\d",
            r"^\[",
            r"^use style",
            r"^insert",
            r"^your\s+(paper|keyword|title)",
            r"^placeholder",
        ]
        return any(re.search(pat, low) for pat in bad_patterns)

    @staticmethod
    def _extract_string_list(raw: str, key_hints: list[str] = None) -> list[str]:
        if not raw:
            return []

        cleaned = LLMService._strip_think_tags(raw)
        parsed  = LLMService._extract_json(raw)

        if parsed is not None:
            items = []
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                hints = key_hints or ["papers", "names", "paper_names", "titles", "keywords", "terms", "suggestions"]
                for k in hints:
                    if isinstance(parsed.get(k), list):
                        items = parsed[k]
                        break
                if not items:
                    for v in parsed.values():
                        if isinstance(v, list) and v:
                            items = v
                            break

            out = []
            for item in items:
                s = str(item).strip().strip('"').strip("'").strip()
                if s and len(s) > 2 and not LLMService._is_placeholder(s):
                    out.append(s)
            if out:
                return out

        quotes = re.findall(r'"([^"]{5,})"', cleaned or raw)
        out    = [q.strip() for q in quotes if len(q.strip()) > 5 and not LLMService._is_placeholder(q)]
        if out:
            return out

        lines = (cleaned or raw).split("\n")
        out   = []
        for line in lines:
            line = line.strip()
            line = re.sub(r"^[\d]+[.)]\s*", "", line)
            line = re.sub(r"^[-*•]\s*",     "", line)
            line = line.strip().strip('"').strip("'").strip()
            if (line and len(line) > 5
                    and not LLMService._is_placeholder(line)
                    and not line.startswith("<")
                    and not line.startswith("{")):
                out.append(line)
        return out

    # ── Convenience callers for each config ───────────────────────────

    async def call_text(self, prompt: str, **kwargs) -> str:
        raw = await self._call_api("text", prompt, **kwargs)
        return self._strip_think_tags(raw)

    async def call_text_json(self, prompt: str, **kwargs) -> dict:
        raw    = await self._call_api("text", prompt, **kwargs)
        parsed = self._extract_json(raw)
        return parsed if isinstance(parsed, dict) else {}

    async def call_image(self, prompt: str, **kwargs) -> str:
        raw = await self._call_api("image", prompt, **kwargs)
        return self._strip_think_tags(raw)

    async def call_image_json(self, prompt: str, **kwargs) -> dict:
        raw    = await self._call_api("image", prompt, **kwargs)
        parsed = self._extract_json(raw)
        return parsed if isinstance(parsed, dict) else {}

    async def call_image_with_base64(self, prompt: str, image_b64: str, mime_type: str) -> str:
        try:
            return await self.call_image(f"{prompt}\n[Image provided as base64 — {mime_type}]")
        except Exception as e:
            logger.debug(f"Image-with-base64 fallback: {e}")
            return ""

    async def call_graph(self, prompt: str, **kwargs) -> str:
        raw = await self._call_api("graph", prompt, **kwargs)
        return self._strip_think_tags(raw)

    async def call_graph_json(self, prompt: str, **kwargs) -> dict:
        raw    = await self._call_api("graph", prompt, **kwargs)
        parsed = self._extract_json(raw)
        return parsed if isinstance(parsed, dict) else {}

    async def call_equation(self, prompt: str, **kwargs) -> str:
        raw = await self._call_api("equation", prompt, **kwargs)
        return self._strip_think_tags(raw)

    async def call_equation_json(self, prompt: str, **kwargs) -> dict:
        raw    = await self._call_api("equation", prompt, **kwargs)
        parsed = self._extract_json(raw)
        return parsed if isinstance(parsed, dict) else {}

    # ── Discovery helpers ─────────────────────────────────────────────

    async def suggest_paper_names(self, topic: str, context: str = "") -> list[str]:
        prompt = f"""You are an expert research librarian.

Suggest exactly 3 REAL, published paper titles for:
TOPIC: "{topic}"
CONTEXT: {context or "general researcher"}

Rules:
- exact full titles of REAL published papers
- no fake or fabricated titles
- prefer foundational/high-citation papers that best represent the topic
- these papers will be used as seeds to find more related research
- for broad topics, cover distinct major schools, paradigms, or model families
  within the user's field/context rather than one narrow sub-area
- output JSON only

JSON:
{{"papers":["title1","title2","title3"]}}"""

        raw   = await self._call_api("discovery", prompt, temperature=0.2, max_tokens=2048)
        names = self._extract_string_list(raw, key_hints=["papers", "names", "titles"])
        valid = [n for n in names if len(n) > 10 and not n.lower().startswith(("step ", "note:", "here "))]
        logger.info(f"   Extracted {len(valid)} seed paper names: {[n[:60] for n in valid[:3]]}")
        return valid[:3]

    async def analyze_seed_papers(self, topic: str, seed_papers: list[dict]) -> dict:
        papers_text = ""
        for i, p in enumerate(seed_papers, 1):
            title    = (p.get("title",    "") or "")[:200]
            abstract = (p.get("abstract", "") or "")
            year     = p.get("year", "?")
            cites    = p.get("citation_count", 0) or 0
            papers_text += f"\n--- Paper {i} ---\n"
            papers_text += f'Title: "{title}" ({year}, {cites} citations)\n'
            papers_text += f"Abstract: {abstract}\n"

        prompt = f"""You are analyzing {len(seed_papers)} research papers on the topic: "{topic}"

{papers_text}

Analyze these papers thoroughly and identify:
1. The CORE technical concepts and methods shared across them
2. The specific research problem they address
3. Key technical terminology and vocabulary
4. The research sub-area or domain

Return JSON:
{{
    "core_concepts":    ["concept1", "concept2", ...],
    "shared_methods":   ["method1",  "method2",  ...],
    "key_terminology":  ["term1",    "term2",    ...],
    "research_domain":  "specific sub-domain",
    "analysis_summary": "Brief 2-3 sentence analysis"
}}

Return ONLY valid JSON."""

        try:
            raw    = await self._call_api("discovery", prompt, temperature=0.2, max_tokens=2048)
            parsed = self._extract_json(raw)
            if parsed and isinstance(parsed, dict):
                logger.info(f"   [SeedAnalysis] Core concepts: {parsed.get('core_concepts', [])[:5]}")
                logger.info(f"   [SeedAnalysis] Domain: {parsed.get('research_domain', 'unknown')}")
                return parsed
        except Exception as e:
            logger.warning(f"   [SeedAnalysis] Failed: {e}")

        return {
            "core_concepts":    [],
            "shared_methods":   [],
            "key_terminology":  [],
            "research_domain":  "",
            "analysis_summary": "",
        }

    async def generate_keywords(self, topic: str, papers_metadata: list[dict], user_field: str = "") -> tuple:
        logger.info(f"   [generate_keywords] Using API config: 'discovery' (DISCOVERY_MODEL)")

        papers_text = ""
        for i, p in enumerate(papers_metadata[:10], 1):
            title    = p.get("title", "?")
            abstract = (p.get("abstract", "") or "")[:300]
            year     = p.get("year", "?")
            cites    = p.get("citation_count", 0) or 0
            papers_text += f'\n{i}. "{title}" ({year}, {cites} cites)\n'
            if abstract:
                papers_text += f"   Abstract snippet: {abstract}\n"

        field_clause = ""
        if user_field:
            field_clause = f"""
USER'S FIELD OF STUDY: "{user_field}"
• ALL keywords MUST belong to or be relevant within "{user_field}".
• Do NOT generate keywords from other fields.
• Set every keyword's "field" value to "{user_field}" or a sub-field of it."""

        prompt = f"""Generate search keywords for finding academic papers.

TOPIC: "{topic}"{field_clause}

REFERENCE PAPERS:
{papers_text}

Generate 5-8 technical search terms. Each should be:
- Specific enough to filter out unrelated papers
- 1-4 words
- The kind of terms found in a paper's "Keywords" section

Return ONLY JSON:
{{"keywords":[{{"keyword":"self-attention","field":"deep learning"}}]}}"""

        raw    = await self._call_api("discovery", prompt, temperature=0.3, max_tokens=2048)
        parsed = self._extract_json(raw)

        keyword_field_pairs = []
        global_field        = user_field

        if parsed and isinstance(parsed, dict):
            kw_list = parsed.get("keywords", [])
            if isinstance(kw_list, list):
                for item in kw_list:
                    if isinstance(item, dict):
                        kw    = (item.get("keyword", "") or "").strip()
                        field = (item.get("field",   "") or item.get("field_of_study", "") or "").strip()
                        if user_field:
                            field = user_field
                        if kw and len(kw) >= 3 and len(kw) <= 60:
                            keyword_field_pairs.append({"keyword": kw, "field": field})
                            if not global_field and field:
                                global_field = field
                    elif isinstance(item, str):
                        kw = item.strip()
                        if kw and len(kw) >= 3 and len(kw) <= 60:
                            keyword_field_pairs.append({"keyword": kw, "field": user_field or ""})

            if not global_field:
                global_field = parsed.get("field_of_study", "") or ""

        topic_lower       = topic.lower().strip()
        off_topic_domains = self._detect_off_topic_domains(topic_lower)

        filtered = []
        for pair in keyword_field_pairs:
            kw       = pair["keyword"]
            kw_lower = kw.lower().strip()
            if kw_lower == topic_lower:
                continue
            if re.match(r"^(step|note|here|the |a |an )", kw_lower):
                continue
            if any(w in kw_lower for w in ["extract", "identify", "paper title", "for example", "such as"]):
                continue
            if kw_lower in {"model", "method", "approach", "framework", "system", "analysis",
                            "technique", "algorithm", "network", "learning", "training", "data", "results"}:
                continue

            blocked = False
            for domain, blocklist in off_topic_domains.items():
                if any(term in kw_lower for term in blocklist):
                    logger.info(f"   🚫 Blocked keyword '{kw}' — off-topic domain '{domain}'")
                    blocked = True
                    break

            if not blocked:
                filtered.append(pair)

        if not filtered:
            words    = topic.split()
            filtered = [{"keyword": topic, "field": global_field}]
            if len(words) >= 2:
                for w in words:
                    if len(w) >= 4:
                        filtered.append({"keyword": w, "field": global_field})

        return filtered[:8], global_field

    @staticmethod
    def _detect_off_topic_domains(topic_lower: str) -> dict:
        domain_signals = {
            "computer_vision": {
                "signals":   ["computer vision", "image", "visual", "object detection", "segmentation",
                               "image classification", "video", "opencv", "cnn for image", "yolo",
                               "resnet", "vgg", "visual recognition"],
                "blocklist": ["image segmentation", "object detection", "image classification",
                               "visual recognition", "image generation", "face recognition",
                               "scene understanding", "image captioning", "visual question",
                               "image-to-image", "super resolution", "optical flow"],
            },
            "nlp": {
                "signals":   ["nlp", "natural language", "text", "language model", "sentiment",
                               "translation", "summarization", "question answering", "ner",
                               "named entity", "parsing", "tokeniz", "word embedding"],
                "blocklist": ["text classification", "sentiment analysis", "named entity",
                               "machine translation", "text generation", "language model",
                               "word embedding", "text mining", "document classification"],
            },
            "robotics": {
                "signals":   ["robot", "manipulation", "locomotion", "autonomous", "slam",
                               "motion planning", "grasping"],
                "blocklist": ["robot control", "manipulation", "locomotion", "grasping",
                               "motion planning", "autonomous navigation"],
            },
            "biology": {
                "signals":   ["biology", "biological", "gene", "protein", "cell", "dna", "rna",
                               "genome", "organism", "evolution"],
                "blocklist": ["gene expression", "protein folding", "cell biology",
                               "dna sequencing", "genome analysis"],
            },
        }

        blocked = {}
        for domain, config in domain_signals.items():
            if not any(sig in topic_lower for sig in config["signals"]):
                blocked[domain] = config["blocklist"]
        return blocked

    # ── Scoring ───────────────────────────────────────────────────────

    async def batch_score_papers(self, topic: str, context: str, papers: list[dict]) -> list[float]:
        if not papers:
            return []

        BATCH_SIZE = 10
        all_scores = []

        for batch_start in range(0, len(papers), BATCH_SIZE):
            batch       = papers[batch_start:batch_start + BATCH_SIZE]
            batch_num   = batch_start // BATCH_SIZE + 1
            total_batches = (len(papers) + BATCH_SIZE - 1) // BATCH_SIZE
            logger.info(f"   → Judge batch {batch_num}/{total_batches} ({len(batch)} papers)...")
            scores = await self._score_batch_chunk(topic, context, batch)
            all_scores.extend(scores)

        return all_scores

    async def _score_batch_chunk(self, topic: str, context: str, papers: list[dict]) -> list[float]:
        paper_lines = []
        for i, p in enumerate(papers):
            title    = (p.get("title")    or "?")[:150]
            abstract = (p.get("abstract") or "")[:1200]
            year     = p.get("year", "?")
            cites    = p.get("citation_count", 0) or 0
            venue    = p.get("venue", "") or ""
            fields   = p.get("fields_of_study", []) or []
            fields_str = ", ".join(fields[:3]) if fields else "N/A"

            line  = f'[{i}] Title: "{title}"\n'
            line += f'    Year: {year} | Citations: {cites} | Venue: {venue or "N/A"} | Fields: {fields_str}\n'
            line += f'    Abstract: {abstract}\n' if abstract else '    Abstract: NOT AVAILABLE\n'
            paper_lines.append(line)

        prompt = f"""You are a strict research-paper relevance judge.

RESEARCH TOPIC: "{topic}"
Context: {context or "general"}

Score each paper's relevance to "{topic}". Return JSON:
{{"scores":[0.95,0.82,...]}}
Need exactly {len(papers)} scores (0.0 – 1.0).

PAPERS:
""" + "\n".join(paper_lines)

        try:
            raw    = await self._call_api("judge", prompt, temperature=0.1, max_tokens=4096)
            parsed = self._extract_json(raw)
            if parsed and isinstance(parsed, dict) and isinstance(parsed.get("scores"), list):
                arr = []
                for s in parsed["scores"]:
                    try:
                        arr.append(max(0.0, min(1.0, float(s))))
                    except Exception:
                        arr.append(0.3)
                if len(arr) < len(papers):
                    arr.extend([0.3] * (len(papers) - len(arr)))
                return arr[:len(papers)]
        except Exception as e:
            logger.warning(f"   ⚠️ batch_score_papers failed, fallback heuristic: {e}")

        return self._heuristic_score_batch(topic, papers)

    @staticmethod
    def _heuristic_score_batch(topic: str, papers: list[dict]) -> list[float]:
        import math
        topic_words = set(topic.lower().split())
        max_cites   = max((p.get("citation_count", 0) or 0 for p in papers), default=1) or 1
        top_venues  = {
            "neurips", "nips", "icml", "iclr", "cvpr", "iccv", "eccv",
            "acl", "emnlp", "naacl", "aaai", "ijcai", "nature", "science",
            "cell", "pnas", "jmlr", "tpami", "arxiv",
        }

        scores = []
        for p in papers:
            title        = (p.get("title")    or "").lower()
            abstract     = (p.get("abstract") or "").lower()
            title_words  = set(title.split())
            abstract_words = set(abstract.split())
            year   = p.get("year") or 2020
            cites  = p.get("citation_count", 0) or 0
            venue  = (p.get("venue") or "").lower()
            ref_count = p.get("reference_count", 0) or 0

            title_overlap   = len(topic_words & title_words)    / len(topic_words) if topic_words else 0.0
            abs_overlap     = len(topic_words & abstract_words) / len(topic_words) if topic_words else 0.0
            topic_in_title  = 1.0 if topic.lower() in title else 0.0
            cite_score      = min(1.0, math.log10(cites + 1) / math.log10(max_cites + 1)) if max_cites > 1 else 0.0
            venue_score     = 1.0 if any(tv in venue for tv in top_venues) else (0.5 if len(venue) > 3 else 0.1)

            score = (
                0.25 * topic_in_title +
                0.15 * title_overlap  +
                0.10 * abs_overlap    +
                0.30 * cite_score     +
                0.15 * venue_score    +
                0.05 * min(1.0, ref_count / 50.0)
            )
            scores.append(round(max(0.05, min(0.95, score)), 2))

        return scores

    # ── Chunk-level summarization ─────────────────────────────────────

    async def summarize_chunk(
        self,
        chunk_text: str,
        paper_title: str,
        chunk_info: dict,
        context: dict,
    ) -> dict:
        page_range   = chunk_info.get("page_range",       "?")
        prev_summary = chunk_info.get("previous_summary", "")

        # ── Role-based adaptation ──
        persona = (context or {}).get("persona", "Researcher") or "Researcher"
        depth   = (context or {}).get("depth",   "Understand") or "Understand"

        role_instructions = {
            "Learner": "Write for a student who is new to this field. Use simple language, explain jargon, provide intuitive analogies. Focus on the 'why' and 'what' rather than low-level math.",
            "Educator": "Write for a professor preparing teaching materials. Highlight teachable concepts, key takeaways, and pedagogical structure. Make the content suitable for a lecture.",
            "Researcher": "Write for an expert researcher. Be precise, rigorous, and technical. Include specific numbers, model architectures, loss functions, dataset details, and statistical results.",
        }
        depth_instructions = {
            "Skim": "Be thorough — 9-11 sentences focusing on the most critical points with specific details.",
            "Understand": "Be thorough — 13-20 sentences covering all key content with specific details.",
            "DeepDive": "Be exhaustive — 17-25 sentences. Cover every significant point including edge cases, ablations, and nuances.",
        }
        role_inst  = role_instructions.get(persona, role_instructions["Researcher"])
        depth_inst = depth_instructions.get(depth, depth_instructions["Understand"])

        prompt = f"""You are analyzing a research paper: "{paper_title}"
Pages: {page_range}

=== AUDIENCE ===
{role_inst}

=== DEPTH ===
{depth_inst}

{"Previous context: " + prev_summary if prev_summary else "This is the beginning of the paper."}

Text:
{chunk_text[:25000]}

Return JSON:
{{
    "summary":              "Detailed summary following the audience and depth guidelines above.",
    "key_points":           ["Detailed point with specific information — adapt to audience level"],
    "section_type":         "introduction|methodology|results|discussion|conclusion|content",
    "importance":           "high|medium|low",
    "visual_elements":      [{{"label":"Figure 1","caption":"...","explanation":"...","item_type":"figure","page_number":1}}],
    "mathematical_content": [{{"label":"Eq. (1)","caption":"...","explanation":"...","item_type":"equation","page_number":1}}],
    "graph_elements":       [{{"label":"Table 1","caption":"...","explanation":"...","item_type":"table","page_number":1}}]
}}
Return ONLY valid JSON."""

        try:
            raw    = await self._call_api("text", prompt, temperature=0.2, max_tokens=6000)
            parsed = self._extract_json(raw)
            if parsed and isinstance(parsed, dict):
                return {
                    "summary":              parsed.get("summary",              "") or "",
                    "key_points":           parsed.get("key_points",           []) or [],
                    "section_type":         parsed.get("section_type",         "content") or "content",
                    "importance":           parsed.get("importance",           "medium") or "medium",
                    "visual_elements":      parsed.get("visual_elements",      []) or [],
                    "mathematical_content": parsed.get("mathematical_content", []) or [],
                    "graph_elements":       parsed.get("graph_elements",       []) or [],
                }
        except Exception as e:
            logger.warning(f"   ⚠️ summarize_chunk failed: {e}")

        return {
            "summary": "", "key_points": [], "section_type": "content",
            "importance": "medium", "visual_elements": [],
            "mathematical_content": [], "graph_elements": [],
        }

    async def combine_summaries(
        self,
        chunk_summaries: list[dict],
        paper_title: str,
        context: dict,
    ) -> dict:
        summaries_text = ""
        for cs in chunk_summaries:
            summaries_text += f"\n[Pages {cs.get('page_range', '?')}] ({cs.get('section_type', 'content')})\n"
            summaries_text += f"Summary: {cs.get('summary', '')}\n"
            kps = cs.get("key_points", [])
            if kps:
                summaries_text += "Key points:\n" + "\n".join(f"- {kp}" for kp in kps) + "\n"

        # ── Role-based adaptation ──
        persona = (context or {}).get("persona", "Researcher") or "Researcher"
        depth   = (context or {}).get("depth",   "Understand") or "Understand"

        role_instructions = {
            "Learner": (
                "Write for a student new to this field. Use clear, accessible language. "
                "Explain technical terms when they appear. Use analogies to make complex ideas intuitive. "
                "Focus on the big picture — what problem was solved, why it matters, and what the key ideas are."
            ),
            "Educator": (
                "Write for a professor preparing teaching materials. Structure content for pedagogy — "
                "lead with context, build up concepts logically, highlight key takeaways suitable for a lecture. "
                "Include discussion-worthy points and common misconceptions to address."
            ),
            "Researcher": (
                "Write for an expert researcher in this field. Be precise and rigorous. "
                "Include specific model names, dataset names, metric values, architectural choices, "
                "training procedures, and quantitative comparisons with prior work. Do not simplify."
            ),
        }
        depth_summary_length = {
            "Skim": "15-20 sentences",
            "Understand": "25-40 sentences",
            "DeepDive": "40-55 sentences",
        }
        depth_insights_count = {
            "Skim": "6-9",
            "Understand": "10-15",
            "DeepDive": "15-22",
        }
        role_inst    = role_instructions.get(persona, role_instructions["Researcher"])
        summary_len  = depth_summary_length.get(depth, "20-35 sentences")
        insight_ct   = depth_insights_count.get(depth, "8-12")

        prompt = f"""Synthesize a complete, detailed analysis of: "{paper_title}"

=== AUDIENCE ===
{role_inst}

{summaries_text}

Produce a thorough, well-structured analysis adapted to the audience above.

=== FORMATTING RULES ===
You MUST structure each text field using markdown formatting:
- Use ## headings to separate major sections (e.g., ## Motivation, ## Proposed Approach, ## Key Contributions, ## Experimental Results, ## Conclusion)
- Under each heading, write 2-4 sentences of explanation as a paragraph
- Use bullet points (- ) for listing specific details, metrics, comparisons, or technical points
- Separate sections with a blank line (\n\n)
- The summary MUST feel structured and scannable — NOT a wall of text

Return JSON:
{{
    "summary":     "A comprehensive, well-structured summary of {summary_len}. Use ## headings for sections like Motivation, Problem Statement, Proposed Approach, Key Contributions, Experimental Results, Comparisons with Prior Work, and Conclusion. Under each heading write a short explanatory paragraph followed by bullet points listing specific details. Separate sections with newlines. Adapt language and depth to the audience.",
    "key_insights":["Provide {insight_ct} detailed insights with specific evidence from the paper"],
    "methodology": "13-20 sentence detailed methodology description. Use ### sub-headings for Architecture, Training Procedure, and Evaluation Protocol. Use bullet points for specific technical details.",
    "results":     "13-20 sentence detailed results. Use ### sub-headings like Main Findings, Quantitative Results, and Comparison with Baselines. Use bullet points for specific metric values.",
    "limitations": "10-15 sentence description. Use ### sub-headings like Current Limitations, Assumptions, and Future Directions. Use bullet points for each specific limitation or future direction."
}}
Return ONLY valid JSON."""

        try:
            raw    = await self._call_api("text", prompt, temperature=0.2, max_tokens=8192)
            parsed = self._extract_json(raw)
            if parsed and isinstance(parsed, dict):
                return {
                    "summary":      parsed.get("summary",      "") or "",
                    "key_insights": parsed.get("key_insights", []) or [],
                    "methodology":  parsed.get("methodology",  "") or "",
                    "results":      parsed.get("results",      "") or "",
                    "limitations":  parsed.get("limitations",  "") or "",
                }
        except Exception as e:
            logger.warning(f"   ⚠️ combine_summaries failed: {e}")

        combined = " ".join(cs.get("summary", "") for cs in chunk_summaries if cs.get("summary"))
        all_kps  = []
        for cs in chunk_summaries:
            all_kps.extend(cs.get("key_points", []))

        return {
            "summary": combined, "key_insights": all_kps[:5],
            "methodology": "", "results": "", "limitations": "",
        }

    async def group_visual_elements(
        self,
        visuals:   list[dict],
        equations: list[dict],
        graphs:    list[dict],
        paper_title: str = "",
        context: dict = None,
    ) -> list[dict]:
        all_items = visuals + equations + graphs
        if not all_items:
            return []

        groups = []
        if visuals:
            groups.append({
                "group_id": "figure_group_0", "group_type": "figures",
                "group_label": "Figures & Diagrams",
                "group_summary": f"{len(visuals)} figure(s) found in the paper",
                "items": visuals, "item_count": len(visuals),
            })
        if equations:
            groups.append({
                "group_id": "eq_group_0", "group_type": "equations",
                "group_label": "Mathematical Formulations",
                "group_summary": f"{len(equations)} equation(s) found in the paper",
                "items": equations, "item_count": len(equations),
            })
        if graphs:
            groups.append({
                "group_id": "table_group_0", "group_type": "tables",
                "group_label": "Tables & Charts",
                "group_summary": f"{len(graphs)} table(s)/chart(s) found in the paper",
                "items": graphs, "item_count": len(graphs),
            })

        return groups

    # ── Stage 1: Adaptive paradigm-based seeding ──────────────────────

    async def suggest_paradigm_seeds(self, topic: str, profile) -> list[str]:
        paradigms    = getattr(profile, "paradigms",        []) or []
        target_count = getattr(profile, "target_seed_count", 4)
        domain       = getattr(profile, "primary_domain",   "") or ""

        if not paradigms:
            return await self.suggest_paper_names(topic, domain)

        paradigm_list = "\n".join(f"  - {p}" for p in paradigms)
        prompt = f"""Research topic: "{topic}"
Field: {domain}
Paradigms to cover:
{paradigm_list}

Suggest exactly {target_count} REAL, published research papers that, together,
cover these paradigms. Aim for 1-2 papers per paradigm where possible.

Rules:
- Papers MUST be real and highly cited within their field
- Do NOT invent titles
- Influence is RELATIVE to the field (a 500-cite math paper can be seminal)
- Prefer foundational or turning-point papers
- For broad topics, ensure the seed set spans distinct major schools,
  paradigms, techniques, or model families named/implied by the profile.
- Stay inside the user's field and context. Do not drift into adjacent
  fields unless the query/profile explicitly makes the topic interdisciplinary.
- Return ONLY the exact full titles

Return JSON: {{"papers": ["exact title 1", "exact title 2", ...]}}"""

        try:
            raw   = await self._call_api("discovery", prompt, temperature=0.2, max_tokens=2048)
            names = self._extract_string_list(raw, key_hints=["papers", "titles"])
            valid = [n for n in names if len(n) > 10 and not self._is_placeholder(n)]
            if valid:
                return valid[:target_count]
        except Exception as e:
            logger.warning(f"   [Stage1] suggest_paradigm_seeds failed: {e}")

        return await self.suggest_paper_names(topic, domain)

    # ── Stage 6: LLM Cross-Encoder-Style Reranker ────────────────────

    async def curate_final(
        self,
        topic: str,
        candidates: list[dict],
        seeds: list[dict],
        profile,
        target_count: int = 15,
    ) -> list[dict]:
        if not candidates:
            return []
        if len(candidates) <= target_count:
            return candidates

        paradigms    = getattr(profile, "paradigms",       []) or []
        domain       = getattr(profile, "primary_domain",  "") or ""
        temporal     = getattr(profile, "temporal_focus",  "any") or "any"
        seed_titles  = [s.get("title", "") for s in seeds if s.get("title")]

        cand_lines = []
        for i, p in enumerate(candidates):
            abstract = (p.get("abstract", "") or "").replace("\n", " ")[:180]
            channels = ",".join(p.get("_channels", []) or [])
            cand_lines.append(
                f'[{i}] "{(p.get("title", "") or "")[:110]}" '
                f'({p.get("year", "?")}, {p.get("citation_count", 0)} cites, '
                f'score={p.get("final_score", 0):.2f}, '
                f'rrf={p.get("_rrf_score", 0):.4f}, channels={channels}) '
                f'Abstract: {abstract}'
            )
        cand_block = "\n".join(cand_lines)

        prompt = f"""You are a research-paper reranker acting like a cloud
cross-encoder over query-paper pairs. Judge semantic relevance to the query
using the title, abstract, citations, rank-fusion evidence, and retrieval
channels. Do not rely on keyword overlap alone.

Field: {domain}
Query: "{topic}"
Temporal focus: {temporal}
Paradigms to cover: {paradigms}
User's seed papers: {seed_titles}

From the {len(candidates)} candidates below, select EXACTLY {target_count} paper indices
that best satisfy ALL constraints:

1. PARADIGM COVERAGE: represent every paradigm above at least once when possible.
   CRITICAL: For a broad query, prioritize paradigm DIVERSITY over high similarity 
   to a single seed. A paper that covers a missing paradigm with 5,000 citations 
   beats a paper that echoes an existing seed with 50,000 citations.
   
2. CITATION VALIDATION: Prefer papers with >500 citations when available. 
   Low-citation papers (<50) should only be included if they fill a paradigm 
   gap that no high-cite paper covers.

3. TEMPORAL BALANCE:
   - historical:     70% foundational / 30% recent
   - contemporary:   40% / 60%
   - cutting_edge:   20% / 80% (prefer last 2 years)
   - any:            50/50

4. NO REDUNDANCY: avoid near-duplicates. Two papers on the same narrow sub-topic 
   is wasteful — pick only the more influential one.
   CRITICAL DEDUP RULES:
   - Do NOT select multiple papers with the same core title/topic
     (e.g., two editions of "Cognitive Dissonance" = pick ONE, the original).
   - If two titles share >60% word overlap, they are duplicates — pick ONE.
   - Prefer the ORIGINAL/canonical publication year when duplicates exist.

5. QUALITY in FIELD-RELATIVE TERMS — judge by {domain} standards.

6. SEED HANDLING: include seeds IF genuinely relevant; omit if off-topic.

Candidates:
{cand_block}

Return JSON: {{"selected_indices": [int, int, ...]}}
Return ONLY valid JSON."""

        try:
            raw    = await self._call_api("judge", prompt, temperature=0.2, max_tokens=2048)
            parsed = self._extract_json(raw)
            if isinstance(parsed, dict):
                idxs       = parsed.get("selected_indices", []) or []
                valid_idxs = []
                for x in idxs:
                    try:
                        i = int(x)
                        if 0 <= i < len(candidates):
                            valid_idxs.append(i)
                    except (ValueError, TypeError):
                        continue
                if valid_idxs:
                    seen   = set()
                    result = []
                    for i in valid_idxs:
                        if i not in seen:
                            seen.add(i)
                            result.append(candidates[i])
                    if len(result) >= max(3, target_count // 2):
                        return result[:target_count]
        except Exception as e:
            logger.warning(f"   [Stage6] curator failed: {e}")

        # Fallback: top by final_score
        return candidates[:target_count]
