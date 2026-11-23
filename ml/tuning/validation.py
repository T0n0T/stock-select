"""按季度抽取连续验证段，固定日期组并保持时间因果关系。"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
import random
from typing import Any, Sequence


def distributed_backtest_splits(
    dates: Sequence[str], sessions: Sequence[str], *, initial_train_dates: int,
    test_dates: int, holdout_dates: int, purge_gap: int, seed: int,
) -> dict[str, Any]:
    if min(initial_train_dates, test_dates, holdout_dates) <= 0 or purge_gap < 0:
        raise ValueError("validation window lengths must be positive and gap nonnegative")
    calendar = sorted(set(sessions))
    indices = {day: i for i, day in enumerate(calendar)}
    eligible = sorted({day for day in dates if day in indices and indices[day] + purge_gap < len(calendar)})
    quarters: dict[str, list[str]] = defaultdict(list)
    for day in eligible[initial_train_dates + purge_gap:]:
        quarters[f"{day[:4]}Q{(int(day[5:7]) - 1) // 3 + 1}"].append(day)
    rng = random.Random(seed)
    blocks, skipped = [], []
    for quarter, days in sorted(quarters.items()):
        # 未结束季度优先保留完整留出段，选参段可缩短，避免遗漏最新环境。
        development_count = min(test_dates, len(days) - holdout_dates - purge_gap)
        if development_count < min(5, test_dates):
            skipped.append(quarter)
            continue
        choices = [(a, b) for a in range(len(days) - development_count + 1)
                   for b in range(len(days) - holdout_dates + 1)
                   if a + development_count + purge_gap <= b or b + holdout_dates + purge_gap <= a]
        if not choices:
            skipped.append(quarter)
            continue
        a, b = rng.choice(choices)
        blocks.append({"quarter": quarter, "development": days[a:a + development_count],
                       "holdout": days[b:b + holdout_dates]})
    if len(blocks) < 2:
        raise ValueError("not enough complete quarter blocks for distributed validation")
    reserved = sorted(day for block in blocks for day in block["holdout"])
    blocked_indices = {i for day in reserved for i in range(
        max(0, indices[day] - purge_gap), min(len(calendar), indices[day] + purge_gap + 1))}
    development = [day for day in eligible if indices[day] not in blocked_indices]

    def splits(role: str) -> list[tuple[list[str], list[str]]]:
        result = []
        for block in blocks:
            test = block[role]
            train = [day for day in development if indices[day] + purge_gap < indices[test[0]]]
            if not train:
                raise ValueError("quarter block has no past training history")
            result.append((train, list(test)))
        return result

    return {"development_dates": development, "holdout_dates": reserved,
            "development_splits": splits("development"), "holdout_splits": splits("holdout"),
            "quarter_blocks": blocks, "skipped_quarters": skipped, "seed": seed,
            "initial_train_dates": initial_train_dates, "purge_gap": purge_gap}


def exclude_reserved_label_spans(
    rows: Sequence[dict[str, Any]], label_ends: dict[tuple[str, str], str], reserved_dates: Sequence[str],
) -> list[dict[str, Any]]:
    reserved = sorted(set(reserved_dates))
    safe = []
    for row in rows:
        day = str(row["date"])
        end = label_ends.get((day, str(row["code"])), day)
        index = bisect_left(reserved, day)
        if index == len(reserved) or reserved[index] > end:
            safe.append(row)
    return safe
