"""Deterministic, explainable scoring. Pure functions only: no DB, no LLM.

Each eligible employee gets a retention score in [0, 100]:
  1. every factor is min-max normalised to [0, 1] across the eligible pool
     (all-equal values normalise to 0.5),
  2. factors where lower is better are inverted (1 - x),
  3. score = 100 * sum(weight_i * normalised_i), weights rescaled to sum to 1.
Lowest scores rank first; the first `target_count` are proposed for selection.
Ties break on employee_id so results are reproducible.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Candidate:
    employee_id: int
    values: Mapping[str, float]
    excluded: bool = False
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class ScoredCandidate:
    employee_id: int
    score: float | None
    rank: int | None
    contributions: dict[str, float] = field(default_factory=dict)
    selected: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None


def normalize_weights(weights: Mapping[str, float], known: Sequence[str]) -> dict[str, float]:
    unknown = set(weights) - set(known)
    if unknown:
        raise ValueError(f"unknown factors: {sorted(unknown)}")
    if any(v < 0 for v in weights.values()):
        raise ValueError("weights must be non-negative")
    active = {k: float(v) for k, v in weights.items() if v > 0}
    total = sum(active.values())
    if total == 0:
        raise ValueError("at least one weight must be positive")
    return {k: v / total for k, v in active.items()}


def score_pool(
    candidates: Sequence[Candidate],
    weights: Mapping[str, float],
    directions: Mapping[str, bool],
    target_count: int,
) -> list[ScoredCandidate]:
    w = normalize_weights(weights, list(directions))
    eligible = [c for c in candidates if not c.excluded]

    ranges: dict[str, tuple[float, float]] = {}
    for k in w:
        vals = [c.values[k] for c in eligible]
        ranges[k] = (min(vals), max(vals)) if vals else (0.0, 0.0)

    raw: list[tuple[float, Candidate, dict[str, float]]] = []
    for c in eligible:
        contribs: dict[str, float] = {}
        total = 0.0
        for k, wk in w.items():
            lo, hi = ranges[k]
            norm = 0.5 if hi == lo else (c.values[k] - lo) / (hi - lo)
            if not directions[k]:
                norm = 1.0 - norm
            part = wk * norm * 100
            contribs[k] = round(part, 4)
            total += part
        raw.append((round(total, 4), c, contribs))

    raw.sort(key=lambda t: (t[0], t[1].employee_id))
    out = [
        ScoredCandidate(
            employee_id=c.employee_id,
            score=score,
            rank=i,
            contributions=contribs,
            selected=i <= target_count,
        )
        for i, (score, c, contribs) in enumerate(raw, start=1)
    ]
    out.extend(
        ScoredCandidate(
            employee_id=c.employee_id,
            score=None,
            rank=None,
            excluded=True,
            exclusion_reason=c.exclusion_reason,
        )
        for c in sorted(candidates, key=lambda c: c.employee_id)
        if c.excluded
    )
    return out


def apply_overrides(scored: Sequence[ScoredCandidate], overrides: Mapping[int, str]) -> dict[int, bool]:
    """Final selection per employee after manual overrides.
    Hard-excluded employees are never selected, whatever the override says."""
    final: dict[int, bool] = {}
    for s in scored:
        if s.excluded:
            final[s.employee_id] = False
            continue
        action = overrides.get(s.employee_id)
        if action == "include":
            final[s.employee_id] = True
        elif action == "exclude":
            final[s.employee_id] = False
        else:
            final[s.employee_id] = s.selected
    return final
