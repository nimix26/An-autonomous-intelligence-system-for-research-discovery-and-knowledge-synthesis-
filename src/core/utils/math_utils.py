# core/utils/math_utils.py
"""
Shared numerical utilities — single source of truth for normalization.

All similarity/normalization operations across scoring.py, filters.py,
and mmr_diversifier.py MUST use these functions to avoid the recurring
zero-vector matmul warnings.
"""

import logging
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)


def safe_normalize(matrix: np.ndarray, eps: float = 1e-10) -> Tuple[np.ndarray, np.ndarray]:
    """
    L2-normalize rows of a 2D matrix with zero-vector guard.

    Returns:
        (normalized, valid_mask)
        - normalized: (N, D) matrix where zero-vector rows are set to 0.0
                      (not NaN, not Inf — safe for downstream matmul)
        - valid_mask: (N,) bool array, False where row was a zero vector

    This is the ONLY normalization function that should be used across
    the codebase. Do not write ad-hoc `X / np.linalg.norm(X)` anywhere.
    """
    if matrix is None:
        return np.zeros((0, 0)), np.zeros(0, dtype=bool)

    matrix = np.asarray(matrix, dtype=np.float64)

    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)

    if matrix.shape[0] == 0:
        return matrix, np.zeros(0, dtype=bool)

    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    # Clip pathological values before squaring so norm calculation cannot
    # overflow. Normal model embeddings are tiny compared with this bound.
    matrix = np.clip(matrix, -1e6, 1e6)

    norms = np.sqrt(np.sum(matrix * matrix, axis=1, keepdims=True))  # (N, 1)
    norms = np.nan_to_num(norms, nan=0.0, posinf=0.0, neginf=0.0)
    valid = (norms.squeeze(axis=1) > eps)                  # (N,)

    # Replace zero norms with 1.0 to avoid division warnings
    safe_norms = np.where(norms > eps, norms, 1.0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        normalized = matrix / safe_norms
    normalized = np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)

    # Explicitly zero out invalid rows (belt-and-suspenders)
    if (~valid).any():
        normalized = normalized.copy()
        normalized[~valid] = 0.0

    n_invalid = int((~valid).sum())
    if n_invalid > 0:
        logger.warning(
            f"   [safe_normalize] {n_invalid}/{matrix.shape[0]} zero-vector rows — "
            f"similarity for these papers will be 0"
        )
    return normalized, valid


def safe_cosine_sim(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """
    Cosine similarity between all rows of A and B, zero-vector safe.

    A: (N, D)  B: (M, D)
    Returns (N, M) matrix, clipped to [-1, 1], no NaN/Inf.
    """
    if A is None or B is None:
        return np.zeros((0, 0))
    A_norm, _ = safe_normalize(A)
    B_norm, _ = safe_normalize(B)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        sim = A_norm @ B_norm.T
    sim = np.nan_to_num(sim, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.clip(sim, -1.0, 1.0)
