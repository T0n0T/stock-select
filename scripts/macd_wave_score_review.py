from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import pandas as pd

from stock_select.analysis.macd_wave_score import derive_macd_wave_stage, score_macd_state_machine_combo
from stock_select.analysis.macd_waves import classify_macd_state_from_lines
from stock_select import db_access
from stock_select.indicators import compute_macd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "runtime"


def _load_state_machine_review_module():
    script_path = Path(__file__).resolve().with_name("macd_state_machine_review.py")
    spec = importlib.util.spec_from_file_location("macd_state_machine_review", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_STATE_MACHINE_REVIEW = _load_state_machine_review_module()
ReviewSample = _STATE_MACHINE_REVIEW.ReviewSample
parse_manual_review_notes = _STATE_MACHINE_REVIEW.parse_manual_review_notes
load_worst_negative_samples = _STATE_MACHINE_REVIEW.load_worst_negative_samples
collect_samples = _STATE_MACHINE_REVIEW.collect_samples
resolve_script_dsn = _STATE_MACHINE_REVIEW.resolve_script_dsn
DEFAULT_NOTES_PATH = _STATE_MACHINE_REVIEW.DEFAULT_NOTES_PATH
DEFAULT_WORST_CSV_PATH = _STATE_MACHINE_REVIEW.DEFAULT_WORST_CSV_PATH


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated MACD wave-score review samples.")
    parser.add_argument("--method", choices=("b1", "b2", "dribull"), default="b2")
    parser.add_argument("--source", choices=("manual", "worst", "both"), default="manual")
    parser.add_argument("--notes-path", type=Path, default=DEFAULT_NOTES_PATH)
    parser.add_argument("--worst-csv-path", type=Path, default=DEFAULT_WORST_CSV_PATH)
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--seed", type=int, default=20260512)
    parser.add_argument("--lookback-days", type=int, default=420)
    parser.add_argument("--dsn")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RUNTIME_ROOT / "research" / "macd_wave_score")
    parser.add_argument("--run-id", default="manual")
    return parser.parse_args(argv)


def compute_weekly_and_daily_stages(history: pd.DataFrame):
    daily_macd = compute_macd(history[["close"]].astype(float))
    daily_state = classify_macd_state_from_lines(daily_macd[["dif", "dea"]])
    daily_stage = derive_macd_wave_stage(
        daily_state,
        latest_dif=float(daily_macd.iloc[-1]["dif"]),
        latest_dea=float(daily_macd.iloc[-1]["dea"]),
        latest_hist=float((daily_macd.iloc[-1]["dif"] - daily_macd.iloc[-1]["dea"]) * 2.0),
    )

    weekly_close = (
        history.assign(trade_date=pd.to_datetime(history["trade_date"]))
        .set_index("trade_date")["close"]
        .astype(float)
        .resample("W-FRI")
        .last()
        .dropna()
    )
    weekly_macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    weekly_state = classify_macd_state_from_lines(weekly_macd[["dif", "dea"]])
    weekly_stage = derive_macd_wave_stage(
        weekly_state,
        latest_dif=float(weekly_macd.iloc[-1]["dif"]),
        latest_dea=float(weekly_macd.iloc[-1]["dea"]),
        latest_hist=float((weekly_macd.iloc[-1]["dif"] - weekly_macd.iloc[-1]["dea"]) * 2.0),
        previous_odd_peak_value=weekly_state.H,
    )
    return weekly_stage, daily_stage


def score_sample(
    connection,
    sample: ReviewSample,
    *,
    method: str,
    lookback_days: int,
) -> dict[str, object]:
    end = pd.Timestamp(sample.pick_date)
    start = end - pd.Timedelta(days=lookback_days)
    history = db_access.fetch_symbol_history(
        connection,
        symbol=sample.code,
        start_date=str(start.date()),
        end_date=sample.pick_date,
    )
    if history.empty:
        return {**asdict(sample), "error": "missing history"}

    weekly_stage, daily_stage = compute_weekly_and_daily_stages(history)
    score = score_macd_state_machine_combo(
        method=method,
        weekly_stage=weekly_stage,
        daily_stage=daily_stage,
        signal=sample.signal or "",
    )
    return {
        **asdict(sample),
        "history_rows": int(len(history)),
        "macd_score": score.score_1_to_5,
        "raw_score": score.raw_score,
        "setup_tag": score.setup_tag,
        "risk_flags": list(score.risk_flags),
        "review_context": score.review_context,
    }


def summarize_scores(results: list[dict[str, object]]) -> dict[str, object]:
    score_buckets = {"1.0-2.4": 0, "2.5-3.3": 0, "3.4-4.1": 0, "4.2-4.6": 0, "4.7-5.0": 0}
    setup_tag_counts: dict[str, int] = {}
    top_samples = sorted(
        (
            {
                "code": str(item.get("code", "")),
                "pick_date": str(item.get("pick_date", "")),
                "macd_score": float(item.get("macd_score", 0.0)),
            }
            for item in results
            if "macd_score" in item
        ),
        key=lambda item: item["macd_score"],
        reverse=True,
    )[:10]
    for item in results:
        score = float(item.get("macd_score", 0.0))
        if score < 2.5:
            score_buckets["1.0-2.4"] += 1
        elif score < 3.4:
            score_buckets["2.5-3.3"] += 1
        elif score < 4.2:
            score_buckets["3.4-4.1"] += 1
        elif score < 4.7:
            score_buckets["4.2-4.6"] += 1
        else:
            score_buckets["4.7-5.0"] += 1
        setup_tag = str(item.get("setup_tag", "")).strip()
        if setup_tag:
            setup_tag_counts[setup_tag] = setup_tag_counts.get(setup_tag, 0) + 1
    return {
        "total": len(results),
        "score_buckets": score_buckets,
        "setup_tag_counts": setup_tag_counts,
        "top_samples": top_samples,
    }


def render_summary_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# MACD Wave Score Summary",
        "",
        f"- total: {summary.get('total', 0)}",
        f"- score_buckets: {json.dumps(summary.get('score_buckets', {}), ensure_ascii=False, sort_keys=True)}",
        f"- setup_tag_counts: {json.dumps(summary.get('setup_tag_counts', {}), ensure_ascii=False, sort_keys=True)}",
    ]
    top_samples = summary.get("top_samples", [])
    if isinstance(top_samples, list) and top_samples:
        lines.append("- top_samples:")
        for item in top_samples:
            lines.append(f"  - {item.get('code')} @ {item.get('pick_date')} score={item.get('macd_score')}")
    return "\n".join(lines) + "\n"


def write_artifacts(*, output_dir: Path, results: list[dict[str, object]], summary: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "macd_score_samples.jsonl"
    summary_path = output_dir / "summary.json"
    markdown_path = output_dir / "summary.md"
    jsonl_lines = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in results]
    jsonl_path.write_text("\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_summary_markdown(summary), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    import psycopg

    args = parse_args(argv)
    samples = collect_samples(args)
    run_dir = args.output_dir / args.run_id
    dsn = resolve_script_dsn(args.dsn)
    with psycopg.connect(dsn) as connection:
        results = [
            score_sample(connection, sample, method=args.method, lookback_days=args.lookback_days)
            for sample in samples
        ]
    summary = summarize_scores(results)
    write_artifacts(output_dir=run_dir, results=results, summary=summary)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
