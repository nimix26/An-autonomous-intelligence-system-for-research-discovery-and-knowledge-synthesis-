"""
core/keyword_generator.py — Simplified 3-stage keyword pipeline.

Stage 1: KeyBERT extracts 10 keywords PER SEED PAPER + spaCy POS filtering
         + SentenceTransformer similarity ranking → 10 per-paper keywords
Stage 2: LLM selects best 10 search keywords from all candidates
Stage 3: Post-validation — banlist/dedupe/off-topic checks

These 10 keywords are the ONLY search terms used downstream.
No concept expansion, no alternative phrasings, no adjacent concepts.

Dependencies: keybert, sentence-transformers, spacy (en_core_web_sm)
"""

import logging
import re
import warnings

from core.config import Config

logger = logging.getLogger(__name__)

# ── Lazy-loaded models ────────────────────────────────────────────────

_nlp = None
_sim_model = None
_kw_model = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("   [Keywords] spaCy en_core_web_sm loaded ✅")
        except Exception as e:
            logger.warning(f"   [Keywords] spaCy unavailable: {e}")
            _nlp = False
    return _nlp if _nlp is not False else None


def _get_sim_model():
    global _sim_model
    if _sim_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _sim_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("   [Keywords] SentenceTransformer all-MiniLM-L6-v2 loaded ✅")
        except Exception as e:
            logger.warning(f"   [Keywords] SentenceTransformer unavailable: {e}")
            _sim_model = False
    return _sim_model if _sim_model is not False else None


def _get_kw_model():
    global _kw_model
    if _kw_model is None:
        sim = _get_sim_model()
        if sim:
            try:
                from keybert import KeyBERT
                _kw_model = KeyBERT(sim)
                logger.info("   [Keywords] KeyBERT loaded ✅")
            except Exception as e:
                logger.warning(f"   [Keywords] KeyBERT unavailable: {e}")
                _kw_model = False
        else:
            _kw_model = False
    return _kw_model if _kw_model is not False else None


# ── Banlists ──────────────────────────────────────────────────────────

BANLIST = {
    "method", "methods", "approach", "approaches", "model", "models",
    "system", "systems", "technique", "techniques", "algorithm",
    "algorithms", "network", "networks", "learning", "training", "data",
    "results", "result", "performance", "evaluation", "experiment",
    "experiments", "study", "studies", "paper", "papers", "work",
    "research", "application", "applications", "problem", "problems",
    "solution", "solutions", "process", "task", "tasks", "feature",
    "features", "representation", "representations", "architecture",
    "implementation", "strategy", "strategies", "mechanism", "mechanisms",
    "module", "modules", "component", "components", "structure",
    "information", "knowledge", "input", "output", "layer", "layers",
    "function", "functions", "set", "sets", "class", "classes",
    "state", "states", "sample", "samples", "step", "steps",
    "proposed method", "proposed approach", "proposed model",
    "existing methods", "previous work", "related work",
    "state of the art", "state-of-the-art",
}

JUNK_FRAGMENTS = {
    "psy", "neu", "cog", "bio", "soc", "com", "env", "eco",
    "phy", "che", "mat", "eng", "med", "edu", "pol", "geo",
    "art", "his", "phi", "lin", "sta", "gen", "mol", "cel",
}

MIN_KEYWORD_LENGTH = 4
TARGET_KEYWORDS_PER_PAPER = 10
TARGET_FINAL_KEYWORDS = 10


class KeywordGenerator:
    def __init__(self, llm_service=None):
        from core.llm_service import LLMService
        self.llm = llm_service or LLMService()

    async def generate(
        self,
        topic: str,
        seed_papers: list[dict],
        user_field: str = "",
    ) -> tuple[list[dict], str, dict]:
        """
        Simplified 3-stage keyword pipeline.

        Stage 1: 10 keywords per seed paper (KeyBERT + spaCy + similarity ranking)
        Stage 2: LLM picks best 10 from the combined candidate pool
        Stage 3: Post-validation

        Returns:
            (keyword_field_pairs, global_field, per_paper_keywords)
        """
        logger.info("   [Keywords] === 3-Stage Pipeline (10/paper → LLM top 10) ===")

        # ── Stage 1 ──
        per_paper_keywords, all_candidates = self._stage1_extract_per_paper(topic, seed_papers)

        total_kw = sum(len(v) for v in per_paper_keywords.values())
        logger.info(f"   [Keywords] Stage 1: {total_kw} keywords across "
                    f"{len(per_paper_keywords)} papers ({len(all_candidates)} unique candidates)")

        for paper_title, kws in per_paper_keywords.items():
            logger.info(f"      📄 '{paper_title[:50]}' → {len(kws)} keywords:")
            for kw, score in kws[:5]:
                logger.info(f"         📝 '{kw}' (sim={score:.3f})")
            if len(kws) > 5:
                logger.info(f"         ... and {len(kws) - 5} more")

        # ── Stage 2 ──
        if all_candidates:
            selected, global_field = await self._stage2_llm_filter(
                topic, all_candidates, seed_papers, per_paper_keywords, user_field
            )
        else:
            logger.warning("   [Keywords] No candidates from Stage 1, falling back to LLM-only")
            selected, global_field = await self._stage2_llm_fallback(
                topic, seed_papers, user_field
            )

        logger.info(f"   [Keywords] Stage 2: {len(selected)} keywords selected by LLM")

        # ── Stage 3 ──
        validated = self._stage3_post_validate(topic, selected, user_field)
        logger.info(f"   [Keywords] Stage 3: {len(validated)} keywords after validation")

        if not validated:
            validated = [{"keyword": topic, "field": user_field}]
            logger.warning("   [Keywords] All keywords filtered — using topic as fallback")

        if user_field:
            global_field = user_field

        for pair in validated:
            logger.info(f"   [Keywords] ✅ '{pair['keyword']}' → field: {pair.get('field', 'N/A')}")
        logger.info(f"   [Keywords] Global field: {global_field or 'not detected'}")

        return validated[:TARGET_FINAL_KEYWORDS], global_field, per_paper_keywords

    # ── Stage 1 ──────────────────────────────────────────────────────

    def _stage1_extract_per_paper(
        self, topic: str, seed_papers: list[dict]
    ) -> tuple[dict, list[tuple[str, float]]]:
        kw_model  = _get_kw_model()
        nlp       = _get_nlp()
        sim_model = _get_sim_model()

        per_paper_keywords: dict = {}
        all_seen: set = set()
        all_candidates: list = []

        for paper in seed_papers:
            title    = (paper.get("title",    "") or "").strip()
            abstract = (paper.get("abstract", "") or "").strip()

            if not title:
                continue

            text = f"{title}. {abstract}" if abstract else title
            if len(text) < 30:
                continue

            raw_phrases = []
            if kw_model:
                try:
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", category=RuntimeWarning,
                                                message=".*divide by zero.*|.*overflow.*|.*invalid value.*")
                        raw_candidates = kw_model.extract_keywords(
                            text,
                            keyphrase_ngram_range=(1, 3),
                            stop_words="english",
                            use_mmr=True,
                            diversity=0.5,
                            top_n=40,
                        )
                    raw_phrases = [c[0] for c in raw_candidates]
                except Exception as e:
                    logger.warning(f"   [Keywords] KeyBERT failed for '{title[:40]}': {e}")
                    raw_phrases = self._fallback_ngram_extraction(text)
            else:
                raw_phrases = self._fallback_ngram_extraction(text)

            if not raw_phrases:
                continue

            clean_phrases = self._spacy_pos_filter(raw_phrases, nlp)

            if len(clean_phrases) < TARGET_KEYWORDS_PER_PAPER:
                existing = set(clean_phrases)
                for p in raw_phrases:
                    p_clean = p.lower().strip()
                    if (p_clean not in existing
                            and len(p_clean) >= 4
                            and len(p_clean.split()) <= 4
                            and p_clean not in BANLIST):
                        clean_phrases.append(p_clean)
                        existing.add(p_clean)
                    if len(clean_phrases) >= 15:
                        break

            clean_phrases = list(set(clean_phrases))

            ranked = self._rank_by_similarity(topic, clean_phrases, sim_model)
            paper_kws = ranked[:TARGET_KEYWORDS_PER_PAPER]
            per_paper_keywords[title] = paper_kws

            for kw, score in paper_kws:
                if kw not in all_seen:
                    all_seen.add(kw)
                    all_candidates.append((kw, score))

        return per_paper_keywords, all_candidates

    def _spacy_pos_filter(self, phrases: list[str], nlp) -> list[str]:
        if not nlp:
            return [p.lower().strip() for p in phrases
                    if len(p) >= 4 and len(p.split()) <= 4]

        clean = []
        for phrase in phrases:
            doc = nlp(phrase)
            if not any(tok.pos_ in {"NOUN", "PROPN"} for tok in doc):
                continue
            bad_boundary = {"ADP", "VERB", "AUX", "DET", "CCONJ", "PRON"}
            if doc[0].pos_ in bad_boundary or doc[-1].pos_ in bad_boundary:
                continue
            if len(phrase) < 4 or len(phrase.split()) > 4:
                continue
            if sum(tok.is_stop for tok in doc) / len(doc) > 0.5:
                continue
            clean.append(phrase.lower().strip())

        return clean

    def _rank_by_similarity(
        self, topic: str, phrases: list[str], sim_model
    ) -> list[tuple[str, float]]:
        if not phrases:
            return []

        if sim_model:
            try:
                from sentence_transformers import util as st_util
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=RuntimeWarning,
                                            message=".*divide by zero.*|.*overflow.*|.*invalid value.*")
                    q_emb  = sim_model.encode(topic,   convert_to_tensor=True)
                    p_embs = sim_model.encode(phrases, convert_to_tensor=True)
                    scores = st_util.cos_sim(q_emb, p_embs)[0].tolist()
                scores = [0.0 if (s != s or abs(s) == float('inf')) else s for s in scores]
                return sorted(zip(phrases, scores), key=lambda x: -x[1])
            except Exception as e:
                logger.warning(f"   [Keywords] Similarity ranking failed: {e}")

        return [(p, 0.5) for p in phrases[:TARGET_KEYWORDS_PER_PAPER]]

    def _fallback_ngram_extraction(self, text: str) -> list[str]:
        words   = text.lower().split()
        phrases = set()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                ngram = " ".join(words[i:i + n])
                ngram = re.sub(r"[.,;:!?()\"]+" , "", ngram).strip()
                if len(ngram) >= 4 and ngram not in BANLIST:
                    phrases.add(ngram)
        return list(phrases)[:30]

    async def expand_concepts(
        self,
        topic: str,
        seed_papers: list[dict],
        profile,
    ) -> list[str]:
        """LLM topic expansion constrained by the profiled/selected field."""
        domain = getattr(profile, "primary_domain", "") or ""
        sub_domain = getattr(profile, "sub_domain", "") or ""
        paradigms = getattr(profile, "paradigms", []) or []
        count = Config.STAGE2A_CONCEPT_COUNT

        seed_lines = []
        for p in seed_papers[:6]:
            title = (p.get("title", "") or "")[:180]
            abstract = (p.get("abstract", "") or "")[:260]
            if title:
                seed_lines.append(f'- "{title}" | {abstract}')

        field_clause = ""
        if domain:
            field_clause = (
                f'\nSelected/profiled field: "{domain}". '
                "Expand the topic inside this field and avoid unrelated meanings from other fields."
            )

        prompt = f"""Expand this academic research topic into search concepts.

Topic: "{topic}"{field_clause}
Sub-domain: {sub_domain or "not specified"}
Profile paradigms: {paradigms}

Seed papers:
{chr(10).join(seed_lines) if seed_lines else "No seed papers available."}

Return exactly {count} concise technical concepts or alternate phrasings that would
help retrieve papers in the selected field. Use 1-5 words each. Do not include
generic academic words like method, model, paper, approach, or study.

Return ONLY JSON:
{{"concepts": ["concept 1", "concept 2", ...]}}"""

        try:
            raw = await self.llm._call_api("discovery", prompt, temperature=0.25, max_tokens=2048)
            parsed = self.llm._extract_json(raw)
            items = parsed.get("concepts", []) if isinstance(parsed, dict) else []
            concepts = []
            seen = set()
            for item in items:
                concept = str(item or "").strip()
                key = re.sub(r"[^a-z0-9]", "", concept.lower())
                if not concept or len(concept) < 3 or key in seen:
                    continue
                seen.add(key)
                concepts.append(concept)
            return concepts[:count]
        except Exception as e:
            logger.warning(f"   [Keywords] Concept expansion failed: {e}")
            return []

    # ── Stage 2 ──────────────────────────────────────────────────────

    async def _stage2_llm_filter(
        self,
        topic: str,
        all_candidates: list[tuple[str, float]],
        seed_papers: list[dict],
        per_paper_keywords: dict,
        user_field: str,
    ) -> tuple[list[dict], str]:
        per_paper_section = ""
        for paper_title, kws in per_paper_keywords.items():
            per_paper_section += f'\n  Paper: "{paper_title[:100]}"\n'
            per_paper_section += f'  Keywords: {", ".join(kw for kw, _ in kws)}\n'

        candidate_list = "\n".join(
            f'  - "{c}" (relevance score: {score:.2f})'
            for c, score in all_candidates
        )

        field_clause = ""
        if user_field:
            field_clause = f'\nUser\'s field: "{user_field}". All keywords must be relevant to this field.'

        prompt = f"""You are selecting academic search keywords from a pre-ranked list of
candidate phrases. These were extracted from {len(seed_papers)} seed research papers
using KeyBERT (keyphrase extraction) and filtered by spaCy POS analysis +
semantic similarity ranking against the topic.

RESEARCH TOPIC: "{topic}"{field_clause}

KEYWORDS EXTRACTED PER PAPER:
{per_paper_section}

ALL UNIQUE CANDIDATES (ranked by semantic similarity to topic):
{candidate_list}

YOUR TASK:
Pick exactly {TARGET_FINAL_KEYWORDS} of the BEST candidates from the list above that
would make excellent academic search queries for finding more papers about "{topic}".

SELECTION CRITERIA:
- Pick phrases that are SPECIFIC and TECHNICAL (not generic academic terms)
- Pick phrases that capture the CORE concepts of the topic
- Prefer phrases with higher relevance scores
- Each keyword should capture a DIFFERENT aspect of the research area
- ONLY pick from the candidate list above — do NOT invent new phrases
- Good keywords = ones that a researcher would type into Google Scholar

For each selected keyword, assign the most specific field of study.

Return ONLY JSON:
{{"keywords": [{{"keyword": "exact phrase from list", "field": "specific field"}}, ...],
  "field_of_study": "overall field"}}"""

        raw    = await self.llm._call_api("discovery", prompt, temperature=0.2, max_tokens=2048)
        parsed = self.llm._extract_json(raw)

        keyword_field_pairs = []
        global_field        = user_field

        if parsed and isinstance(parsed, dict):
            kw_list = parsed.get("keywords", [])
            if isinstance(kw_list, list):
                for item in kw_list:
                    if isinstance(item, dict):
                        kw    = (item.get("keyword", "") or "").strip()
                        field = (item.get("field",   "") or "").strip()
                        if user_field:
                            field = user_field
                        if kw and len(kw) >= MIN_KEYWORD_LENGTH and kw.lower() not in JUNK_FRAGMENTS:
                            keyword_field_pairs.append({"keyword": kw, "field": field})
                            if not global_field and field:
                                global_field = field
                    elif isinstance(item, str):
                        kw = item.strip()
                        if kw and len(kw) >= MIN_KEYWORD_LENGTH and kw.lower() not in JUNK_FRAGMENTS:
                            keyword_field_pairs.append({"keyword": kw, "field": user_field})

            if not global_field:
                global_field = parsed.get("field_of_study", "") or ""

        return keyword_field_pairs, global_field

    async def _stage2_llm_fallback(
        self,
        topic: str,
        seed_papers: list[dict],
        user_field: str,
    ) -> tuple[list[dict], str]:
        papers_text = ""
        for i, p in enumerate(seed_papers[:5], 1):
            title    = p.get("title", "?")
            abstract = (p.get("abstract", "") or "")[:400]
            papers_text += f'\n{i}. "{title}"\n   Abstract: {abstract}\n'

        field_clause = ""
        if user_field:
            field_clause = f'\nField: "{user_field}". Keywords must match this field.'

        prompt = f"""Generate {TARGET_FINAL_KEYWORDS} technical search keywords for finding academic papers.

TOPIC: "{topic}"{field_clause}

REFERENCE PAPERS:
{papers_text}

Generate specific, technical phrases (1-4 words each) that would find more papers
like the ones above. Avoid generic terms like "model", "method", "approach".

Return ONLY JSON:
{{"keywords": [{{"keyword": "specific phrase", "field": "field of study"}}, ...],
  "field_of_study": "overall field"}}"""

        raw    = await self.llm._call_api("discovery", prompt, temperature=0.3, max_tokens=2048)
        parsed = self.llm._extract_json(raw)

        pairs        = []
        global_field = user_field

        if parsed and isinstance(parsed, dict):
            for item in parsed.get("keywords", []):
                if isinstance(item, dict):
                    kw    = (item.get("keyword", "") or "").strip()
                    field = (item.get("field",   "") or user_field or "").strip()
                    if kw and len(kw) >= 3:
                        pairs.append({"keyword": kw, "field": field})
                        if not global_field and field:
                            global_field = field
            if not global_field:
                global_field = parsed.get("field_of_study", "") or ""

        return pairs, global_field

    # ── Stage 3 ──────────────────────────────────────────────────────

    def _stage3_post_validate(
        self,
        topic: str,
        keywords: list[dict],
        user_field: str,
    ) -> list[dict]:
        topic_lower = topic.lower().strip()
        off_topic   = self._detect_off_topic_domains(topic_lower)

        validated        = []
        seen_normalized  = set()

        for pair in keywords:
            kw       = pair.get("keyword", "").strip()
            kw_lower = kw.lower().strip()

            if kw_lower in BANLIST or kw_lower in JUNK_FRAGMENTS:
                logger.debug(f"   [Keywords] ❌ Banlist/junk: '{kw}'")
                continue

            if kw_lower == topic_lower:
                logger.debug(f"   [Keywords] ❌ Topic verbatim: '{kw}'")
                continue

            words = kw_lower.split()
            if len(kw) < MIN_KEYWORD_LENGTH or len(kw) > 60 or len(words) > 5:
                logger.debug(f"   [Keywords] ❌ Length/format: '{kw}'")
                continue

            if re.match(r"^(step|note|here|the |a |an )", kw_lower):
                continue
            if any(w in kw_lower for w in ["extract", "identify", "paper title",
                                            "for example", "such as"]):
                continue

            normalized = re.sub(r"[^a-z0-9]", "", kw_lower)
            if normalized in seen_normalized:
                logger.debug(f"   [Keywords] ❌ Duplicate: '{kw}'")
                continue

            is_substring = False
            for existing in list(seen_normalized):
                if normalized in existing or existing in normalized:
                    if len(normalized) <= len(existing):
                        is_substring = True
                        break

            if is_substring:
                logger.debug(f"   [Keywords] ❌ Substring of existing: '{kw}'")
                continue

            seen_normalized.add(normalized)

            blocked = False
            for domain, blocklist in off_topic.items():
                if any(term in kw_lower for term in blocklist):
                    logger.info(f"   [Keywords] 🚫 Off-topic '{kw}' — domain '{domain}'")
                    blocked = True
                    break

            if blocked:
                continue

            validated.append(pair)

        return validated

    @staticmethod
    def _detect_off_topic_domains(topic_lower: str) -> dict:
        return {}
