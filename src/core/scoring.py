# scoring.py — FIXED VERSION
# Removes all recency calculations, guarantees weight_recency=0.0 in relevance_mode

"""
core/scoring.py — Stage 4: Multi-Signal Scoring

Uses shared safe_normalize utility — NO ad-hoc normalization, NO div-by-zero warnings.
CRITICAL: Recency is NEVER used. Only relevance signals (semantic, seed, citation).
"""

import logging
import math
from datetime import datetime
from typing import List

import numpy as np

from core.query_profiler import QueryProfile
from core.utils.math_utils import safe_cosine_sim, safe_normalize

logger = logging.getLogger(__name__)


class PaperScorer:
    def __init__(self, llm_service=None):
        self.llm = llm_service

    def score_pool(
        self,
        papers: List[dict],
        profile: QueryProfile,
        query_embedding: np.ndarray = None,
        seed_embeddings: np.ndarray = None,
        paper_embeddings: np.ndarray = None,
    ) -> List[dict]:
        """
        Score papers using relevance signals:
          - semantic_sim:   query similarity (embedding-based)
          - seed_proximity: seed similarity (embedding-based)
          - citation_count: broad impact signal
          - field_impact:   citation velocity normalized inside this result pool
          - venue_quality:  lightweight venue reputation signal
          - rrf_score:      multi-channel rank-fusion evidence
          - channel_boost:  multi-source evidence

        CRITICAL: NO RECENCY. Ever.
        If profile.weight_recency != 0.0, something is wrong upstream.
        This function will clamp it to 0.0 as a safety measure.
        """
        if not papers:
            return []

        current_year = datetime.now().year
        n = len(papers)

        # ✅ SAFETY: Clamp recency weight to 0.0 regardless of profile
        w_recency_override = 0.0  # ALWAYS zero
        if profile.weight_recency != 0.0:
            logger.warning(
                f"   ⚠️ [Scoring] profile.weight_recency={profile.weight_recency} != 0.0 "
                f"in relevance_mode! Forcing to 0.0. Check QueryProfiler._derive_thresholds()."
            )
            profile.weight_recency = 0.0

        # Initialize signal arrays
        cite_velocity = np.zeros(n)
        citation_count = np.zeros(n)
        venue_quality = np.zeros(n)
        rrf_score = np.zeros(n)
        # ✅ REMOVED: recency = np.zeros(n)
        semantic_sim = np.zeros(n)
        seed_proximity = np.zeros(n)
        channel_boost = np.zeros(n)

        # Compute citation-based impact signal (NOT recency-based)
        for i, p in enumerate(papers):
            year = int(p.get("year", 0) or 0)
            cites = int(p.get("citation_count", 0) or 0)
            age = max(1, current_year - year) if year > 0 else 20.0
            
            # Citation velocity: cites per year (always favors impact, never age)
            cite_velocity[i] = cites / age
            citation_count[i] = math.log10(cites + 1)
            venue_quality[i] = self._venue_quality(p.get("venue", "") or "")
            rrf_score[i] = float(p.get("_rrf_score", 0.0) or 0.0)
            
            # ✅ NO recency computation
            # recency[i] = math.exp(-age / 7.0)  ← DELETED
            
            # Channel boost: papers found by multiple retrieval methods are stronger
            channels = p.get("_channels", [])
            channel_boost[i] = min(1.0, (len(channels) / 4.0)) if channels else 0.0

        # Compute embedding-based relevance signals
        embeddings_valid = (
            query_embedding is not None
            and paper_embeddings is not None
            and paper_embeddings.shape[0] == n
            and paper_embeddings.shape[0] > 0
        )

        if embeddings_valid:
            # ✅ FIX 1: use shared safe_normalize — no div-by-zero warnings
            q = np.asarray(query_embedding).flatten().reshape(1, -1)
            q_normed, q_valid = safe_normalize(q)
            p_normed, p_valid = safe_normalize(paper_embeddings)

            if q_valid[0]:
                semantic_sim = safe_cosine_sim(paper_embeddings, q).reshape(-1)
                semantic_sim[~p_valid] = 0.0
                n_invalid = int((~p_valid).sum())
                if n_invalid > 0:
                    logger.warning(f"   [SPECTER] {n_invalid}/{n} papers had zero embeddings — similarity set to 0")
            else:
                logger.warning("   [SPECTER] Query embedding was zero — semantic_sim disabled")
                semantic_sim = np.zeros(n)

            if seed_embeddings is not None and seed_embeddings.shape[0] > 0:
                s_normed, s_valid = safe_normalize(seed_embeddings)
                sims_to_seeds = safe_cosine_sim(paper_embeddings, seed_embeddings)
                # Zero out invalid seed columns and invalid paper rows
                if (~s_valid).any():
                    sims_to_seeds[:, ~s_valid] = 0.0
                sims_to_seeds[~p_valid, :] = 0.0
                seed_proximity = sims_to_seeds.max(axis=1) if sims_to_seeds.size > 0 else np.zeros(n)

        # Normalize signals to [0, 1]
        def normalize(arr: np.ndarray) -> np.ndarray:
            arr = np.asarray(arr, dtype=np.float64)
            arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
            lo, hi = float(arr.min()), float(arr.max())
            if hi - lo < 1e-9:
                return np.zeros_like(arr)
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                normalized = (arr - lo) / (hi - lo)
            return np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)

        cc_n = normalize(citation_count)
        fi_n = normalize(cite_velocity)
        vq_n = venue_quality
        rrf_n = normalize(rrf_score)
        # ✅ REMOVED: rc_n = normalize(recency)
        ss_n = normalize(semantic_sim)
        sp_n = normalize(seed_proximity)
        cb_n = channel_boost
        soft_n = (0.45 * cc_n) + (0.35 * fi_n) + (0.20 * vq_n)

        # ✅ REBALANCED WEIGHTS: RELEVANCE ONLY
        # Semantic (query match) + Seed alignment + soft metadata + RRF + channel boost
        # NO recency component
        if embeddings_valid:
            w_semantic   = 0.35
            w_seed_prox  = 0.20
            w_soft       = 0.25
            w_rrf        = 0.15
            w_channel    = 0.05
            w_recency    = 0.00  # ALWAYS ZERO
        else:
            # Fallback when embeddings unavailable
            w_semantic   = 0.0
            w_seed_prox  = 0.0
            w_soft       = 0.50
            w_rrf        = 0.35
            w_channel    = 0.15
            w_recency    = 0.00  # ALWAYS ZERO

        # Compute final scores
        for i, p in enumerate(papers):
            # ✅ NO recency signal in final score
            final_score = (
                w_semantic * ss_n[i] +
                w_seed_prox * sp_n[i] +
                w_soft * soft_n[i] +
                w_rrf * rrf_n[i] +
                w_recency * 0.0 +  # Always 0
                w_channel * cb_n[i]
            )

            p["signals"] = {
                "semantic_sim": round(float(ss_n[i]), 3),
                "seed_proximity": round(float(sp_n[i]), 3),
                "citation_count": round(float(cc_n[i]), 3),
                "field_normalized_impact": round(float(fi_n[i]), 3),
                "venue_quality": round(float(vq_n[i]), 3),
                "soft_metadata_score": round(float(soft_n[i]), 3),
                "rrf": round(float(rrf_n[i]), 3),
                # ✅ REMOVED: "recency": round(float(rc_n[i]), 3),
                "channel_boost": round(float(cb_n[i]), 3),
            }
            p["final_score"] = round(float(final_score), 4)

        papers.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        logger.info(f"   [Stage4] Scored {n} papers | weights: sem={w_semantic:.2f}, "
                    f"seed={w_seed_prox:.2f}, soft={w_soft:.2f}, "
                    f"rrf={w_rrf:.2f}, rec={w_recency:.2f}, ch={w_channel:.2f}")
        return papers

    @staticmethod
    def _venue_quality(venue: str) -> float:
        v = (venue or "").lower()
        if not v:
            return 0.0

        top_tier_terms = [
            "nature", "science", "cell", "nejm", "lancet", "jama",
            "neurips", "nips", "icml", "iclr", "acl", "emnlp", "naacl",
            "cvpr", "iccv", "eccv", "siggraph", "kdd", "www", "chi",
            "sigmod", "vldb", "osdi", "sosp", "pldi",
        ]
        strong_terms = [
            "ieee", "acm", "springer", "elsevier", "proceedings",
            "transactions", "journal", "conference", "workshop",
        ]

        if any(term in v for term in top_tier_terms):
            return 1.0
        if any(term in v for term in strong_terms):
            return 0.65
        return 0.35

    def heuristic_score(self, paper: dict, topic: str = "") -> float:
        """
        Fallback scoring when embeddings unavailable.
        Uses ONLY citation impact, never recency.
        """
        cites = int(paper.get("citation_count", 0) or 0)
        cite_score = min(1.0, math.log10(cites + 1) / 5.0)
        return round(cite_score, 3)

    async def score_all(self, papers, topic, context="", use_llm_relevance=True):
        """Score all papers using heuristic (no recency)."""
        for p in papers:
            if hasattr(p, "to_dict"):
                p.overall_score = self.heuristic_score(p.to_dict(), topic)
            else:
                p.overall_score = self.heuristic_score(p, topic)
        papers.sort(key=lambda x: getattr(x, "overall_score", 0), reverse=True)
        return papers
