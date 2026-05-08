from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _return_stats(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {
            "count": 0,
            "avg_ret5_pct": None,
            "median_ret5_pct": None,
            "win_rate_pct": None,
            "surge_rate_pct": None,
        }
    return {
        "count": int(len(frame)),
        "avg_ret5_pct": round(float(frame["ret5_pct"].mean()), 3),
        "median_ret5_pct": round(float(frame["ret5_pct"].median()), 3),
        "win_rate_pct": round(float((frame["ret5_pct"] > 0).mean() * 100.0), 1),
        "surge_rate_pct": round(float((frame["ret5_pct"] >= 20).mean() * 100.0), 1),
    }


def _score_stats(frame: pd.DataFrame) -> dict[str, object]:
    payload = _return_stats(frame)
    if frame.empty:
        payload["avg_total_score"] = None
        return payload
    payload["avg_total_score"] = round(float(frame["total_score"].mean()), 3)
    return payload


def _records(frame: pd.DataFrame, *, limit: int = 20) -> list[dict[str, object]]:
    columns = [
        "pick_date",
        "code",
        "signal",
        "signal_type",
        "verdict",
        "watch_tier",
        "total_score",
        "ret5_pct",
        "trend_structure",
        "price_position",
        "volume_behavior",
        "previous_abnormal_move",
        "macd_phase",
        "box_position",
        "close_box_position",
        "box_range_pct",
        "zxdq_5d_slope_pct",
        "zxdkx_5d_slope_pct",
        "override_bucket",
    ]
    available = [column for column in columns if column in frame.columns]
    if not available:
        return []
    cleaned = frame[available].where(pd.notna(frame[available]), None)
    return cleaned.head(limit).to_dict(orient="records")


def _group_stats(frame: pd.DataFrame, by: list[str], *, min_count: int = 10) -> list[dict[str, object]]:
    if frame.empty:
        return []
    grouped = (
        frame.groupby(by)
        .agg(
            n=("ret5_pct", "size"),
            avg_ret5_pct=("ret5_pct", "mean"),
            median_ret5_pct=("ret5_pct", "median"),
            win_rate_pct=("ret5_pct", lambda s: (s > 0).mean() * 100.0),
            surge_rate_pct=("ret5_pct", lambda s: (s >= 20).mean() * 100.0),
        )
        .reset_index()
    )
    grouped = grouped[grouped["n"] >= min_count].copy()
    if grouped.empty:
        return []
    grouped["avg_ret5_pct"] = grouped["avg_ret5_pct"].round(3)
    grouped["median_ret5_pct"] = grouped["median_ret5_pct"].round(3)
    grouped["win_rate_pct"] = grouped["win_rate_pct"].round(1)
    grouped["surge_rate_pct"] = grouped["surge_rate_pct"].round(1)
    grouped = grouped.sort_values(["avg_ret5_pct", "win_rate_pct"], ascending=[False, False])
    return grouped.where(pd.notna(grouped), None).to_dict(orient="records")


def _quantiles(series: pd.Series) -> dict[str, float | None]:
    values = series.dropna()
    if values.empty:
        return {"mean": None, "median": None, "q10": None, "q25": None, "q50": None, "q75": None, "q90": None}
    return {
        "mean": round(float(values.mean()), 3),
        "median": round(float(values.median()), 3),
        "q10": round(float(values.quantile(0.10)), 3),
        "q25": round(float(values.quantile(0.25)), 3),
        "q50": round(float(values.quantile(0.50)), 3),
        "q75": round(float(values.quantile(0.75)), 3),
        "q90": round(float(values.quantile(0.90)), 3),
    }


def _top_bottom_block(frame: pd.DataFrame, *, top_n: int, ascending: bool) -> dict[str, object]:
    selected = frame.nsmallest(top_n, "ret5_pct") if ascending else frame.nlargest(top_n, "ret5_pct")
    return {
        **_return_stats(selected),
        "verdict_counts": {str(key): int(value) for key, value in selected["verdict"].value_counts().to_dict().items()},
        "watch_tier_counts": {str(key): int(value) for key, value in selected["watch_tier"].value_counts(dropna=False).to_dict().items()},
        "signal_type_counts": {
            f"{signal}|{signal_type}": int(count)
            for (signal, signal_type), count in selected.groupby(["signal", "signal_type"]).size().sort_values(ascending=False).items()
        },
        "override_counts": {str(key): int(value) for key, value in selected["override_bucket"].value_counts().to_dict().items()},
        "means": {
            column: round(float(selected[column].mean()), 3)
            for column in [
                "total_score",
                "trend_structure",
                "price_position",
                "volume_behavior",
                "previous_abnormal_move",
                "macd_phase",
                "box_position",
                "close_box_position",
                "box_range_pct",
                "zxdq_5d_slope_pct",
                "zxdkx_5d_slope_pct",
            ]
            if column in selected.columns
        },
    }


def _watch_score_bins(frame: pd.DataFrame) -> list[dict[str, object]]:
    watch = frame[frame["verdict"] == "WATCH"].copy()
    if watch.empty:
        return []
    bins = [-1.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 10_000.0]
    labels = ["<=40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100", "100+"]
    watch["watch_score_bin"] = pd.cut(watch["watch_score"], bins=bins, labels=labels)
    grouped = (
        watch.groupby("watch_score_bin", observed=False)
        .agg(
            n=("ret5_pct", "size"),
            avg_ret5_pct=("ret5_pct", "mean"),
            median_ret5_pct=("ret5_pct", "median"),
            win_rate_pct=("ret5_pct", lambda s: (s > 0).mean() * 100.0),
            surge_rate_pct=("ret5_pct", lambda s: (s >= 20).mean() * 100.0),
        )
        .reset_index()
    )
    grouped = grouped[grouped["n"] > 0].copy()
    grouped["avg_ret5_pct"] = grouped["avg_ret5_pct"].round(3)
    grouped["median_ret5_pct"] = grouped["median_ret5_pct"].round(3)
    grouped["win_rate_pct"] = grouped["win_rate_pct"].round(1)
    grouped["surge_rate_pct"] = grouped["surge_rate_pct"].round(1)
    grouped["watch_score_bin"] = grouped["watch_score_bin"].astype(str)
    return grouped.where(pd.notna(grouped), None).to_dict(orient="records")


def _fail_interval_tests(frame: pd.DataFrame) -> list[dict[str, object]]:
    fail = frame[frame["verdict"] == "FAIL"].copy()
    rules = [
        ("box_position<=0.35", fail["box_position"] <= 0.35),
        ("box_position<=0.40", fail["box_position"] <= 0.40),
        ("box_position<=0.50", fail["box_position"] <= 0.50),
        ("close_box_position<=0.40", fail["close_box_position"] <= 0.40),
        ("close_box_position<=0.50", fail["close_box_position"] <= 0.50),
        ("box_range_pct>=80", fail["box_range_pct"] >= 80.0),
        ("box_range_pct>=120", fail["box_range_pct"] >= 120.0),
        (
            "box_position<=0.40 & box_range_pct>=80",
            (fail["box_position"] <= 0.40) & (fail["box_range_pct"] >= 80.0),
        ),
        (
            "box_position<=0.35 & box_range_pct>=80",
            (fail["box_position"] <= 0.35) & (fail["box_range_pct"] >= 80.0),
        ),
    ]
    rows: list[dict[str, object]] = []
    for rule_name, mask in rules:
        subset = fail[mask].copy()
        if subset.empty:
            continue
        rows.append({"rule_name": rule_name, **_return_stats(subset)})
    return rows


def _candidate_playbacks(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    candidates = {
        "B2_rebound_A_clean_all": (frame["signal"] == "B2")
        & (frame["signal_type"] == "rebound")
        & (frame["override_bucket"] == "A-clean"),
        "B2_rebound_A_clean_macd_lt_3_8": (frame["signal"] == "B2")
        & (frame["signal_type"] == "rebound")
        & (frame["override_bucket"] == "A-clean")
        & (frame["macd_phase"] < 3.8),
        "B2_trend_start_A_borderline": (frame["signal"] == "B2")
        & (frame["signal_type"] == "trend_start")
        & (frame["override_bucket"] == "A-borderline"),
        "B2_trend_start_A_borderline_slope_nonneg": (frame["signal"] == "B2")
        & (frame["signal_type"] == "trend_start")
        & (frame["override_bucket"] == "A-borderline")
        & (frame["zxdq_5d_slope_pct"] >= 0.0),
        "B2_rebound_watch_c": (frame["signal"] == "B2")
        & (frame["signal_type"] == "rebound")
        & (frame["watch_tier"] == "WATCH-C"),
        "B2_trend_start_watch_b_macd_lt_4_0": (frame["signal"] == "B2")
        & (frame["signal_type"] == "trend_start")
        & (frame["watch_tier"] == "WATCH-B")
        & (frame["macd_phase"] < 4.0),
        "FAIL_left_box_rebound": (frame["verdict"] == "FAIL")
        & (frame["signal_type"] == "rebound")
        & (frame["box_position"] <= 0.35),
        "FAIL_left_box_rebound_prev5": (frame["verdict"] == "FAIL")
        & (frame["signal_type"] == "rebound")
        & (frame["box_position"] <= 0.35)
        & (frame["previous_abnormal_move"] >= 5.0),
    }
    payload: dict[str, dict[str, object]] = {}
    for name, mask in candidates.items():
        subset = frame[mask].copy()
        payload[name] = _return_stats(subset)
    return payload


def build_summary(frame: pd.DataFrame, *, top_n: int = 50) -> dict[str, object]:
    verdict_stats = {
        str(verdict): _score_stats(subset)
        for verdict, subset in frame.groupby("verdict")
    }
    watch_tier_stats = {
        str(tier): _return_stats(subset)
        for tier, subset in frame[frame["verdict"] == "WATCH"].groupby("watch_tier")
    }
    contradictions = {
        "pass_but_weak": _records(frame[(frame["verdict"] == "PASS") & (frame["ret5_pct"] < 0.0)].sort_values("ret5_pct")),
        "watch_but_surge": _records(frame[(frame["verdict"] == "WATCH") & (frame["ret5_pct"] >= 20.0)].sort_values("ret5_pct", ascending=False)),
        "fail_but_surge": _records(frame[(frame["verdict"] == "FAIL") & (frame["ret5_pct"] >= 20.0)].sort_values("ret5_pct", ascending=False)),
    }
    fail = frame[frame["verdict"] == "FAIL"].copy()
    fail_quantiles = {
        "all_fail": {
            "box_position": _quantiles(fail["box_position"]),
            "close_box_position": _quantiles(fail["close_box_position"]),
            "box_range_pct": _quantiles(fail["box_range_pct"]),
            "zxdq_5d_slope_pct": _quantiles(fail["zxdq_5d_slope_pct"]),
            "zxdkx_5d_slope_pct": _quantiles(fail["zxdkx_5d_slope_pct"]),
        },
        "fail_surge": {
            "box_position": _quantiles(fail.loc[fail["ret5_pct"] >= 20.0, "box_position"]),
            "close_box_position": _quantiles(fail.loc[fail["ret5_pct"] >= 20.0, "close_box_position"]),
            "box_range_pct": _quantiles(fail.loc[fail["ret5_pct"] >= 20.0, "box_range_pct"]),
            "zxdq_5d_slope_pct": _quantiles(fail.loc[fail["ret5_pct"] >= 20.0, "zxdq_5d_slope_pct"]),
            "zxdkx_5d_slope_pct": _quantiles(fail.loc[fail["ret5_pct"] >= 20.0, "zxdkx_5d_slope_pct"]),
        },
        "fail_down": {
            "box_position": _quantiles(fail.loc[fail["ret5_pct"] < 0.0, "box_position"]),
            "close_box_position": _quantiles(fail.loc[fail["ret5_pct"] < 0.0, "close_box_position"]),
            "box_range_pct": _quantiles(fail.loc[fail["ret5_pct"] < 0.0, "box_range_pct"]),
            "zxdq_5d_slope_pct": _quantiles(fail.loc[fail["ret5_pct"] < 0.0, "zxdq_5d_slope_pct"]),
            "zxdkx_5d_slope_pct": _quantiles(fail.loc[fail["ret5_pct"] < 0.0, "zxdkx_5d_slope_pct"]),
        },
    }
    return {
        "sample_count": int(len(frame)),
        "verdict_stats": verdict_stats,
        "watch_tier_stats": watch_tier_stats,
        "contradictions": contradictions,
        "top_bottom": {
            "top": _top_bottom_block(frame, top_n=top_n, ascending=False),
            "bottom": _top_bottom_block(frame, top_n=top_n, ascending=True),
        },
        "combo_stats": {
            "signal_signal_type_verdict": _group_stats(frame, ["signal", "signal_type", "verdict"]),
            "signal_signal_type_watch_tier": _group_stats(frame[frame["verdict"] == "WATCH"], ["signal", "signal_type", "watch_tier"]),
            "signal_signal_type_override": _group_stats(frame, ["signal", "signal_type", "override_bucket"]),
        },
        "watch_score_bins": _watch_score_bins(frame),
        "fail_quantiles": fail_quantiles,
        "fail_interval_tests": _fail_interval_tests(frame),
        "candidate_playbacks": _candidate_playbacks(frame),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze b2 weak dataset and emit summary JSON")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-n", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = pd.read_csv(args.dataset)
    payload = build_summary(frame, top_n=args.top_n)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
