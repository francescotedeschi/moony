"""Play-count bias for matching — no DB import (safe for core.py)."""

from __future__ import annotations

import math

PLAY_FAIRNESS_POOL_WEIGHT = 0.14
PLAY_FAIRNESS_SCORE_WEIGHT = 0.65


def play_fairness_tier(play_count: int, minimum_tier: int) -> bool:
    """True when *play_count* is in the best available tier (0 = never played)."""
    return play_count <= minimum_tier


def play_fairness_pool_bonus(play_count: int) -> float:
    """Subtract from mood distance rank — favors tracks with fewer plays."""
    return PLAY_FAIRNESS_POOL_WEIGHT * math.sqrt(max(0, play_count))


def play_fairness_score_penalty(play_count: int) -> float:
    """Subtract from match score — favors tracks with fewer plays."""
    return PLAY_FAIRNESS_SCORE_WEIGHT * math.sqrt(max(0, play_count))
