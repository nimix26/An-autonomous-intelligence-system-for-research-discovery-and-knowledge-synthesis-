"""
core/mmr_diversifier.py — Stage 5: Maximal Marginal Relevance Diversification

Uses shared safe_normalize utility — single source of truth for all normalization.
"""

import logging
from typing import List

import numpy as np

from core.utils.math_utils import safe_cosine_sim, safe_normalize

logger = logging.getLogger(__name__)


class MMRDiversifier:
    """Maximal Marginal Relevance paper selector."""

    def diversify(
        self,
        papers: List[dict],
        embeddings: np.ndarray,
        k: int = 30,
        lambda_param: float = 0.7,
    ) -> List[int]:
        n = len(papers)
        if n == 0:
            return []
        k = min(k, n)

        # Fix 1: shared safe_normalize — no ad-hoc div-by-zero patterns
        normed, valid_mask = safe_normalize(embeddings)
        n_invalid = int((~valid_mask).sum())

        # Pairwise similarity — clean, no warnings
        sim_matrix = safe_cosine_sim(embeddings, embeddings)

        # Zero out invalid rows/cols so bad embeddings contribute nothing
        if n_invalid > 0:
            sim_matrix[~valid_mask, :] = 0.0
            sim_matrix[:, ~valid_mask] = 0.0

        relevance = np.array([float(p.get("final_score", 0.0)) for p in papers])

        rel_min, rel_max = relevance.min(), relevance.max()
        if rel_max - rel_min > 1e-9:
            rel_norm = (relevance - rel_min) / (rel_max - rel_min)
        else:
            rel_norm = np.ones(n)

        selected: List[int] = []
        remaining = set(range(n))

        first = int(np.argmax(rel_norm))
        selected.append(first)
        remaining.discard(first)

        for _ in range(k - 1):
            if not remaining:
                break

            remaining_list = list(remaining)
            max_sim_to_selected = sim_matrix[np.ix_(remaining_list, selected)].max(axis=1)

            mmr_scores = (
                lambda_param * rel_norm[remaining_list]
                - (1.0 - lambda_param) * max_sim_to_selected
            )

            best_local = int(np.argmax(mmr_scores))
            best_idx = remaining_list[best_local]

            selected.append(best_idx)
            remaining.discard(best_idx)

        logger.info(f"      MMR selected {len(selected)}/{n} papers (λ={lambda_param:.2f})")
        return selected
