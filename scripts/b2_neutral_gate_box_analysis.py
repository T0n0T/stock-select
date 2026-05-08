from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from stock_select.cli import _load_prepared_cache_v2
from stock_select.reviewers.b2 import _resolve_zx_lines, _tail_slope


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_PREPARED_ROOT = DEFAULT_RUNTIME_ROOT / "prepared"


def _load_samples(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    neutral = frame[(frame["environment_state"] == "neutral") & frame["ret5_pct"].notna()].copy()
    neutral["pick_date"] = neutral["pick_date"].astype(str)
    neutral["code"] = neutral["code"].astype(str)
    return neutral


def _load_review_meta(reviews_root: Path) -> dict[tuple[str, str], dict[str, object]]:
    meta: dict[tuple[str, str], dict[str, object]] = {}
    for summary_path in sorted(reviews_root.glob("*.b2/summary.json")):
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        for bucket in ("recommendations", "excluded"):
            for item in payload.get(bucket, []):
                base = item.get("baseline_review") or {}
                pick_date = str(item.get("pick_date") or base.get("pick_date") or "")
                code = str(item.get("code") or base.get("code") or "")
                if not pick_date or not code:
                    continue
                meta[(pick_date, code)] = {
                    "signal": item.get("signal") or base.get("signal"),
                    "signal_type": item.get("signal_type") or base.get("signal_type"),
                    "watch_score": item.get("watch_score") or base.get("watch_score"),
                    "watch_tier": item.get("watch_tier") or base.get("watch_tier"),
                }
    return meta


def _prepared_cache_for_pick_date(prepared_root: Path, pick_date: str, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    candidates = sorted(path for path in prepared_root.glob("*.feather") if path.name <= f"{pick_date}.feather")
    if not candidates:
        raise FileNotFoundError(f"no prepared cache found on or before {pick_date}")
    data_path = candidates[-1]
    cache_key = str(data_path)
    if cache_key not in cache:
        payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
        prepared = payload.get("prepared_table")
        if not isinstance(prepared, pd.DataFrame):
            raise ValueError(f"prepared cache prepared_table missing for {data_path}")
        cache[cache_key] = prepared
    return cache[cache_key]


def _sample_metrics(history: pd.DataFrame) -> dict[str, float | None]:
    history = history.sort_values("trade_date").reset_index(drop=True).copy()
    zxdq, zxdkx = _resolve_zx_lines(history)
    high = history["high"].astype(float)
    low = history["low"].astype(float)
    close = history["close"].astype(float)
    recent_high = high.tail(120).dropna()
    recent_low = low.tail(120).dropna()
    latest_high = float(high.iloc[-1]) if len(high) else float("nan")
    latest_low = float(low.iloc[-1]) if len(low) else float("nan")
    latest_close = float(close.iloc[-1]) if len(close) else float("nan")

    box_high = float(recent_high.max()) if not recent_high.empty else None
    box_low = float(recent_low.min()) if not recent_low.empty else None
    current_mid_price = (latest_high + latest_low) / 2.0 if pd.notna(latest_high) and pd.notna(latest_low) else None
    box_range = (box_high - box_low) if box_high is not None and box_low is not None else None
    box_position = None
    close_box_position = None
    if box_range is not None and box_range > 0 and current_mid_price is not None:
        box_position = (current_mid_price - box_low) / box_range
        close_box_position = (latest_close - box_low) / box_range

    latest_zxdq = float(zxdq.iloc[-1]) if len(zxdq) and pd.notna(zxdq.iloc[-1]) else None
    latest_zxdkx = float(zxdkx.iloc[-1]) if len(zxdkx) and pd.notna(zxdkx.iloc[-1]) else None
    return {
        "zxdq_5d_slope_pct": _tail_slope(zxdq, periods=5) * 100.0 if len(zxdq.dropna()) > 5 else None,
        "zxdkx_5d_slope_pct": _tail_slope(zxdkx, periods=5) * 100.0 if len(zxdkx.dropna()) > 5 else None,
        "latest_zxdq": latest_zxdq,
        "latest_zxdkx": latest_zxdkx,
        "close_vs_zxdq_pct": ((latest_close / latest_zxdq - 1.0) * 100.0) if latest_zxdq and latest_zxdq != 0 else None,
        "close_vs_zxdkx_pct": ((latest_close / latest_zxdkx - 1.0) * 100.0) if latest_zxdkx and latest_zxdkx != 0 else None,
        "box_high": box_high,
        "box_low": box_low,
        "box_range_pct": ((box_high / box_low - 1.0) * 100.0) if box_high and box_low and box_low != 0 else None,
        "current_mid_price": current_mid_price,
        "box_position": box_position,
        "close_box_position": close_box_position,
    }


def build_dataset(*, artifact_dir: Path, prepared_root: Path) -> pd.DataFrame:
    samples = _load_samples(artifact_dir / "samples_with_env.csv")
    review_meta = _load_review_meta(artifact_dir / "reviews")
    prepared_cache: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, object]] = []
    for row in samples.itertuples(index=False):
        prepared = _prepared_cache_for_pick_date(prepared_root, row.pick_date, prepared_cache)
        history = prepared.loc[prepared["ts_code"] == row.code].copy()
        if history.empty:
            continue
        history["trade_date"] = pd.to_datetime(history["trade_date"])
        history = history.loc[history["trade_date"] <= pd.Timestamp(row.pick_date)]
        if history.empty:
            continue
        metrics = _sample_metrics(history)
        meta = review_meta.get((row.pick_date, row.code), {})
        rows.append(
            {
                **row._asdict(),
                **meta,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _summary(frame: pd.DataFrame) -> dict[str, float | int | None]:
    if frame.empty:
        return {"count": 0}
    return {
        "count": int(len(frame)),
        "avg_ret5_pct": round(float(frame["ret5_pct"].mean()), 3),
        "median_ret5_pct": round(float(frame["ret5_pct"].median()), 3),
        "win_rate_pct": round(float((frame["ret5_pct"] > 0).mean() * 100.0), 1),
        "avg_score": round(float(frame["total_score"].mean()), 3),
        "avg_zxdq_5d_slope_pct": round(float(frame["zxdq_5d_slope_pct"].dropna().mean()), 3),
        "avg_box_position": round(float(frame["box_position"].dropna().mean()), 3),
    }


def build_payload(dataset: pd.DataFrame) -> dict[str, object]:
    pass_all = dataset[dataset["verdict"] == "PASS"].copy()
    pass_gate = pass_all[pass_all["zxdq_5d_slope_pct"].fillna(-999.0) >= 0.0].copy()
    pass_blocked = pass_all[pass_all["zxdq_5d_slope_pct"].fillna(-999.0) < 0.0].copy()

    watch_all = dataset[dataset["verdict"] == "WATCH"].copy()
    watch_big = watch_all[watch_all["ret5_pct"] >= 20.0].copy()
    watch_rest = watch_all[watch_all["ret5_pct"] < 20.0].copy()

    fail_all = dataset[dataset["verdict"] == "FAIL"].copy()
    fail_big = fail_all[fail_all["ret5_pct"] >= 20.0].copy()
    fail_negative = fail_all[fail_all["ret5_pct"] < 0.0].copy()

    watch_compare_columns = [
        "total_score",
        "trend_structure",
        "price_position",
        "volume_behavior",
        "previous_abnormal_move",
        "macd_phase",
        "zxdq_5d_slope_pct",
        "zxdkx_5d_slope_pct",
        "box_position",
        "close_box_position",
        "close_vs_zxdq_pct",
        "close_vs_zxdkx_pct",
    ]
    watch_diff = []
    for column in watch_compare_columns:
        if column not in watch_big.columns or column not in watch_rest.columns:
            continue
        big = watch_big[column].dropna()
        rest = watch_rest[column].dropna()
        if big.empty or rest.empty:
            continue
        watch_diff.append(
            {
                "field": column,
                "watch_big_mean": round(float(big.mean()), 3),
                "watch_rest_mean": round(float(rest.mean()), 3),
                "delta": round(float(big.mean() - rest.mean()), 3),
            }
        )
    watch_diff = sorted(watch_diff, key=lambda item: abs(float(item["delta"])), reverse=True)

    fail_quantiles = {}
    for label, frame in [("fail_big", fail_big), ("fail_negative", fail_negative), ("fail_all", fail_all)]:
        if frame.empty:
            fail_quantiles[label] = {}
            continue
        fail_quantiles[label] = {
            "box_position_q10": round(float(frame["box_position"].quantile(0.10)), 3),
            "box_position_q25": round(float(frame["box_position"].quantile(0.25)), 3),
            "box_position_q50": round(float(frame["box_position"].quantile(0.50)), 3),
            "box_position_q75": round(float(frame["box_position"].quantile(0.75)), 3),
            "box_position_q90": round(float(frame["box_position"].quantile(0.90)), 3),
            "close_box_position_q50": round(float(frame["close_box_position"].quantile(0.50)), 3),
            "box_range_pct_q50": round(float(frame["box_range_pct"].quantile(0.50)), 3),
        }

    payload = {
        "pass_gate": {
            "pass_all": _summary(pass_all),
            "pass_gate_keep": _summary(pass_gate),
            "pass_gate_blocked": _summary(pass_blocked),
            "blocked_examples": pass_blocked.sort_values("ret5_pct").head(12)[
                [
                    "pick_date",
                    "code",
                    "signal",
                    "signal_type",
                    "total_score",
                    "ret3_pct",
                    "ret5_pct",
                    "zxdq_5d_slope_pct",
                    "zxdkx_5d_slope_pct",
                    "trend_structure",
                    "price_position",
                    "volume_behavior",
                    "previous_abnormal_move",
                    "macd_phase",
                    "box_position",
                ]
            ].to_dict(orient="records"),
        },
        "watch_distinction": {
            "watch_big": _summary(watch_big),
            "watch_rest": _summary(watch_rest),
            "mean_deltas": watch_diff[:12],
            "big_examples": watch_big.sort_values("ret5_pct", ascending=False).head(12)[
                [
                    "pick_date",
                    "code",
                    "signal",
                    "signal_type",
                    "total_score",
                    "ret3_pct",
                    "ret5_pct",
                    "zxdq_5d_slope_pct",
                    "zxdkx_5d_slope_pct",
                    "trend_structure",
                    "price_position",
                    "volume_behavior",
                    "previous_abnormal_move",
                    "macd_phase",
                    "box_position",
                    "watch_score",
                    "watch_tier",
                ]
            ].to_dict(orient="records"),
        },
        "fail_box": {
            "fail_big": _summary(fail_big),
            "fail_negative": _summary(fail_negative),
            "quantiles": fail_quantiles,
            "big_examples": fail_big.sort_values("ret5_pct", ascending=False).head(12)[
                [
                    "pick_date",
                    "code",
                    "signal",
                    "signal_type",
                    "total_score",
                    "ret3_pct",
                    "ret5_pct",
                    "trend_structure",
                    "price_position",
                    "volume_behavior",
                    "previous_abnormal_move",
                    "macd_phase",
                    "box_position",
                    "close_box_position",
                    "box_high",
                    "box_low",
                    "current_mid_price",
                    "box_range_pct",
                ]
            ].to_dict(orient="records"),
        },
    }
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze b2 neutral gate and box metrics")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--prepared-root", type=Path, default=DEFAULT_PREPARED_ROOT)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_dataset(artifact_dir=args.artifact_dir, prepared_root=args.prepared_root)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output_csv, index=False)
    payload = build_payload(dataset)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output_json)
    print(args.output_csv)


if __name__ == "__main__":
    main()
