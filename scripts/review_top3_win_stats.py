from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_TOP_N = 3


def load_dotenv_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        candidate_key, candidate_value = line.split("=", 1)
        if candidate_key.strip() != key:
            continue
        value = candidate_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def resolve_dsn(cli_dsn: str | None) -> str:
    project_root = Path(__file__).resolve().parents[1]
    for value in (cli_dsn, os.getenv("POSTGRES_DSN"), load_dotenv_value(project_root / ".env", "POSTGRES_DSN")):
        if value and value.strip():
            return value.strip()
    raise ValueError("A database DSN is required.")


def normalize_method(value: str) -> str:
    return value.strip().lower()


def normalize_environment(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def collect_pass_top_reviews(summary: dict[str, object], *, top_n: int = DEFAULT_TOP_N) -> list[dict[str, object]]:
    candidates = []
    for section in ("recommendations", "excluded"):
        values = summary.get(section, [])
        if isinstance(values, list):
            candidates.extend(item for item in values if isinstance(item, dict))
    passes = [item for item in candidates if str(item.get("verdict", "")).upper() == "PASS"]
    return sorted(passes, key=lambda item: float(item.get("total_score", 0.0)), reverse=True)[:top_n]


def fetch_price_rows(dsn: str, symbols: Sequence[str], start_date: str, end_date: str) -> list[dict[str, object]]:
    import psycopg

    if not symbols:
        return []
    query = """
        SELECT ts_code, trade_date, open::double precision AS open, close::double precision AS close
        FROM daily_market
        WHERE ts_code = ANY(%s)
          AND trade_date BETWEEN %s AND %s
        ORDER BY ts_code ASC, trade_date ASC
    """
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(symbols), start_date, end_date))
            return [
                {
                    "ts_code": row[0],
                    "trade_date": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
                    "open": row[2],
                    "close": row[3],
                }
                for row in cursor.fetchall()
            ]


def get_forward_data(rows: Sequence[dict[str, object]], code: str, pick_date: str) -> dict[str, object] | None:
    history = sorted(
        (row for row in rows if str(row.get("ts_code")) == code),
        key=lambda row: str(row.get("trade_date")),
    )
    current = [row for row in history if str(row.get("trade_date")) <= pick_date]
    if not current:
        return None
    entry_close = float(current[-1]["close"])
    if entry_close == 0:
        return None
    future = [row for row in history if str(row.get("trade_date")) > pick_date]
    result: dict[str, object] = {"entry_close": entry_close}
    if future:
        next_open = float(future[0]["open"])
        open_gap_pct = round((next_open / entry_close - 1.0) * 100, 2)
        result["next_date"] = str(future[0]["trade_date"])
        result["open_gap_pct"] = open_gap_pct
        result["open_class"] = "high" if open_gap_pct > 0.05 else "low" if open_gap_pct < -0.05 else "flat"
    else:
        result["open_gap_pct"] = None
        result["open_class"] = "missing"
    if len(future) >= 3:
        ret3 = round((float(future[2]["close"]) / entry_close - 1.0) * 100, 2)
        result["ret3_pct"] = ret3
        result["win_ret3"] = ret3 > 0
    else:
        result["ret3_pct"] = None
        result["win_ret3"] = None
    if len(future) >= 5:
        ret5 = round((float(future[4]["close"]) / entry_close - 1.0) * 100, 2)
        result["ret5_pct"] = ret5
        result["win_ret5"] = ret5 > 0
    else:
        result["ret5_pct"] = None
        result["win_ret5"] = None
    return result


def load_environment_by_date(runtime_root: Path) -> dict[str, str]:
    daily_dir = runtime_root / "environment" / "daily"
    result: dict[str, str] = {}
    if not daily_dir.exists():
        return result
    for path in sorted(daily_dir.glob("????-??-??.*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        pick_date = str(payload.get("pick_date") or path.name[:10])
        state = normalize_environment(payload.get("state"))
        if state:
            result[pick_date] = state
    return result


def collect_runtime_records(
    *,
    method: str,
    start_date: str,
    end_date: str,
    runtime_root: Path,
    price_rows: Sequence[dict[str, object]],
    top_n: int,
    environment_state: str | None = None,
) -> list[dict[str, object]]:
    normalized_method = normalize_method(method)
    env_by_date = load_environment_by_date(runtime_root)
    env_filter = normalize_environment(environment_state)
    records: list[dict[str, object]] = []
    for review_dir in sorted((runtime_root / "reviews").glob(f"????-??-??.{normalized_method}")):
        pick_date = review_dir.name.removesuffix(f".{normalized_method}")
        if pick_date < start_date or pick_date > end_date:
            continue
        summary_path = review_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_pick_date = str(summary.get("pick_date") or pick_date)
        environment = env_by_date.get(summary_pick_date)
        if env_filter is not None and normalize_environment(environment) != env_filter:
            continue
        for rank, item in enumerate(collect_pass_top_reviews(summary, top_n=top_n), start=1):
            code = str(item.get("code", "")).strip()
            if not code:
                continue
            fwd = get_forward_data(price_rows, code, summary_pick_date)
            if fwd is None:
                continue
            records.append(
                {
                    "method": normalized_method,
                    "pick_date": summary_pick_date,
                    "code": code,
                    "rank": rank,
                    "total_score": float(item.get("total_score", 0.0)),
                    "environment_state": environment,
                    **fwd,
                }
            )
    return records


def summarize_win_metrics(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str | None], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[(normalize_method(str(record.get("method", ""))), normalize_environment(record.get("environment_state")))].append(record)
    rows: list[dict[str, object]] = []
    for (method, environment_state), items in sorted(grouped.items(), key=lambda item: item[0]):
        ret3_values = [float(item["ret3_pct"]) for item in items if item.get("ret3_pct") is not None]
        ret5_values = [float(item["ret5_pct"]) for item in items if item.get("ret5_pct") is not None]
        dates = sorted({str(item.get("pick_date", "")) for item in items})
        day_hit_ret3 = 0
        day_count_ret3 = 0
        day_hit_ret5 = 0
        day_count_ret5 = 0
        for pick_date in dates:
            day_items = [item for item in items if str(item.get("pick_date")) == pick_date]
            day_ret3 = [float(item["ret3_pct"]) for item in day_items if item.get("ret3_pct") is not None]
            day_ret5 = [float(item["ret5_pct"]) for item in day_items if item.get("ret5_pct") is not None]
            if day_ret3:
                day_count_ret3 += 1
                day_hit_ret3 += int(any(value > 0 for value in day_ret3))
            if day_ret5:
                day_count_ret5 += 1
                day_hit_ret5 += int(any(value > 0 for value in day_ret5))
        rows.append(
            {
                "method": method,
                "environment_state": environment_state,
                "record_count": len(items),
                "review_count": len(dates),
                "win_rate_ret3_pct": round(sum(1 for value in ret3_values if value > 0) / len(ret3_values) * 100, 1) if ret3_values else None,
                "win_rate_ret5_pct": round(sum(1 for value in ret5_values if value > 0) / len(ret5_values) * 100, 1) if ret5_values else None,
                "day_hit_rate_ret3_pct": round(day_hit_ret3 / day_count_ret3 * 100, 1) if day_count_ret3 else None,
                "day_hit_rate_ret5_pct": round(day_hit_ret5 / day_count_ret5 * 100, 1) if day_count_ret5 else None,
            }
        )
    return rows


def collect_symbols_from_reviews(runtime_root: Path, method: str, start_date: str, end_date: str, top_n: int) -> list[str]:
    symbols: set[str] = set()
    normalized_method = normalize_method(method)
    for review_dir in sorted((runtime_root / "reviews").glob(f"????-??-??.{normalized_method}")):
        pick_date = review_dir.name.removesuffix(f".{normalized_method}")
        if pick_date < start_date or pick_date > end_date:
            continue
        summary_path = review_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for item in collect_pass_top_reviews(summary, top_n=top_n):
            code = str(item.get("code", "")).strip()
            if code:
                symbols.add(code)
    return sorted(symbols)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PASS topN win-rate stats for Rust review runtime artifacts")
    parser.add_argument("--method", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--dsn")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--environment-state")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def print_summary(rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        print("No PASS topN records found for the requested filters.")
        return
    print("method\tenvironment_state\trecord_count\treview_count\twin_rate_ret3_pct\twin_rate_ret5_pct\tday_hit_rate_ret3_pct\tday_hit_rate_ret5_pct")
    for row in rows:
        print(
            "\t".join(
                str(row.get(key) if row.get(key) is not None else "-")
                for key in (
                    "method",
                    "environment_state",
                    "record_count",
                    "review_count",
                    "win_rate_ret3_pct",
                    "win_rate_ret5_pct",
                    "day_hit_rate_ret3_pct",
                    "day_hit_rate_ret5_pct",
                )
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top_n <= 0:
        raise SystemExit("--top-n must be positive.")
    dsn = resolve_dsn(args.dsn)
    symbols = collect_symbols_from_reviews(args.runtime_root, args.method, args.start_date, args.end_date, args.top_n)
    price_rows = fetch_price_rows(dsn, symbols, args.start_date, date.today().isoformat())
    records = collect_runtime_records(
        method=args.method,
        start_date=args.start_date,
        end_date=args.end_date,
        runtime_root=args.runtime_root,
        price_rows=price_rows,
        top_n=args.top_n,
        environment_state=args.environment_state,
    )
    summary = summarize_win_metrics(records)
    payload = {"records": records, "summary": summary}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
