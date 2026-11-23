"""变动持有期标签；切分时按实际退出时点隔离，并重建日内分档。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from ml.backtest.rule_exit import ExitMarket
from .labels import as_float


def exit_quartile_labels(values: dict[str, float]) -> dict[str, int]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    output = {}
    index, count = 0, len(ordered)
    while index < count:
        end = index+1
        while end < count and ordered[end][1] == ordered[index][1]:
            end += 1
        # 相同收益使用相同分档；20 个不同收益对应 5/5/5/5。
        bucket = min(3, int(((index+end-1)/2)*4/count))
        for code, _ in ordered[index:end]:
            output[code] = bucket
        index = end
    return output


def _rebuild_ranks(rows: list[dict[str, Any]]) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["date"])].append(row)
    for group in groups.values():
        values = {str(row["code"]): value for row in group if (value := as_float(row.get("exit_net_return"))) is not None}
        labels = exit_quartile_labels(values)
        for row in group:
            row["rank_label_exit"] = labels.get(str(row["code"]), "")


def align_exit_labels(
    rows: Sequence[dict[str, Any]], market: ExitMarket, *, commission_rate: float = .0003,
    stamp_tax_rate: float = .0005, transfer_fee_rate: float = .00001,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], str]]:
    output, ends = [], {}
    for original in rows:
        row = dict(original)
        for column in ("exit_return", "exit_net_return", "rank_label_exit", "exit_date", "exit_reason",
                       "exit_entry_date", "exit_holding_sessions"):
            row[column] = ""
        day, code = str(row["date"]), str(row["code"])
        outcome = market.outcome(code, day)
        row["exit_label_status"] = outcome["status"]
        if outcome["status"] == "closed":
            row.update(exit_return=outcome["return_pct"], exit_date=outcome["exit_date"],
                       exit_reason=outcome["exit_reason"], exit_entry_date=outcome["entry_date"],
                       exit_holding_sessions=outcome["holding_sessions"])
            row["exit_net_return"] = (
                outcome["exit_price"]*(1-commission_rate-stamp_tax_rate-transfer_fee_rate)
                / (outcome["entry_price"]*(1+commission_rate+transfer_fee_rate))-1
            )*100
            ends[(day, code)] = outcome["exit_date"]
        output.append(row)
    _rebuild_ranks(output)
    return output, ends


def policy_training_rows_before(rows: Sequence[dict[str, Any]], dates: set[str], cutoff: str) -> list[dict[str, Any]]:
    safe = [dict(row) for row in rows if str(row["date"]) in dates
            and row.get("exit_date") and str(row["exit_date"]) < cutoff
            and as_float(row.get("exit_net_return")) is not None]
    safe.sort(key=lambda row: (str(row["date"]), str(row["code"])))
    _rebuild_ranks(safe)
    return safe
