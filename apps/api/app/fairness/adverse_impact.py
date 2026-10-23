"""Adverse impact analysis (four-fifths heuristic) on retention rates. Pure functions.

For each group: retention_rate = 1 - selected / pool.
impact_ratio = group retention_rate / highest group retention_rate.
A group is flagged when impact_ratio < threshold.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class GroupStat:
    group: str
    pool: int
    selected: int
    selection_rate: float
    retention_rate: float
    impact_ratio: float | None
    flagged: bool
    small_sample: bool


def adverse_impact(
    rows: Iterable[tuple[str, bool]],
    threshold: float = 0.8,
    min_group_size: int = 5,
) -> list[GroupStat]:
    pool: dict[str, int] = defaultdict(int)
    sel: dict[str, int] = defaultdict(int)
    for group, selected in rows:
        pool[group] += 1
        sel[group] += int(selected)

    retention = {g: 1 - sel[g] / pool[g] for g in pool}
    best = max(retention.values(), default=0.0)

    stats = []
    for g in sorted(pool):
        ratio = round(retention[g] / best, 4) if best > 0 else None
        stats.append(
            GroupStat(
                group=g,
                pool=pool[g],
                selected=sel[g],
                selection_rate=round(sel[g] / pool[g], 4),
                retention_rate=round(retention[g], 4),
                impact_ratio=ratio,
                flagged=ratio is not None and ratio < threshold,
                small_sample=pool[g] < min_group_size,
            )
        )
    return stats
