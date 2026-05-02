from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.cli import _load_prepared_cache_v2


REVIEWS_DIR = Path("/home/pi/.agents/skills/stock-select/runtime/reviews")
PREPARED_DIR = Path("/home/pi/.agents/skills/stock-select/runtime/prepared")
SHARED_PREPARED_METHODS = {"b1", "b2", "dribull"}


def collect_pass_top_reviews(summary: dict, *, top_n: int = 3) -> list[dict]:
    candidates = summary.get("recommendations", []) + summary.get("excluded", [])
    passes = [item for item in candidates if str(item.get("verdict", "")).upper() == "PASS"]
    return sorted(
        passes,
        key=lambda item: float(item.get("total_score", 0)),
        reverse=True,
    )[:top_n]


def load_prepared(method: str) -> pd.DataFrame:
    normalized_method = method.strip().lower()
    if normalized_method in SHARED_PREPARED_METHODS:
        feather_pattern = "*-*-*.feather"
        ignored_feather_suffixes = {".hcr.feather"}
    else:
        feather_pattern = f"*-*-*.{normalized_method}.feather"
        ignored_feather_suffixes = set()

    candidates: list[Path] = []
    for path in sorted(PREPARED_DIR.glob(feather_pattern)):
        if any(path.name.endswith(suffix) for suffix in ignored_feather_suffixes):
            continue
        candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            f"No prepared cache matching {feather_pattern} in {PREPARED_DIR}"
        )

    data_path = sorted(candidates)[-1]
    payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError("Prepared cache prepared_table missing.")
    return prepared


def get_forward_data(
    prepared: pd.DataFrame,
    code: str,
    pick_date: str,
) -> dict:
    if prepared.empty or "ts_code" not in prepared.columns:
        return None
    df = prepared.loc[prepared["ts_code"] == code].copy()
    if df.empty:
        return None
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce", format="mixed")
    df = df.sort_values("trade_date").reset_index(drop=True)
    for col in ["open", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    cutoff = pd.Timestamp(pick_date)
    cur = df[df["trade_date"] <= cutoff].tail(1)
    if cur.empty:
        return None

    entry_close = float(cur.iloc[0]["close"])
    future = df[df["trade_date"] > cutoff]

    result = {"entry_close": entry_close}

    # Next-day open gap
    if not future.empty:
        nxt = future.iloc[0]
        gap_pct = (float(nxt["open"]) / entry_close - 1.0) * 100
        result["next_date"] = str(nxt["trade_date"]).split()[0]
        result["next_open"] = round(float(nxt["open"]), 2)
        result["open_gap_pct"] = round(gap_pct, 2)
        if gap_pct > 0.05:
            result["open_class"] = "high"
        elif gap_pct < -0.05:
            result["open_class"] = "low"
        else:
            result["open_class"] = "flat"
    else:
        result["open_gap_pct"] = None
        result["open_class"] = "missing"

    # 3-day forward return
    if len(future) >= 3:
        exit3 = float(future.iloc[2]["close"])
        result["ret3_pct"] = round((exit3 / entry_close - 1.0) * 100, 2)
        result["exit3_date"] = str(future.iloc[2]["trade_date"]).split()[0]
    else:
        result["ret3_pct"] = None

    # 5-day forward return
    if len(future) >= 5:
        exit5 = float(future.iloc[4]["close"])
        result["ret5_pct"] = round((exit5 / entry_close - 1.0) * 100, 2)
        result["exit5_date"] = str(future.iloc[4]["trade_date"]).split()[0]
    else:
        result["ret5_pct"] = None

    return result


def run(method: str, start_date: str, end_date: str) -> None:
    prepared = load_prepared(method)
    records = []

    # Gather all review directories within range
    review_dirs = sorted(REVIEWS_DIR.glob(f"????-??-??.{method}"))
    for rd in review_dirs:
        dt_str = rd.name.replace(f".{method}", "")
        if dt_str < start_date or dt_str > end_date:
            continue
        summary_path = rd / "summary.json"
        if not summary_path.exists():
            continue

        summary = json.loads(summary_path.read_text())
        pick_date = summary["pick_date"]

        top3 = collect_pass_top_reviews(summary, top_n=3)
        if not top3:
            continue

        for rank, s in enumerate(top3, 1):
            code = s["code"]
            score = float(s.get("total_score", 0))
            fwd = get_forward_data(prepared, code, pick_date)
            if fwd is None:
                continue

            records.append({
                "pick_date": pick_date,
                "code": code,
                "rank": rank,
                "score": score,
                "open_gap_pct": fwd.get("open_gap_pct"),
                "open_class": fwd.get("open_class", "missing"),
                "ret3_pct": fwd.get("ret3_pct"),
                "ret5_pct": fwd.get("ret5_pct"),
            })

    if not records:
        print(f"No PASS records found for method={method} date=[{start_date}, {end_date}]")
        return

    # Diagnostics: how many top3 entries were skipped for missing forward data
    total_raw = 0
    total_skipped = 0
    for rd in review_dirs:
        dt_str = rd.name.replace(f".{method}", "")
        if dt_str < start_date or dt_str > end_date:
            continue
        summary_path = rd / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text())
        top3 = collect_pass_top_reviews(summary, top_n=3)
        total_raw += len(top3)
        for s in top3:
            fwd = get_forward_data(prepared, s["code"], summary["pick_date"])
            if fwd is None:
                total_skipped += 1
    if total_skipped:
        print(f"  (skipped {total_skipped}/{total_raw} top3 entries — insufficient history for forward computation)")
    else:
        print(f"  (all {total_raw} top3 entries have full forward data)")

    # Stats helpers
    def gap_stats(items):
        valid = [r for r in items if r["open_gap_pct"] is not None]
        if not valid:
            return {}
        gaps = [r["open_gap_pct"] for r in valid]
        classes = Counter(r["open_class"] for r in valid)
        return {
            "n": len(valid),
            "high": classes.get("high", 0),
            "low": classes.get("low", 0),
            "flat": classes.get("flat", 0),
            "high_pct": round(classes.get("high", 0) / len(valid) * 100, 1),
            "low_pct": round(classes.get("low", 0) / len(valid) * 100, 1),
            "avg_gap": round(sum(gaps) / len(gaps), 2),
            "median_gap": round(statistics.median(gaps), 2),
        }

    def ret_stats(items, key):
        valid = [r for r in items if r[key] is not None]
        if not valid:
            return {}
        rets = [r[key] for r in valid]
        wins = sum(1 for v in rets if v > 0)
        return {
            "n": len(valid),
            "win": wins,
            "loss": len(valid) - wins,
            "win_pct": round(wins / len(valid) * 100, 1),
            "avg_ret": round(sum(rets) / len(rets), 2),
            "median_ret": round(statistics.median(rets), 2),
            "max_ret": round(max(rets), 2),
            "min_ret": round(min(rets), 2),
        }

    # Overall top3 stats
    all_scores = [r["score"] for r in records]
    print(f"\n{'='*60}")
    print(f"  Method: {method}")
    print(f"  Date range: {start_date} ~ {end_date}")
    print(f"  Total top3 records: {len(records)}")
    print(f"  Score range: {min(all_scores):.2f} ~ {max(all_scores):.2f}  (avg {sum(all_scores)/len(all_scores):.2f})")
    print(f"{'='*60}")

    print(f"\n--- Open Gap (top3) ---")
    g = gap_stats(records)
    if g:
        print(f"  n={g['n']}  high={g['high']}({g['high_pct']}%)  low={g['low']}({g['low_pct']}%)  flat={g['flat']}")
        print(f"  avg_gap={g['avg_gap']}%  median_gap={g['median_gap']}%")

    print(f"\n--- 3-Day Return (top3) ---")
    r3 = ret_stats(records, "ret3_pct")
    if r3:
        print(f"  n={r3['n']}  win={r3['win']}({r3['win_pct']}%)  loss={r3['loss']}")
        print(f"  avg={r3['avg_ret']}%  median={r3['median_ret']}%  max={r3['max_ret']}%  min={r3['min_ret']}%")

    print(f"\n--- 5-Day Return (top3) ---")
    r5 = ret_stats(records, "ret5_pct")
    if r5:
        print(f"  n={r5['n']}  win={r5['win']}({r5['win_pct']}%)  loss={r5['loss']}")
        print(f"  avg={r5['avg_ret']}%  median={r5['median_ret']}%  max={r5['max_ret']}%  min={r5['min_ret']}%")

    # By rank
    print(f"\n--- By Rank ---")
    for rk in [1, 2, 3]:
        items = [r for r in records if r["rank"] == rk]
        if not items:
            continue
        g2 = gap_stats(items)
        r3b = ret_stats(items, "ret3_pct")
        r5b = ret_stats(items, "ret5_pct")
        print(f"\n  Rank {rk} (n={len(items)}):")
        if g2:
            print(f"    Gap:  avg={g2['avg_gap']}%  high={g2['high_pct']}%  low={g2['low_pct']}%")
        if r3b:
            print(f"    3d:   n={r3b['n']}  avg={r3b['avg_ret']}%  win={r3b['win_pct']}%")
        if r5b:
            print(f"    5d:   n={r5b['n']}  avg={r5b['avg_ret']}%  win={r5b['win_pct']}%")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stats on top-3 PASS stocks by score: forward returns and open gaps"
    )
    parser.add_argument(
        "--method", "-m",
        default="hcr",
        help="Method name (e.g. hcr, b1, b2). Default: hcr",
    )
    parser.add_argument(
        "--start", "-s",
        default="2026-04-01",
        help="Start date (YYYY-MM-DD). Default: 2026-04-01",
    )
    parser.add_argument(
        "--end", "-e",
        default="2026-04-30",
        help="End date (YYYY-MM-DD). Default: 2026-04-30",
    )
    args = parser.parse_args()
    run(args.method, args.start, args.end)


if __name__ == "__main__":
    main()
