from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = Path(
    "/home/pi/.agents/skills/stock-select/runtime/research/review_tuning/b2_macd_category_corr_2026_fast"
)
DEFAULT_NOTES_PATH = DEFAULT_ARTIFACT_DIR / "macd_review_notes.md"
DEFAULT_WORST_CSV_PATH = DEFAULT_ARTIFACT_DIR / "worst_negative_category_samples.csv"


@dataclass(frozen=True)
class ReviewSample:
    code: str
    pick_date: str
    source: str
    signal: str = ""
    signal_type: str = ""
    verdict: str = ""
    total_score: float | None = None
    ret5_pct: float | None = None
    macd_category: str = ""
    manual_note: str = ""


@dataclass(frozen=True)
class ManualExpectation:
    daily_stage: str
    weekly_stage: str
    rating: str
    summary: str


def parse_manual_review_notes(path: Path) -> list[ReviewSample]:
    text = path.read_text(encoding="utf-8")
    header_pattern = re.compile(r"^##\s+\d+\.\s+([0-9]{6}\.(?:SZ|SH|BJ)).*$", re.MULTILINE)
    matches = list(header_pattern.finditer(text))
    samples: list[ReviewSample] = []
    for index, match in enumerate(matches):
        code = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        date_match = re.search(r"\|\s*入选日期\s*\|\s*(\d{4}-\d{2}-\d{2})", block)
        if date_match is None:
            continue
        samples.append(
            ReviewSample(
                code=code,
                pick_date=date_match.group(1),
                source="manual_notes",
                manual_note=_extract_manual_summary(block),
            )
        )
    return samples


def _extract_manual_summary(block: str) -> str:
    marker_match = re.search(r"^###\s+用户(?:转述)?判断\s*$", block, flags=re.MULTILINE)
    if marker_match is None:
        return ""
    section = block[marker_match.end() :]
    section = section.split("###", 1)[0]
    lines = [line.strip("> ").strip() for line in section.splitlines()]
    return " ".join(line for line in lines if line)[:500]


def load_worst_negative_samples(path: Path, *, sample_size: int | None = None, seed: int = 20260511) -> list[ReviewSample]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if sample_size is not None and sample_size > 0 and len(rows) > sample_size:
        rows = random.Random(seed).sample(rows, sample_size)
    samples: list[ReviewSample] = []
    for row in rows:
        samples.append(
            ReviewSample(
                code=str(row.get("code", "")).strip(),
                pick_date=str(row.get("pick_date", "")).strip(),
                source="worst_negative_csv",
                signal=str(row.get("signal", "")).strip(),
                signal_type=str(row.get("signal_type", "")).strip(),
                verdict=str(row.get("verdict", "")).strip(),
                total_score=_to_float_or_none(row.get("total_score")),
                ret5_pct=_to_float_or_none(row.get("ret5_pct")),
                macd_category=str(row.get("macd_category", "")).strip(),
            )
        )
    return [sample for sample in samples if sample.code and sample.pick_date]


def _to_float_or_none(value: object) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def infer_manual_expectation(sample: ReviewSample) -> ManualExpectation:
    note = sample.manual_note
    daily_stage = "unknown"
    weekly_stage = "unknown"
    rating = "unknown"

    if any(token in note for token in ("三浪启动", "上涨浪起点", "不严格的三浪启动")):
        daily_stage = "odd_start"
    elif any(token in note for token in ("二浪调整修复阶段，还未启动", "二浪调整未启动")):
        daily_stage = "wave2_repair"
    elif any(token in note for token in ("二浪回调末", "二浪回调末期", "2浪末", "二浪底分型")):
        daily_stage = "wave2_end"

    if any(token in note for token in ("未上水的强化", "未上水强化", "水下推升", "水下，正向")):
        weekly_stage = "underwater_strengthening"
    elif any(token in note for token in ("脱离底背离", "上行阶段", "一浪第一阶段", "一浪启动后正在强化")):
        weekly_stage = "strengthening"
    elif any(token in note for token in ("周MACD水下", "周线水下", "水下高风险", "水下，正向")):
        weekly_stage = "underwater"
    elif "顶背离" in note:
        weekly_stage = "top_divergence_risk"

    if "FAIL是没问题" in note or "FAIL没问题" in note:
        rating = "fail"
    elif "pass" in note.lower():
        rating = "pass"
    elif "watch" in note.lower() or "观察" in note:
        rating = "watch"
    elif "高分" in note or "绝对的机会" in note:
        rating = "strong_opportunity"
    elif daily_stage in {"wave2_end", "odd_start"}:
        rating = "opportunity"

    return ManualExpectation(
        daily_stage=daily_stage,
        weekly_stage=weekly_stage,
        rating=rating,
        summary=note[:200],
    )


def classify_observed_daily_stage(state: dict[str, object]) -> str:
    current_state = str(state.get("current_state", ""))
    current_wave_index = int(state.get("current_wave_index") or 0)
    even_repair_started = bool(state.get("even_repair_started"))
    golden_cross_imminent = bool(state.get("golden_cross_imminent"))

    if current_state == "even_wave_forming":
        if golden_cross_imminent:
            return "odd_start_imminent" if current_wave_index == 2 else "odd_start_imminent"
        if even_repair_started:
            return "wave2_repair" if current_wave_index == 2 else "even_repair"
        return "wave2_adjusting" if current_wave_index == 2 else "even_adjusting"
    if current_state == "odd_wave_forming":
        return "odd_start" if current_wave_index >= 3 else "wave1_forming"
    if current_state in {"pre_odd_pushing", "pre_wave1_pushing"}:
        return "pre_odd_pushing"
    if current_state == "pre_odd_adjusting":
        return "pre_odd_adjusting"
    return current_state or "unknown"


def build_alignment(sample: ReviewSample, daily_state: dict[str, object], weekly_state: dict[str, object]) -> dict[str, object]:
    expectation = infer_manual_expectation(sample)
    observed_daily_stage = classify_observed_daily_stage(daily_state)
    equivalent_pairs = {
        ("wave2_end", "wave2_repair"),
        ("wave2_repair", "wave2_end"),
        ("odd_start", "odd_start_imminent"),
        ("odd_start_imminent", "odd_start"),
        ("odd_start", "wave2_repair"),
        ("odd_start", "even_repair"),
    }
    daily_match = observed_daily_stage == expectation.daily_stage or (
        expectation.daily_stage,
        observed_daily_stage,
    ) in equivalent_pairs
    if expectation.daily_stage == "wave2_end" and observed_daily_stage == "wave2_adjusting":
        daily_alignment = "near"
    elif expectation.daily_stage == "odd_start" and observed_daily_stage in {"wave1_forming", "pre_odd_pushing"}:
        daily_alignment = "near"
    else:
        daily_alignment = "match" if daily_match else "mismatch"
    return {
        "manual_expectation": asdict(expectation),
        "observed_daily_stage": observed_daily_stage,
        "daily_alignment": daily_alignment,
        "weekly_state": weekly_state.get("current_state"),
    }


def summarize_alignments(results: Sequence[dict[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {
        "total": len(results),
        "match": 0,
        "near": 0,
        "mismatch": 0,
        "unknown": 0,
        "mismatches": [],
        "near_samples": [],
    }
    mismatches: list[str] = []
    near_samples: list[str] = []
    for result in results:
        alignment = result.get("alignment")
        status = "unknown"
        if isinstance(alignment, dict):
            status = str(alignment.get("daily_alignment") or "unknown")
        if status not in {"match", "near", "mismatch"}:
            status = "unknown"
        summary[status] = int(summary[status]) + 1
        sample_key = f"{result.get('code')}@{result.get('pick_date')}"
        if status == "mismatch":
            mismatches.append(sample_key)
        elif status == "near":
            near_samples.append(sample_key)
    summary["mismatches"] = mismatches
    summary["near_samples"] = near_samples
    return summary


def resolve_script_dsn(cli_dsn: str | None) -> str:
    from stock_select.db_access import load_dotenv_value, resolve_dsn

    dotenv_dsn = load_dotenv_value(PROJECT_ROOT / ".env", "POSTGRES_DSN")
    return resolve_dsn(cli_dsn, os.getenv("POSTGRES_DSN"), dotenv_dsn)


def analyze_sample(connection, sample: ReviewSample, *, lookback_days: int) -> dict[str, object]:
    from stock_select.analysis.macd_waves import classify_macd_state_from_lines
    from stock_select.db_access import fetch_symbol_history
    from stock_select.indicators import compute_macd

    end = pd.Timestamp(sample.pick_date)
    start = end - pd.Timedelta(days=lookback_days)
    history = fetch_symbol_history(
        connection,
        symbol=sample.code,
        start_date=str(start.date()),
        end_date=sample.pick_date,
    )
    if history.empty:
        return {**asdict(sample), "error": "missing history"}
    daily_macd = compute_macd(history[["close"]].astype(float))
    daily_state = classify_macd_state_from_lines(daily_macd[["dif", "dea"]])

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
    daily_state_dict = asdict(daily_state)
    weekly_state_dict = asdict(weekly_state)

    return {
        **asdict(sample),
        "history_rows": int(len(history)),
        "daily_state": daily_state_dict,
        "weekly_state": weekly_state_dict,
        "alignment": build_alignment(sample, daily_state_dict, weekly_state_dict),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated MACD state-machine review samples.")
    parser.add_argument("--notes-path", type=Path, default=DEFAULT_NOTES_PATH)
    parser.add_argument("--worst-csv-path", type=Path, default=DEFAULT_WORST_CSV_PATH)
    parser.add_argument("--source", choices=("manual", "worst", "both"), default="manual")
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--seed", type=int, default=20260511)
    parser.add_argument("--lookback-days", type=int, default=420)
    parser.add_argument("--dsn")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    return parser.parse_args(argv)


def collect_samples(args: argparse.Namespace) -> list[ReviewSample]:
    samples: list[ReviewSample] = []
    if args.source in {"manual", "both"}:
        samples.extend(parse_manual_review_notes(args.notes_path))
    if args.source in {"worst", "both"}:
        samples.extend(load_worst_negative_samples(args.worst_csv_path, sample_size=args.sample_size, seed=args.seed))
    seen: set[tuple[str, str, str]] = set()
    unique: list[ReviewSample] = []
    for sample in samples:
        key = (sample.source, sample.code, sample.pick_date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(sample)
    return unique


def main(argv: Sequence[str] | None = None) -> int:
    import psycopg

    args = parse_args(argv)
    samples = collect_samples(args)
    dsn = resolve_script_dsn(args.dsn)
    with psycopg.connect(dsn) as connection:
        results = [analyze_sample(connection, sample, lookback_days=args.lookback_days) for sample in samples]
    payload: list[dict[str, object]] = results
    if args.summary:
        payload = [*results, {"alignment_summary": summarize_alignments(results)}]
    lines = [json.dumps(result, ensure_ascii=False, sort_keys=True) for result in payload]
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        for line in lines:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
