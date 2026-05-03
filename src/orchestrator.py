# orchestrator.py — FIXED VERSION
# Removes ALL hardcoded boosts, recency manipulation, and year zeroing

import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta

import numpy as np

from core.config import Config
from core.llm_service import LLMService
from core.database_searcher import DatabaseSearcher
from core.pdf_downloader import PDFDownloader
from core.chunked_processor import ChunkedProcessor
from core.scoring import PaperScorer
from core.keyword_generator import KeywordGenerator
from core.query_profiler import QueryProfiler
from core.citation_graph import CitationGraphExpander
from core.quality_filter import QualityFilter
from core.mmr_diversifier import MMRDiversifier
from core.semantic_retriever import SemanticRetriever
from core.filters import (
    filter_non_papers,
    deduplicate_papers,
    filter_invalid_metadata,
    semantic_domain_filter,
)
from models.paper import Paper, sanitize_dict

logger = logging.getLogger(__name__)

Config.ensure_dirs()


def _safe_paper_dict(p) -> dict:
    if isinstance(p, Paper):
        return p.to_dict()
    elif isinstance(p, dict):
        return sanitize_dict(p)
    return {}


def _normalize_title(title: str) -> str:
    t = (title or "").lower().strip()
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:120]


def _domain_coherent(paper: dict, profile) -> bool:
    """
    Keep retrieval field-agnostic.

    Domain coherence is handled later by semantic-domain filtering when
    embeddings are available, instead of static per-field blocklists.
    """
    return True


def _profile_search_terms(topic: str, profile) -> list[str]:
    """Generic query expansion from the LLM profile; no field-specific terms."""
    raw_terms = [
        getattr(profile, "primary_domain", "") or "",
        getattr(profile, "sub_domain", "") or "",
        *list(getattr(profile, "alternative_phrasings", []) or []),
        *list(getattr(profile, "paradigms", []) or []),
        *list(getattr(profile, "adjacent_domains", []) or []),
    ]

    terms = []
    seen = {_normalize_title(topic)}
    for term in raw_terms:
        term = (term or "").strip()
        key = _normalize_title(term)
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def _latest_date_cutoff() -> datetime:
    return datetime.now() - timedelta(days=365 * int(Config.LATEST_PAPER_YEAR_WINDOW))


def _latest_year_cutoff() -> int:
    return _latest_date_cutoff().year


def _is_latest_paper(paper: dict, cutoff_year: int) -> bool:
    cutoff_date = _latest_date_cutoff().date()
    publication_date = (paper.get("publication_date", "") or "").strip()
    if publication_date:
        try:
            return datetime.fromisoformat(publication_date[:10]).date() >= cutoff_date
        except ValueError:
            pass
    return int(paper.get("year", 0) or 0) >= cutoff_year


def _dedup_by_title_fuzzy(papers: list, threshold: float = 0.80) -> list:
    """
    Remove near-duplicate papers using word-overlap Jaccard similarity.
    Keeps the first (higher-scored) occurrence.
    """
    kept = []
    kept_tokens = []

    for p in papers:
        title = _normalize_title(p.get('title', ''))
        if not title:
            kept.append(p)
            continue
        tokens = set(title.split())
        is_dup = False
        for existing_tokens in kept_tokens:
            if not tokens or not existing_tokens:
                continue
            jaccard = len(tokens & existing_tokens) / len(tokens | existing_tokens)
            if jaccard >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(p)
            kept_tokens.append(tokens)

    return kept


def _merge_paper_metadata(base: dict, incoming: dict):
    """Keep the richest metadata when the same paper appears in many channels."""
    if (incoming.get("citation_count", 0) or 0) > (base.get("citation_count", 0) or 0):
        base["citation_count"] = incoming.get("citation_count", 0) or 0

    for field in ("abstract", "pdf_url", "doi", "arxiv_id", "venue", "paper_id", "publication_date"):
        if not base.get(field) and incoming.get(field):
            base[field] = incoming[field]

    if len(incoming.get("authors", []) or []) > len(base.get("authors", []) or []):
        base["authors"] = incoming.get("authors", []) or []


def _rrf_fuse(channel_rankings: list[tuple[str, list[dict]]], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion across retrieval channels.

    Papers found by multiple independent channels naturally rise because their
    reciprocal-rank contributions are summed.
    """
    fused: dict[str, dict] = {}

    for channel_name, papers in channel_rankings:
        for rank, paper in enumerate(papers, 1):
            key = _normalize_title(paper.get("title", ""))
            if not key or len(key) < 5:
                continue

            contribution = 1.0 / (k + rank)
            if key not in fused:
                item = dict(paper)
                item["_channels"] = [channel_name]
                item["_channel_ranks"] = {channel_name: rank}
                item["_rrf_score"] = contribution
                fused[key] = item
            else:
                item = fused[key]
                _merge_paper_metadata(item, paper)
                channels = set(item.get("_channels", []))
                channels.add(channel_name)
                item["_channels"] = sorted(channels)
                item.setdefault("_channel_ranks", {})[channel_name] = rank
                item["_rrf_score"] = item.get("_rrf_score", 0.0) + contribution

    return sorted(
        fused.values(),
        key=lambda p: (p.get("_rrf_score", 0.0), p.get("citation_count", 0) or 0),
        reverse=True,
    )


class Orchestrator:
    def __init__(self):
        self.llm             = LLMService()
        self.db              = DatabaseSearcher()
        self.pdf_downloader  = PDFDownloader()
        self.processor       = ChunkedProcessor()
        self.scorer          = PaperScorer()
        self.keyword_gen     = KeywordGenerator(llm_service=self.llm)
        # Universal pipeline components
        self.profiler        = QueryProfiler(self.llm)
        self.citation_graph  = CitationGraphExpander(
            api_key=Config.SEMANTIC_SCHOLAR_API_KEY,
            timeout=Config.STAGE2B_API_TIMEOUT,
        )
        self.semantic_retriever = SemanticRetriever()   # Stage 2C
        self.quality_filter  = QualityFilter()
        self.mmr             = MMRDiversifier()

    # ══════════════════════════════════════════════════════════════════
    # DISCOVER — 6-stage universal pipeline
    # ══════════════════════════════════════════════════════════════════

    async def discover_papers(self, ctx: dict) -> dict:
        topic       = ctx.get("topic",          "").strip()
        persona     = ctx.get("persona",        "Researcher")
        user_field  = (ctx.get("field_of_study", "") or "").strip()
        time_filter = (ctx.get("time_filter",    "relevant") or "relevant").lower().strip()

        if not topic:
            return {
                "topic": "", "papers": [], "keywords": [],
                "total_found": 0, "message": "No topic provided.",
            }

        top_n = Config.get_top_n(persona)
        logger.info("=" * 90)
        logger.info(f"🔎 DISCOVER v2 | Topic: '{topic}' | Persona: {persona} | "
                    f"Target: {top_n} | Filter: {time_filter}")
        logger.info("=" * 90)

        # ━━━ STAGE 0: Query Profiling ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("   Stage 0: Query profiling...")
        # ✅ FIX: relevance_mode is ALWAYS True (never set False)
        # This ensures weight_recency=0.0 throughout
        relevance_mode = True
        profile = await self.profiler.profile(
            topic,
            relevance_mode=relevance_mode,
            user_field=user_field,
        )
        if user_field:
            profile.primary_domain = user_field

        # ━━━ STAGE 1: Adaptive Seeding ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info(f"   Stage 1: Adaptive seeding (target: {profile.target_seed_count})...")
        seed_names = await self.llm.suggest_paradigm_seeds(topic, profile)
        logger.info(f"      → LLM suggested {len(seed_names)} seed names")

        seed_papers: list[Paper] = []
        seen_titles: set[str]    = set()

        for name in seed_names:
            try:
                paper = self.db.search_by_title(name)
                if paper and paper.title:
                    key = _normalize_title(paper.title)
                    if key and len(key) > 5 and key not in seen_titles:
                        seen_titles.add(key)
                        seed_papers.append(paper)
                        logger.info(f"      ✅ Verified: {paper.title[:60]}")
                else:
                    logger.info(f"      ❌ Not found: {name[:60]}")
            except Exception as e:
                logger.debug(f"      Seed error: {e}")
            await asyncio.sleep(Config.API_DELAY_SECONDS)

        if not seed_papers:
            logger.warning("   Stage 1: No seeds verified — fallback to pure search")
            try:
                fallback = self.db.search_papers_with_openalex(topic, limit=5)
                for p in fallback[:3]:
                    key = _normalize_title(p.title)
                    if key and key not in seen_titles:
                        seen_titles.add(key)
                        seed_papers.append(p)
            except Exception as e:
                logger.error(f"   Stage 1 fallback also failed: {e}")

        seed_dicts = [_safe_paper_dict(p) for p in seed_papers]
        logger.info(f"   Stage 1: {len(seed_papers)} seeds verified")

        # ━━━ STAGE 2A: Lexical retrieval + concept expansion ━━━━━━━━
        logger.info("   Stage 2A: Lexical retrieval + concept expansion...")
        try:
            kw_pairs, global_field, per_paper_kw = await self.keyword_gen.generate(
                topic, seed_dicts, user_field=user_field or profile.primary_domain
            )
        except Exception as e:
            logger.warning(f"   Stage 2A: keyword_gen.generate failed: {e}")
            kw_pairs      = [{"keyword": topic, "field": user_field}]
            global_field  = user_field
            per_paper_kw  = {}

        concepts: list[str] = []
        try:
            concepts = await self.keyword_gen.expand_concepts(topic, seed_dicts, profile)
        except Exception as e:
            logger.warning(f"   Stage 2A: concept expansion failed: {e}")

        logger.info(f"      Keywords: {len(kw_pairs)} | Concepts: {len(concepts)} | "
                    f"Alt phrasings: {len(profile.alternative_phrasings)}")

        # Build deduplicated search terms (keywords + concepts + alt phrasings)
        raw_terms    = (
            [kp["keyword"] for kp in kw_pairs if kp.get("keyword")]
            + concepts
            + profile.alternative_phrasings
            + profile.paradigms
            + _profile_search_terms(topic, profile)
        )
        search_terms: list[str] = []
        seen_terms:   set[str]  = set()
        for t in raw_terms:
            tl = (t or "").strip().lower()
            if tl and tl not in seen_terms:
                seen_terms.add(tl)
                search_terms.append(t)
        search_terms = search_terms[:Config.STAGE2A_MAX_SEARCH_TERMS]

        channel_a: dict[str, dict] = {}
        # ✅ FIX: Only use year_filter if time_filter == "latest"
        # For "relevant" mode, search all time (use_year_filter=False)
        use_year_filter = (time_filter == "latest")
        for term in search_terms:
            try:
                results = self.db.search_papers_with_openalex(
                    term, limit=Config.STAGE2A_PAPERS_PER_KEYWORD,
                    year_filter=use_year_filter,
                )
                for p in results:
                    d   = _safe_paper_dict(p)
                    key = _normalize_title(d.get("title", ""))
                    if not key or len(key) < 5:
                        continue
                    if key in channel_a:
                        existing = set(channel_a[key].get("_channels", []))
                        existing.add("API_SEARCH")
                        channel_a[key]["_channels"] = list(existing)
                    else:
                        d["_channels"] = ["API_SEARCH"]
                        channel_a[key] = d
            except Exception as e:
                logger.debug(f"      search '{term[:30]}' failed: {e}")
            await asyncio.sleep(Config.API_DELAY_SECONDS)

        logger.info(f"   Stage 2A: {len(channel_a)} unique papers")

        # ━━━ STAGE 2L: Exact Landmark Search ━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("   Stage 2L: Exact landmark seed channel...")
        channel_landmark: dict[str, dict] = {}
        for sd in seed_dicts:
            key = _normalize_title(sd.get("title", ""))
            if not key:
                continue
            landmark = dict(sd)
            landmark["_channels"] = ["LANDMARK"]
            landmark["_is_seed"] = True
            channel_landmark[key] = landmark
        logger.info(f"   Stage 2L: {len(channel_landmark)} exact landmark papers")

        # ━━━ STAGE 2B: Citation Graph ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("   Stage 2B: Citation graph expansion...")
        channel_b: dict[str, dict] = {}
        try:
            graph_papers = self.citation_graph.expand(
                seed_papers,
                limit_refs=Config.STAGE2B_MAX_REFS_PER_SEED,
                limit_cits=Config.STAGE2B_MAX_CITES_PER_SEED,
                limit_co_citations=Config.STAGE2B_MAX_CO_CITATIONS,
            )
            for p in graph_papers:
                d   = _safe_paper_dict(p)
                key = _normalize_title(d.get("title", ""))
                if not key or len(key) < 5:
                    continue
                if key in channel_b:
                    existing = set(channel_b[key].get("_channels", []))
                    existing.add("CITATION_GRAPH")
                    channel_b[key]["_channels"] = list(existing)
                else:
                    d["_channels"] = ["CITATION_GRAPH"]
                    channel_b[key] = d
        except Exception as e:
            logger.warning(f"   Stage 2B failed: {e}")

        logger.info(f"   Stage 2B: {len(channel_b)} unique papers")

        # ━━━ STAGE 2C: Semantic Retrieval ━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("   Stage 2C: Semantic retrieval (S2 recommendations)...")
        channel_c: dict[str, dict] = {}
        try:
            semantic_papers = self.semantic_retriever.retrieve(seed_papers)
            for p in semantic_papers:
                d   = _safe_paper_dict(p)
                key = _normalize_title(d.get("title", ""))
                if not key or len(key) < 5:
                    continue
                if key in channel_c:
                    existing = set(channel_c[key].get("_channels", []))
                    existing.add("S2_RECOMMENDATIONS")
                    channel_c[key]["_channels"] = list(existing)
                else:
                    d["_channels"] = ["S2_RECOMMENDATIONS"]
                    channel_c[key] = d
        except Exception as e:
            logger.warning(f"   Stage 2C failed: {e}")
            channel_c = {}

        logger.info(f"   Stage 2C: {len(channel_c)} unique papers")

        # ━━━ STAGE 3: RRF Rank Fusion + Filter Chain ━━━━━━━━━━━━━━━
        logger.info("   Stage 3: RRF rank fusion + filter chain...")
        pool = _rrf_fuse([
            ("LANDMARK", list(channel_landmark.values())),
            ("API_SEARCH", list(channel_a.values())),
            ("CITATION_GRAPH", list(channel_b.values())),
            ("S2_RECOMMENDATIONS", list(channel_c.values())),
        ])

        for p in pool:
            if "LANDMARK" in set(p.get("_channels", [])):
                p["_is_seed"] = True

        logger.info(f"   Stage 3: RRF-fused pool = {len(pool)} papers")

        # ✅ FIX: REMOVED hardcoded year zeroing
        # Never manipulate year data based on citation count or any heuristic
        # Keep all metadata as-is from the source
        
        # Idempotency guard: mark this pool as stage3-processed
        if any(p.get("_stage3_done") for p in pool):
            logger.warning("   Stage 3: Pool already filtered — skipping duplicate pass")
        else:
            # Filter chain, applied ONCE, in order:
            before = len(pool)
            pool = filter_non_papers(pool)                    # Fix 2+5 doc-type
            logger.info(f"   Stage 3a: Doc-type filter: {before} → {len(pool)}")

            before = len(pool)
            pool = filter_invalid_metadata(pool)              # Fix 3 year=0
            logger.info(f"   Stage 3b: Metadata filter: {before} → {len(pool)}")

            before = len(pool)
            pool = deduplicate_papers(pool)                   # Fix 4 Roman numerals
            logger.info(f"   Stage 3c: Fingerprint dedup: {before} → {len(pool)}")

            before = len(pool)
            pool = [p for p in pool if _domain_coherent(p, profile)]
            logger.info(f"   Stage 3d: Keyword domain filter: {before} → {len(pool)}")

            if time_filter == "latest":
                cutoff_year = _latest_year_cutoff()
                before = len(pool)
                pool = [p for p in pool if _is_latest_paper(p, cutoff_year)]
                logger.info(
                    f"   Stage 3e: Latest filter: {before} → {len(pool)} "
                    f"(year >= {cutoff_year})"
                )

            # ✅ FIX: REMOVED the hardcoded suspect-reprint detection
            # No longer zero year data. Trust source metadata.
            
            # Mark pool so we can detect accidental re-entry
            for p in pool:
                p["_stage3_done"] = True

        filtered = pool
        logger.info(
            f"   Stage 3: Soft-score mode keeps {len(filtered)} papers; "
            "citation/venue quality is handled by Stage 4 downranking"
        )

        if not filtered:
            return {
                "topic":          topic,
                "papers":         [],
                "keywords":       [kp.get("keyword", "") for kp in kw_pairs],
                "keyword_fields": kw_pairs,
                "field_of_study": profile.primary_domain,
                "profile":        profile.to_dict(),
                "total_found":    0,
                "message":        "No papers remained after retrieval filtering.",
            }

        # ━━━ STAGE 4: Multi-Signal Scoring (SPECTER) ━━━━━━━━━━━━━━━
        logger.info(f"   Stage 4: Scoring {len(filtered)} papers...")
        q_emb      = None
        s_embs     = None
        p_embs     = None
        specter_ok = False

        try:
            from core import specter_ranker
            if specter_ranker.is_available():
                p_embs = specter_ranker.embed_papers(filtered)
                q_emb = specter_ranker.embed_multi_anchor(
                    query=topic,
                    seeds=seed_dicts,
                    alternative_phrasings=profile.alternative_phrasings,
                    concepts=concepts,
                    domain=profile.primary_domain,
                )

                if seed_dicts:
                    s_embs = specter_ranker.embed_papers(seed_dicts)

                specter_ok = True
                logger.info(
                    f"      SPECTER embeddings: pool={p_embs.shape}, "
                    f"query={q_emb.shape}, "
                    f"seeds={s_embs.shape if s_embs is not None else None}"
                )

                # ── Semantic domain coherence filter ──
                seed_title_list = [sd.get("title", "") for sd in seed_dicts]
                filtered_before = len(filtered)
                filtered, p_embs = semantic_domain_filter(
                    papers=filtered,
                    paper_embeddings=p_embs,
                    domain=profile.primary_domain,
                    seed_titles=seed_title_list,
                )
                if len(filtered) < filtered_before:
                    logger.info(f"   Stage 4: Semantic domain filter: "
                                f"{filtered_before} → {len(filtered)}")
            else:
                logger.info("      SPECTER unavailable — scoring without embeddings")
        except Exception as e:
            logger.warning(f"   Stage 4: SPECTER failed: {e}")
            specter_ok = False
            p_embs     = None

        for i, p in enumerate(filtered):
            p["_orig_idx"] = i

        # ✅ FIX: profile.weight_recency is ALWAYS 0.0 in relevance_mode
        # No recency boost anywhere
        scored = self.scorer.score_pool(
            papers=filtered,
            profile=profile,
            query_embedding=q_emb,
            seed_embeddings=s_embs,
            paper_embeddings=p_embs,
        )

        top_for_mmr = scored[:Config.STAGE4_TOP_FOR_MMR]

        # ━━━ STAGE 5: MMR Diversification ━━━━━━━━━
        logger.info(f"   Stage 5: MMR diversification (λ={profile.mmr_lambda:.2f})...")
        diverse_k = min(Config.STAGE5_MMR_POOL_SIZE, len(top_for_mmr))

        if specter_ok and p_embs is not None and p_embs.shape[0] == len(filtered):
            orig_indices  = [p["_orig_idx"] for p in top_for_mmr]
            aligned_embs  = p_embs[orig_indices]

            mmr_indices  = self.mmr.diversify(
                papers=top_for_mmr,
                embeddings=aligned_embs,
                k=diverse_k,
                lambda_param=profile.mmr_lambda,
            )
            diverse_pool = [top_for_mmr[i] for i in mmr_indices]
        else:
            diverse_pool = top_for_mmr[:diverse_k]
            logger.info("      MMR skipped (no embeddings); using score order")

        for p in diverse_pool:
            p.pop("_orig_idx", None)

        # ━━━ STAGE 6: LLM Cross-Encoder-Style Reranker ━━━━━━━━━━━━
        logger.info(f"   Stage 6: LLM cross-encoder-style reranker selecting {top_n}...")
        final_papers = await self.llm.curate_final(
            topic=topic,
            candidates=diverse_pool,
            seeds=seed_dicts,
            profile=profile,
            target_count=top_n,
        )

        if not final_papers:
            final_papers = diverse_pool[:top_n]

        # Fuzzy title dedup — remove near-duplicate selections
        before_dedup = len(final_papers)
        final_papers = _dedup_by_title_fuzzy(final_papers, threshold=0.80)
        if len(final_papers) < before_dedup:
            logger.info(f"   Stage 6: Fuzzy dedup removed {before_dedup - len(final_papers)} duplicates")
            # Backfill from diverse_pool if we lost papers
            if len(final_papers) < top_n:
                existing_titles = {_normalize_title(p.get('title', '')) for p in final_papers}
                for p in diverse_pool:
                    if len(final_papers) >= top_n:
                        break
                    key = _normalize_title(p.get('title', ''))
                    if key and key not in existing_titles:
                        final_papers.append(p)
                        existing_titles.add(key)
                final_papers = _dedup_by_title_fuzzy(final_papers, threshold=0.80)[:top_n]

        # ✅ FIX: time_filter handling is CLEAN and EXPLICIT
        if time_filter == "latest":
            year_cutoff = _latest_year_cutoff()

            logger.info(f"   [TimeFilter] 'latest' mode: keeping papers from {year_cutoff} onwards")

            recent_final = [
                p for p in final_papers
                if _is_latest_paper(p, year_cutoff)
            ]

            if len(recent_final) < top_n:
                needed = top_n - len(recent_final)
                existing_titles = {_normalize_title(p.get("title", "")) for p in recent_final}

                backfill_candidates = sorted(
                    [
                        p for p in diverse_pool
                        if _is_latest_paper(p, year_cutoff)
                        and _normalize_title(p.get("title", "")) not in existing_titles
                    ],
                    key=lambda x: x.get("final_score", 0),
                    reverse=True,
                )

                if len(backfill_candidates) < needed:
                    existing_titles.update(_normalize_title(p.get("title", "")) for p in backfill_candidates)
                    extra_from_pool = sorted(
                        [
                            p for p in filtered
                            if _is_latest_paper(p, year_cutoff)
                            and _normalize_title(p.get("title", "")) not in existing_titles
                        ],
                        key=lambda x: x.get("final_score", 0) if "final_score" in x else (x.get("citation_count", 0) or 0),
                        reverse=True,
                    )
                    backfill_candidates = backfill_candidates + extra_from_pool

                recent_final = recent_final + backfill_candidates[:needed]
                logger.info(
                    f"   [TimeFilter] Backfilled {min(needed, len(backfill_candidates))} recent papers "
                    f"from score-ranked pool"
                )

            final_papers = recent_final[:top_n]
            logger.info(
                f"   [TimeFilter] Final: {len(final_papers)} papers from "
                f"configured latest window (year >= {year_cutoff})"
            )

        # ━━━ PDF Resolution ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info(f"   Resolving PDFs for {len(final_papers)} papers...")
        pdf_count = 0
        for llm_rank, p in enumerate(final_papers, 1):
            pdf_url = p.get("pdf_url", "") or ""
            if not pdf_url:
                try:
                    url = self.pdf_downloader.get_pdf_url({
                        "title":    p.get("title",    "") or "",
                        "arxiv_id": p.get("arxiv_id", "") or "",
                        "doi":      p.get("doi",      "") or "",
                        "pdf_url":  "",
                    })
                    if url:
                        p["pdf_url"] = url
                        pdf_url = url
                except Exception:
                    pass

            if pdf_url:
                p["pdf_hash"] = hashlib.md5(pdf_url.encode()).hexdigest()
                pdf_count += 1
            else:
                p["pdf_hash"] = ""

            p["is_recommended"]  = bool(p.get("_is_seed", False))
            p["relevance_score"] = round(float(p.get("final_score", 0.0)), 3)
            p["rrf_score"] = round(float(p.get("_rrf_score", 0.0)), 5)
            p["retrieval_channels"] = list(p.get("_channels", []) or [])
            p["channel_ranks"] = dict(p.get("_channel_ranks", {}) or {})
            p["ranking_signals"] = dict(p.get("signals", {}) or {})
            p["llm_rank"] = llm_rank

            for k in ["_channels", "_channel_ranks", "_rrf_score", "_is_seed", "signals", "_orig_idx", "_stage3_done"]:
                p.pop(k, None)

        logger.info("")
        logger.info("=" * 90)
        logger.info(f"   ✅ DISCOVER v2 complete: {len(final_papers)} papers ({pdf_count} with PDF)")
        logger.info(f"   Profile: domain={profile.primary_domain}, "
                    f"breadth={profile.breadth:.2f}, paradigms={len(profile.paradigms)}")
        logger.info(
            f"   Pipeline: S0→S1({len(seed_papers)})→S2L({len(channel_landmark)})"
            f"+S2A({len(channel_a)})+S2B({len(channel_b)})+S2C({len(channel_c)})"
            f"→RRF/S3({len(filtered)})→S4→"
            f"S5({len(diverse_pool)})→S6({len(final_papers)})"
        )
        logger.info("=" * 90)

        for i, p in enumerate(final_papers, 1):
            tag     = "⭐" if p.get("is_recommended") else "  "
            pdf_tag = "📄" if p.get("pdf_url") else "❌"
            logger.info(
                f"   {i:2d}. {tag} {pdf_tag} [{p.get('relevance_score', 0):.2f}] "
                f"{(p.get('title', '') or '')[:70]}"
            )
            logger.info(
                f"        Year: {p.get('year', '?')} | "
                f"Cites: {p.get('citation_count', 0) or 0:,} | "
                f"Venue: {(p.get('venue', '') or 'N/A')[:40]}"
            )
        logger.info("=" * 90)
        logger.info("")

        return {
            "topic":          topic,
            "papers":         final_papers,
            "keywords":       [kp.get("keyword", "") for kp in kw_pairs if kp.get("keyword")],
            "keyword_fields": kw_pairs,
            "field_of_study": profile.primary_domain,
            "profile":        profile.to_dict(),
            "time_filter":    time_filter,
            "pipeline_version": "rrf-softscore-llm-rerank",
            "pipeline_stages": [
                "topic_expansion",
                "seed_paper_generation",
                "keybert_keyword_generation",
                "multi_channel_retrieval",
                "rrf_rank_fusion",
                "soft_metadata_scoring",
                "specter_semantic_scoring",
                "llm_cross_encoder_style_reranking",
            ],
            "total_found":    len(final_papers),
            "message":        (
                f"Found {len(final_papers)} papers for '{topic}' "
                f"via RRF + soft scoring + LLM reranking pipeline "
                f"({'last 2 years' if time_filter == 'latest' else 'relevance-ranked'})."
            ),
        }

    async def summarize_single_paper(self, ctx: dict, paper_dict: dict) -> dict:
        topic  = ctx.get("topic", "") or ""
        title  = (paper_dict.get("title", "") or "") if isinstance(paper_dict, dict) else ""
        mode   = ctx.get("mode", "summarize") or "summarize"

        logger.info(f"📖 SUMMARIZE: '{title[:60]}'")

        pdf_url = (paper_dict.get("pdf_url", "") or "") if isinstance(paper_dict, dict) else ""
        if not pdf_url:
            try:
                p = Paper(
                    title    = title,
                    authors  = (paper_dict.get("authors", [])  or []) if isinstance(paper_dict, dict) else [],
                    abstract = (paper_dict.get("abstract", "") or "") if isinstance(paper_dict, dict) else "",
                    year     = (paper_dict.get("year",     0)  or 0)  if isinstance(paper_dict, dict) else 0,
                    doi      = (paper_dict.get("doi",      "") or "") if isinstance(paper_dict, dict) else "",
                    arxiv_id = (paper_dict.get("arxiv_id", "") or "") if isinstance(paper_dict, dict) else "",
                    pdf_url  = "",
                )
                pdf_url = self.db.search_pdf_fallback(p) or ""
            except Exception:
                pdf_url = ""

        try:
            processed = await self.processor.process_paper(
                paper=paper_dict, context=ctx, pdf_url=pdf_url
            )
        except Exception as e:
            logger.error(f"   Processing error: {e}", exc_info=True)
            processed = self.processor._empty_result(pdf_url)

        result = {
            "summary":         processed.get("summary",      "") or "",
            "key_insights":    processed.get("key_insights", []) or [],
            "methodology":     processed.get("methodology",  "") or "",
            "results":         processed.get("results",      "") or "",
            "limitations":     processed.get("limitations",  "") or "",
            "visual_groups":   processed.get("visual_groups",[]) or [],
            "title":           title,
            "authors":         (paper_dict.get("authors", []) or []) if isinstance(paper_dict, dict) else [],
            "year":            (paper_dict.get("year",    0)  or 0)  if isinstance(paper_dict, dict) else 0,
            "venue":           (paper_dict.get("venue",   "") or "") if isinstance(paper_dict, dict) else "",
            "doi":             (paper_dict.get("doi",     "") or "") if isinstance(paper_dict, dict) else "",
            "arxiv_id":        (paper_dict.get("arxiv_id","") or "") if isinstance(paper_dict, dict) else "",
            "pdf_url":         pdf_url or processed.get("pdf_url", "") or "",
            "pdf_hash":        processed.get("pdf_hash", "") or "",
            "chunk_summaries": processed.get("chunk_summaries", []) or [],
            "total_chunks":    processed.get("total_chunks",    0)  or 0,
            "pages_processed": processed.get("pages_processed", 0)  or 0,
            "papers":          [],
            "comparison":      "",
            "compared_analyses": [],
            "implementation":  {},
            "message":         "Analysis complete." if processed.get("summary") else "Could not extract full text.",
            "mode":            mode,
        }

        if not result["summary"] and isinstance(paper_dict, dict) and paper_dict.get("abstract"):
            result["summary"] = paper_dict["abstract"] or ""
            result["message"] = "PDF unavailable. Showing abstract-based summary."

        logger.info(
            f"   ✅ SUMMARIZE complete | "
            f"PDF: {'✅' if result['pdf_hash'] else '❌'} | "
            f"Chunks: {result['total_chunks']}"
        )
        return result

    async def run_pipeline(self, ctx: dict) -> dict:
        topic = ctx.get("topic", "").strip()
        mode  = ctx.get("mode",  "analyze") or "analyze"

        logger.info(f"🚀 PIPELINE: '{topic}' | Mode: {mode}")

        discover_result = await self.discover_papers(ctx)
        papers          = discover_result.get("papers", [])

        if not papers:
            return self._empty_response(topic, mode, f"No papers found for '{topic}'.")

        if mode == "compare":
            return await self.compare_selected_papers(ctx, papers[:5])
        elif mode == "implement":
            return await self.implement_with_papers(ctx, papers[:10])
        else:
            return await self.summarize_single_paper(ctx, papers[0])

    async def compare_selected_papers(self, ctx: dict, selected_papers: list) -> dict:
        topic = ctx.get("topic", "") or ""
        mode  = "compare"

        logger.info(f"   📊 Comparing {len(selected_papers)} selected papers")

        top_for_detail = selected_papers[:5]
        analyses       = []
        for paper in top_for_detail:
            try:
                result = await self.summarize_single_paper(ctx, paper)
                analyses.append(result)
            except Exception as e:
                logger.error(f"   Error processing paper: {e}")

        papers_used = []
        for a in analyses:
            papers_used.append({
                "title":   a.get("title",   ""),
                "year":    a.get("year",    0),
                "venue":   a.get("venue",   ""),
                "authors": a.get("authors", []),
            })

        paper_contributions = []
        detailed_comparison = ""
        research_gaps       = ""

        if len(analyses) >= 2:
            analyses_text = ""
            for i, a in enumerate(analyses, 1):
                analyses_text += f'\n--- Paper {i}: "{a.get("title", "")}" ---\n'
                analyses_text += f"Summary: {a.get('summary', '')[:600]}\n"
                insights = a.get("key_insights", [])
                if insights:
                    analyses_text += f"Insights: {'; '.join(str(ins) for ins in insights[:4])}\n"
                analyses_text += f"Methodology: {a.get('methodology', '')[:400]}\n"
                analyses_text += f"Results: {a.get('results', '')[:400]}\n"

            compare_prompt = f"""You are comparing {len(analyses)} research papers on the topic: "{topic}".

{analyses_text}

Return a JSON object with EXACTLY this structure:
{{
    "paper_contributions": [
        {{"paper_title": "exact title from above", "contribution": "One clear sentence describing this paper's unique contribution"}}
    ],
    "detailed_comparison": "A thorough comparison of ALL papers. MUST be AT LEAST 2000 characters. Compare approaches, methods, datasets, results, strengths, weaknesses.",
    "research_gaps": "A detailed analysis of gaps and actionable future research directions. At least 500 characters."
}}

Return ONLY valid JSON."""

            try:
                compare_result = await self.llm.call_text_json(compare_prompt, max_tokens=8192)
                if compare_result:
                    paper_contributions = compare_result.get("paper_contributions", [])
                    detailed_comparison = compare_result.get("detailed_comparison", "")
                    research_gaps       = compare_result.get("research_gaps",       "")
            except Exception as e:
                logger.error(f"   ⚠️ Compare LLM failed: {e}")

        logger.info(
            f"   ✅ Comparison complete: {len(paper_contributions)} contributions, "
            f"{len(detailed_comparison)} chars"
        )

        return {
            "summary": "", "key_insights": [], "methodology": "", "results": "",
            "limitations": "", "visual_groups": [],
            "title": topic, "authors": [], "year": 0, "venue": "",
            "doi": "", "arxiv_id": "", "pdf_url": "", "pdf_hash": "",
            "chunk_summaries": [], "total_chunks": 0, "pages_processed": 0,
            "papers":              selected_papers,
            "comparison":          detailed_comparison or "",
            "compared_analyses":   analyses,
            "papers_used":         papers_used,
            "paper_contributions": paper_contributions,
            "research_gaps":       research_gaps or "",
            "implementation":      {},
            "message":             f"Compared {len(analyses)} papers in detail.",
            "mode":                mode,
        }

    async def implement_with_papers(self, ctx: dict, papers: list) -> dict:
        topic      = ctx.get("topic", "") or ""
        mode       = "implement"
        top_papers = papers[:10]

        logger.info(f"   💻 Implementation for '{topic}' using {len(top_papers)} papers")

        definition_prompt = f"""Give a concise definition of the topic "{topic}" in about 200 characters.
Explain what it is, what problem it solves, and the core idea of how it works.
Return ONLY the definition text, no JSON, no markdown. Be brief in your thinking."""
        topic_definition = await self.llm.call_text(definition_prompt, max_tokens=2048)
        topic_definition = (topic_definition or "")[:250].strip()

        paper_extractions = []
        all_parameters    = {}

        for i, paper in enumerate(top_papers):
            title    = (paper.get("title",    "") or "") if isinstance(paper, dict) else ""
            abstract = (paper.get("abstract", "") or "")[:600] if isinstance(paper, dict) else ""
            pdf_url  = (paper.get("pdf_url",  "") or "") if isinstance(paper, dict) else ""
            pdf_hash = hashlib.md5(pdf_url.encode()).hexdigest() if pdf_url else ""

            extract_prompt = f"""Extract ALL implementation details from this research paper.

Paper: "{title}"
Abstract: {abstract}

Return JSON with:
{{
    "code_snippets": [{{"code": "...", "page_number": 1, "description": "..."}}],
    "parameters":    {{"parameter_name": "value or recommended range"}},
    "how_to_implement": "Brief step-by-step guide",
    "key_techniques": ["technique 1", "technique 2"]
}}

Return ONLY valid JSON."""

            try:
                extraction = await self.llm.call_text_json(extract_prompt, max_tokens=6144)
                if extraction:
                    extraction["paper_title"] = title
                    extraction["paper_index"] = i
                    extraction["pdf_url"]     = pdf_url
                    extraction["pdf_hash"]    = pdf_hash
                    paper_extractions.append(extraction)

                    params = extraction.get("parameters", {})
                    if isinstance(params, dict):
                        for k, v in params.items():
                            if k not in all_parameters:
                                all_parameters[k] = v
            except Exception as e:
                logger.warning(f"   ⚠️ Extract failed for paper {i}: {e}")

        params_text        = "\n".join(f"- {k}: {v}" for k, v in all_parameters.items()) or "No specific parameters found"
        techniques_all     = []
        for pe in paper_extractions:
            techniques_all.extend(pe.get("key_techniques", []))
        unique_techniques  = list(set(techniques_all))[:15]

        code_prompt = f"""Generate a COMPLETE, working Python implementation for the topic: "{topic}".

Common parameters found across {len(paper_extractions)} research papers:
{params_text}

Key techniques used:
{', '.join(unique_techniques) if unique_techniques else 'Standard approaches'}

Return ONLY the Python code, no markdown fences, no explanation. Be brief in your thinking."""

        generated_code = await self.llm.call_text(code_prompt, max_tokens=16384)

        impl = {
            "topic_definition": topic_definition,
            "paper_extractions": paper_extractions,
            "all_parameters":   all_parameters,
            "generated_code":   generated_code or "",
            "explanation":      topic_definition,
            "code":             generated_code or "",
            "parameters":       all_parameters,
        }

        top_paper = papers[0] if papers else {}
        pdf_url   = (top_paper.get("pdf_url", "") or "") if isinstance(top_paper, dict) else ""
        pdf_hash  = hashlib.md5(pdf_url.encode()).hexdigest() if pdf_url else ""

        logger.info(
            f"   ✅ Implementation complete: "
            f"{len(paper_extractions)} extracted, {len(all_parameters)} params"
        )

        return {
            "summary": topic_definition, "key_insights": [], "methodology": "",
            "results": "", "limitations": "", "visual_groups": [],
            "title": topic, "authors": [], "year": 0, "venue": "",
            "doi": "", "arxiv_id": "", "pdf_url": pdf_url, "pdf_hash": pdf_hash,
            "chunk_summaries": [], "total_chunks": 0, "pages_processed": 0,
            "papers": papers, "comparison": "", "compared_analyses": [],
            "implementation": impl,
            "message": f"Implementation generated from {len(paper_extractions)} papers.",
            "mode": mode,
        }

    def _empty_response(self, topic: str, mode: str, message: str) -> dict:
        return {
            "summary": "", "key_insights": [], "methodology": "",
            "results": "", "limitations": "", "visual_groups": [],
            "title": topic, "authors": [], "year": 0, "venue": "",
            "doi": "", "arxiv_id": "", "pdf_url": "", "pdf_hash": "",
            "chunk_summaries": [], "total_chunks": 0, "pages_processed": 0,
            "papers": [], "comparison": "", "compared_analyses": [],
            "implementation": {}, "message": message, "mode": mode,
        }
