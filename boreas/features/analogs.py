"""Nearest-neighbour analog days by residual-load shape (pure numpy)."""
from __future__ import annotations

import numpy as np


def normalize_shape(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr
    mu, sd = arr.mean(), arr.std()
    return (arr - mu) / sd if sd > 1e-9 else arr - mu


def analog_distance(a: list[float], b: list[float]) -> float:
    """Euclidean distance between z-normalized daily shapes (lower = more similar)."""
    na, nb = normalize_shape(a), normalize_shape(b)
    n = min(na.size, nb.size)
    if n == 0:
        return float("inf")
    return float(np.linalg.norm(na[:n] - nb[:n]) / np.sqrt(n))


def top_analogs(target: list[float], candidates: dict[str, list[float]], k: int = 5) -> list[tuple[str, float]]:
    scored = [(day, analog_distance(target, shape)) for day, shape in candidates.items()]
    scored.sort(key=lambda t: t[1])
    return scored[:k]
