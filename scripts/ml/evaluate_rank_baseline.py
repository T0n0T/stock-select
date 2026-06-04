# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METHOD = "b2"
POLICIES = [
    "current_score_desc",
    "baseline_score_desc",
    "pass_then_current_score_desc",
    "pass_watch_then_current_score_desc",
]
MISMATCH_FEATURE_COLUMNS = [
    "current_verdict",
    "current_score",
    "baseline_score",
    "signal",
    "signal_type",
    "env",
    "close_to_ma25_pct",
    "close_to_zxdkx_pct",
    "ma25_to_zxdkx_pct",
    "zxdq_slope_5d_pct",
    "zxdkx_slope_5d_pct",
    "low_to_ma25_pct",
    "near_ma25_support_flag",
    "ma_aligned_flag",
    "box_position_120d_pct",
    "volume_to_ma20_ratio",
    "abnormal_volume_event_days_ago",
    "abnormal_volume_to_ma20_ratio",
    "macd_hist_to_close_pct",
]
DEFAULT_FACTOR_DIAGNOSTIC_COLUMNS = [
    "latest_bar_position_pct",
    "post_abnormal_min_body_to_event_price_pct",
    "volume_ma5_to_ma20_ratio",
    "abnormal_event_price_to_current_pct",
    "abnormal_event_body_pct",
    "close_to_120d_max_pct",
    "ma25_slope_5d_pct",
    "macd_hist_slope_3d_to_close_pct",
    "close_to_close_ma5_pct",
    "range_width_120d_pct",
    "close_to_ma25_pct",
    "close_to_zxdkx_pct",
    "ma25_to_zxdkx_pct",
    "zxdq_slope_5d_pct",
    "zxdkx_slope_5d_pct",
    "low_to_ma25_pct",
    "box_position_120d_pct",
    "volume_to_ma20_ratio",
    "abnormal_volume_to_ma20_ratio",
    "abnormal_volume_event_days_ago",
    "macd_hist_to_close_pct",
]
DEFAULT_CATEGORICAL_DIAGNOSTIC_COLUMNS = [
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
    "signal",
    "signal_type",
]


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100.0, 1) if denominator else None


def avg(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def score_key(row: dict[str, Any], key: str) -> tuple[int, float]:
    value = as_float(row.get(key))
    if value is None:
        return (1, 0.0)
    return (0, -value)


def verdict_bucket(row: dict[str, Any], *, include_watch: bool) -> int:
    verdict = str(row.get("current_verdict") or "").upper()
    if verdict == "PASS":
        return 0
    if include_watch and verdict == "WATCH":
        return 1
    return 2


def sort_policy(rows: Sequence[dict[str, Any]], policy: str) -> list[dict[str, Any]]:
    if policy == "current_score_desc":
        return sorted(rows, key=lambda row: (score_key(row, "current_score"), str(row.get("date")), str(row.get("code"))))
    if policy == "baseline_score_desc":
        return sorted(rows, key=lambda row: (score_key(row, "baseline_score"), str(row.get("date")), str(row.get("code"))))
    if policy == "pass_then_current_score_desc":
        return sorted(
            rows,
            key=lambda row: (
                0 if str(row.get("current_verdict")).upper() == "PASS" else 1,
                score_key(row, "current_score"),
                str(row.get("date")),
                str(row.get("code")),
            ),
        )
    if policy == "pass_watch_then_current_score_desc":
        return sorted(
            rows,
            key=lambda row: (
                verdict_bucket(row, include_watch=True),
                score_key(row, "current_score"),
                str(row.get("date")),
                str(row.get("code")),
            ),
        )
    raise ValueError(f"unknown policy: {policy}")


def ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        for original_index, _value in ordered[index:end]:
            result[original_index] = average_rank
        index = end
    return result


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_den = math.sqrt(sum((a - left_mean) ** 2 for a in left))
    right_den = math.sqrt(sum((b - right_mean) ** 2 for b in right))
    if left_den == 0.0 or right_den == 0.0:
        return None
    return round(numerator / left_den / right_den, 4)


def rank_ic(ordered_rows: Sequence[dict[str, Any]], label: str) -> float | None:
    pairs = [(-float(index + 1), as_float(row.get(label))) for index, row in enumerate(ordered_rows) if as_float(row.get(label)) is not None]
    if len(pairs) < 2:
        return None
    policy_rank, label_values = zip(*pairs)
    return pearson(ranks(policy_rank), ranks(label_values))


def grouped_by_date(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("date"))].append(row)
    return grouped


def evaluate_policy(rows: Sequence[dict[str, Any]], *, policy: str, top_n: int) -> dict[str, Any]:
    positive_ret3 = ge5_ret3 = le0_ret3 = total_ret3 = 0
    captured_ge5_ret3 = total_ge5_ret3 = 0
    positive_ret5 = ge5_ret5 = le0_ret5 = total_ret5 = 0
    captured_ge5_ret5 = total_ge5_ret5 = 0
    day_hit_ret3 = day_count_ret3 = 0
    day_hit_ret5 = day_count_ret5 = 0
    ic_ret3_values: list[float] = []
    ic_ret5_values: list[float] = []
    grouped = grouped_by_date(rows)

    for _pick_date, day_rows in grouped.items():
        ordered = sort_policy(day_rows, policy)
        top_rows = ordered[:top_n]
        day_good_ret3 = [row for row in day_rows if (as_float(row.get("ret3")) is not None and as_float(row.get("ret3")) >= 5.0)]
        day_good_ret5 = [row for row in day_rows if (as_float(row.get("ret5")) is not None and as_float(row.get("ret5")) >= 5.0)]
        top_codes = {str(row.get("code")) for row in top_rows}
        if day_good_ret3:
            total_ge5_ret3 += len(day_good_ret3)
            captured_ge5_ret3 += sum(1 for row in day_good_ret3 if str(row.get("code")) in top_codes)
        if day_good_ret5:
            total_ge5_ret5 += len(day_good_ret5)
            captured_ge5_ret5 += sum(1 for row in day_good_ret5 if str(row.get("code")) in top_codes)
        ret3_values = [as_float(row.get("ret3")) for row in top_rows if as_float(row.get("ret3")) is not None]
        ret5_values = [as_float(row.get("ret5")) for row in top_rows if as_float(row.get("ret5")) is not None]
        if ret3_values:
            day_count_ret3 += 1
            day_hit_ret3 += int(any(value > 0 for value in ret3_values))
            positive_ret3 += sum(1 for value in ret3_values if value > 0)
            ge5_ret3 += sum(1 for value in ret3_values if value >= 5)
            le0_ret3 += sum(1 for value in ret3_values if value <= 0)
            total_ret3 += len(ret3_values)
        if ret5_values:
            day_count_ret5 += 1
            day_hit_ret5 += int(any(value > 0 for value in ret5_values))
            positive_ret5 += sum(1 for value in ret5_values if value > 0)
            ge5_ret5 += sum(1 for value in ret5_values if value >= 5)
            le0_ret5 += sum(1 for value in ret5_values if value <= 0)
            total_ret5 += len(ret5_values)

        ic3 = rank_ic(ordered, "ret3")
        ic5 = rank_ic(ordered, "ret5")
        if ic3 is not None:
            ic_ret3_values.append(ic3)
        if ic5 is not None:
            ic_ret5_values.append(ic5)

    prefix = f"top{top_n}"
    return {
        "sample_count": len(rows),
        "date_count": len(grouped),
        f"{prefix}_ret3_positive_rate": pct(positive_ret3, total_ret3),
        f"{prefix}_ret5_positive_rate": pct(positive_ret5, total_ret5),
        f"{prefix}_ret3_ge_5_rate": pct(ge5_ret3, total_ret3),
        f"{prefix}_ret3_le_0_rate": pct(le0_ret3, total_ret3),
        f"{prefix}_ret3_ge_5_capture_rate": pct(captured_ge5_ret3, total_ge5_ret3),
        f"{prefix}_ret3_le_0_intrusion_rate": pct(le0_ret3, total_ret3),
        f"{prefix}_ret5_ge_5_rate": pct(ge5_ret5, total_ret5),
        f"{prefix}_ret5_le_0_rate": pct(le0_ret5, total_ret5),
        f"{prefix}_ret5_ge_5_capture_rate": pct(captured_ge5_ret5, total_ge5_ret5),
        f"{prefix}_ret5_le_0_intrusion_rate": pct(le0_ret5, total_ret5),
        f"{prefix}_day_hit_rate_ret3": pct(day_hit_ret3, day_count_ret3),
        f"{prefix}_day_hit_rate_ret5": pct(day_hit_ret5, day_count_ret5),
        "rank_ic_ret3": round(sum(ic_ret3_values) / len(ic_ret3_values), 4) if ic_ret3_values else None,
        "rank_ic_ret5": round(sum(ic_ret5_values) / len(ic_ret5_values), 4) if ic_ret5_values else None,
        "rank_ic_ret3_date_count": len(ic_ret3_values),
        "rank_ic_ret5_date_count": len(ic_ret5_values),
}


def mismatch_case(row: dict[str, Any], *, rank: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "date": row.get("date") or "",
        "code": row.get("code") or "",
        "name": row.get("name") or "",
        "rank": rank,
        "ret3": as_float(row.get("ret3")),
        "ret5": as_float(row.get("ret5")),
    }
    for column in MISMATCH_FEATURE_COLUMNS:
        value = as_float(row.get(column))
        item[column] = value if value is not None else row.get(column, "")
    return item


def collect_mismatch_cases(
    rows: Sequence[dict[str, Any]], *, policy: str, top_n: int = 3, limit: int = 50
) -> dict[str, list[dict[str, Any]]]:
    top_losers: list[dict[str, Any]] = []
    missed_winners: list[dict[str, Any]] = []
    for _pick_date, day_rows in grouped_by_date(rows).items():
        ordered = sort_policy(day_rows, policy)
        for index, row in enumerate(ordered, start=1):
            ret3 = as_float(row.get("ret3"))
            if ret3 is None:
                continue
            if index <= top_n and ret3 <= 0.0:
                top_losers.append(mismatch_case(row, rank=index))
            if index > top_n and ret3 >= 5.0:
                missed_winners.append(mismatch_case(row, rank=index))
    top_losers.sort(key=lambda item: (float(item.get("ret3") or 0.0), str(item.get("date")), int(item.get("rank") or 0)))
    missed_winners.sort(key=lambda item: (-(float(item.get("ret3") or 0.0)), str(item.get("date")), int(item.get("rank") or 0)))
    return {
        "top_losers": top_losers[:limit],
        "missed_winners": missed_winners[:limit],
    }


def factor_bucket_diagnostics(
    rows: Sequence[dict[str, Any]], *, factors: Sequence[str], envs: Sequence[str], bucket_count: int = 4
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for factor in factors:
        diagnostics[factor] = {}
        for env in envs:
            pairs = [
                (as_float(row.get(factor)), as_float(row.get("ret3")))
                for row in rows
                if str(row.get("env") or "unknown").lower() == env
            ]
            valid = sorted((factor_value, ret3) for factor_value, ret3 in pairs if factor_value is not None and ret3 is not None)
            buckets = []
            if valid:
                for bucket_index in range(bucket_count):
                    start = bucket_index * len(valid) // bucket_count
                    end = (bucket_index + 1) * len(valid) // bucket_count
                    bucket = valid[start:end]
                    if not bucket:
                        continue
                    factor_values = [item[0] for item in bucket]
                    ret3_values = [item[1] for item in bucket]
                    buckets.append(
                        {
                            "bucket": bucket_index,
                            "sample_count": len(bucket),
                            "factor_min": round(min(factor_values), 4),
                            "factor_max": round(max(factor_values), 4),
                            "ret3_avg": avg(ret3_values),
                            "ret3_positive_rate": pct(sum(1 for value in ret3_values if value > 0.0), len(ret3_values)),
                            "ret3_ge_5_rate": pct(sum(1 for value in ret3_values if value >= 5.0), len(ret3_values)),
                            "ret3_le_0_rate": pct(sum(1 for value in ret3_values if value <= 0.0), len(ret3_values)),
                        }
                    )
            diagnostics[factor][env] = {
                "sample_count": len(valid),
                "buckets": buckets,
            }
    return diagnostics


def factor_separation_diagnostics(bucket_diagnostics: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for factor, by_env in bucket_diagnostics.items():
        env_summary: dict[str, Any] = {}
        for env, payload in by_env.items():
            buckets = payload.get("buckets", []) if isinstance(payload, dict) else []
            if not buckets:
                env_summary[env] = {
                    "sample_count": 0,
                    "ret3_avg_spread": None,
                    "ret3_positive_rate_spread": None,
                    "ret3_ge_5_rate_spread": None,
                    "ret3_le_0_rate_spread": None,
                }
                continue

            def spread(key: str) -> float | None:
                values = [as_float(bucket.get(key)) for bucket in buckets]
                valid = [value for value in values if value is not None]
                return round(max(valid) - min(valid), 4) if valid else None

            env_summary[env] = {
                "sample_count": payload.get("sample_count"),
                "ret3_avg_spread": spread("ret3_avg"),
                "ret3_positive_rate_spread": spread("ret3_positive_rate"),
                "ret3_ge_5_rate_spread": spread("ret3_ge_5_rate"),
                "ret3_le_0_rate_spread": spread("ret3_le_0_rate"),
            }
        result[factor] = env_summary
    return result


def categorical_factor_diagnostics(
    rows: Sequence[dict[str, Any]], *, factors: Sequence[str], envs: Sequence[str]
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for factor in factors:
        diagnostics[factor] = {}
        for env in envs:
            grouped: dict[str, list[float]] = defaultdict(list)
            for row in rows:
                if str(row.get("env") or "unknown").lower() != env:
                    continue
                ret3 = as_float(row.get("ret3"))
                if ret3 is None:
                    continue
                value = str(row.get(factor) or "unknown").strip() or "unknown"
                grouped[value].append(ret3)
            diagnostics[factor][env] = {
                value: {
                    "sample_count": len(ret3_values),
                    "ret3_avg": avg(ret3_values),
                    "ret3_positive_rate": pct(sum(1 for item in ret3_values if item > 0.0), len(ret3_values)),
                    "ret3_ge_5_rate": pct(sum(1 for item in ret3_values if item >= 5.0), len(ret3_values)),
                    "ret3_le_0_rate": pct(sum(1 for item in ret3_values if item <= 0.0), len(ret3_values)),
                }
                for value, ret3_values in sorted(
                    grouped.items(), key=lambda item: (-len(item[1]), item[0])
                )
            }
    return diagnostics


def read_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def merge_topn_metrics(rows: Sequence[dict[str, Any]], *, policy: str, top_ns: Sequence[int]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for top_n in top_ns:
        merged.update(evaluate_policy(rows, policy=policy, top_n=top_n))
    return merged


def build_report(rows: Sequence[dict[str, Any]], *, dataset: Path, top_ns: Sequence[int], envs: Sequence[str], method: str = DEFAULT_METHOD) -> dict[str, Any]:
    policies: dict[str, Any] = {}
    warnings: list[str] = []
    if not rows:
        warnings.append("dataset_empty")
    for policy in POLICIES:
        by_env = {}
        for env in envs:
            env_rows = [row for row in rows if str(row.get("env") or "unknown").lower() == env]
            by_env[env] = merge_topn_metrics(env_rows, policy=policy, top_ns=top_ns)
        policies[policy] = {
            "overall": merge_topn_metrics(rows, policy=policy, top_ns=top_ns),
            "by_env": by_env,
            "mismatch_cases": collect_mismatch_cases(rows, policy=policy, top_n=min(top_ns), limit=50),
        }
    factor_diagnostics = factor_bucket_diagnostics(
        rows,
        factors=[factor for factor in DEFAULT_FACTOR_DIAGNOSTIC_COLUMNS if any(row.get(factor) not in (None, "") for row in rows)],
        envs=envs,
    )
    return {
        "method": method,
        "dataset": str(dataset),
        "row_count": len(rows),
        "date_count": len({str(row.get("date")) for row in rows}),
        "policies": policies,
        "factor_diagnostics": factor_diagnostics,
        "factor_separation_diagnostics": factor_separation_diagnostics(factor_diagnostics),
        "categorical_factor_diagnostics": categorical_factor_diagnostics(
            rows,
            factors=[
                factor
                for factor in DEFAULT_CATEGORICAL_DIAGNOSTIC_COLUMNS
                if any(row.get(factor) not in (None, "") for row in rows)
            ],
            envs=envs,
        ),
        "warnings": warnings,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# {report.get('method', DEFAULT_METHOD)} baseline ranking report",
        "",
        f"dataset: `{report['dataset']}`",
        f"rows: `{report['row_count']}`",
        f"dates: `{report['date_count']}`",
        "",
        "| policy | scope | top3 ret3 positive | top3 ret3 >=5 | top3 ret3 <=0 | top3 ret3 >=5 capture | top5 ret3 positive | rank ic ret3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for policy, payload in report["policies"].items():
        scopes = {"overall": payload["overall"]}
        scopes.update({f"env:{env}": metrics for env, metrics in payload["by_env"].items()})
        for scope, metrics in scopes.items():
            lines.append(
                "| {policy} | {scope} | {top3_pos} | {top3_ge5} | {top3_le0} | {top3_capture} | {top5_pos} | {ic3} |".format(
                    policy=policy,
                    scope=scope,
                    top3_pos=metrics.get("top3_ret3_positive_rate"),
                    top3_ge5=metrics.get("top3_ret3_ge_5_rate"),
                    top3_le0=metrics.get("top3_ret3_le_0_rate"),
                    top3_capture=metrics.get("top3_ret3_ge_5_capture_rate"),
                    top5_pos=metrics.get("top5_ret3_positive_rate"),
                    ic3=metrics.get("rank_ic_ret3"),
                )
            )
    lines.extend(["", "## mismatch cases", ""])
    for policy, payload in report["policies"].items():
        cases = payload.get("mismatch_cases", {})
        top_losers = cases.get("top_losers", [])[:5]
        missed_winners = cases.get("missed_winners", [])[:5]
        lines.extend([f"### {policy}", "", "top losers:"])
        if top_losers:
            lines.extend(
                f"- {item.get('date')} {item.get('code')} rank={item.get('rank')} ret3={item.get('ret3')} env={item.get('env')} signal={item.get('signal')} close_to_zxdkx_pct={item.get('close_to_zxdkx_pct')}"
                for item in top_losers
            )
        else:
            lines.append("- none")
        lines.append("missed winners:")
        if missed_winners:
            lines.extend(
                f"- {item.get('date')} {item.get('code')} rank={item.get('rank')} ret3={item.get('ret3')} env={item.get('env')} signal={item.get('signal')} close_to_zxdkx_pct={item.get('close_to_zxdkx_pct')}"
                for item in missed_winners
            )
        else:
            lines.append("- none")
        lines.append("")
    if report.get("factor_diagnostics"):
        lines.extend(["", "## factor diagnostics", ""])
        for factor, by_env in report["factor_diagnostics"].items():
            lines.extend([f"### {factor}", "", "| env | bucket | n | factor min | factor max | ret3 avg | ret3 >=5 | ret3 <=0 |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
            for env, payload in by_env.items():
                for bucket in payload.get("buckets", []):
                    lines.append(
                        "| {env} | {bucket} | {n} | {fmin} | {fmax} | {avg_ret3} | {ge5} | {le0} |".format(
                            env=env,
                            bucket=bucket.get("bucket"),
                            n=bucket.get("sample_count"),
                            fmin=bucket.get("factor_min"),
                            fmax=bucket.get("factor_max"),
                            avg_ret3=bucket.get("ret3_avg"),
                            ge5=bucket.get("ret3_ge_5_rate"),
                            le0=bucket.get("ret3_le_0_rate"),
                        )
                    )
            lines.append("")
    if report.get("categorical_factor_diagnostics"):
        lines.extend(["", "## categorical factor diagnostics", ""])
        for factor, by_env in report["categorical_factor_diagnostics"].items():
            lines.extend([f"### {factor}", "", "| env | value | n | ret3 avg | ret3 >=5 | ret3 <=0 |", "|---|---|---:|---:|---:|---:|"])
            for env, values in by_env.items():
                for value, metrics in values.items():
                    lines.append(
                        "| {env} | {value} | {n} | {avg_ret3} | {ge5} | {le0} |".format(
                            env=env,
                            value=value,
                            n=metrics.get("sample_count"),
                            avg_ret3=metrics.get("ret3_avg"),
                            ge5=metrics.get("ret3_ge_5_rate"),
                            le0=metrics.get("ret3_le_0_rate"),
                        )
                    )
            lines.append("")
    if report.get("warnings"):
        lines.extend(["", "## warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "baseline_ranking_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "baseline_ranking_report.md").write_text(markdown_report(report), encoding="utf-8")


def parse_top_ns(value: str) -> list[int]:
    try:
        result = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--top-n must contain positive integers.") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("--top-n must contain positive integers.")
    return result


def parse_envs(value: str) -> list[str]:
    envs = [item.strip().lower() for item in value.split(",") if item.strip()]
    allowed = {"weak", "neutral", "strong", "unknown"}
    invalid = [item for item in envs if item not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(f"unsupported env values: {','.join(invalid)}")
    return envs


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate offline rank baseline policies.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--top-n", type=parse_top_ns, default=parse_top_ns("3,5"))
    parser.add_argument("--env", type=parse_envs, default=parse_envs("weak,neutral,strong,unknown"))
    return parser.parse_args(argv)


def resolve_default_paths(method: str) -> dict[str, Path]:
    root = PROJECT_ROOT / "diagnostics" / "ml" / method
    return {
        "dataset": root / "rank_dataset.csv",
        "output_dir": root,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    defaults = resolve_default_paths(args.method)
    dataset = args.dataset or defaults["dataset"]
    output_dir = args.output_dir or defaults["output_dir"]
    rows = read_dataset(dataset)
    report = build_report(rows, dataset=dataset, top_ns=args.top_n, envs=args.env, method=args.method)
    write_report(report, output_dir)
    print(f"wrote report to {output_dir / 'baseline_ranking_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
