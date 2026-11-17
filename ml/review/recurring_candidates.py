from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from ml.dates import read_dates_file, validate_date
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import PROJECT_ROOT, candidate_path, select_dir

SUPPORTED_METHODS = {"b2", "b3", "lsh", "scm", "pbm"}
DEFAULT_METHOD = "b2"
DEFAULT_WINDOW = 10
DEFAULT_BINARY = PROJECT_ROOT / "target" / "debug" / "stock-select-rs"


@dataclass(frozen=True)
class CandidateOccurrence:
    pick_date: str
    method: str


def parse_methods(value: str) -> list[str]:
    methods = [item.strip().lower() for item in re.split(r"[\s,]+", value) if item.strip()]
    invalid = [method for method in methods if method not in SUPPORTED_METHODS]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"candidate methods must be b2, b3, lsh, scm, or pbm; got {', '.join(invalid)}"
        )
    return list(dict.fromkeys(methods))


def recent_trade_dates(pick_date: str, trade_dates: Sequence[str], *, window: int) -> list[str]:
    if window < 1:
        raise ValueError("window must be positive")
    normalized_pick_date = validate_date(pick_date)
    dates = sorted(dict.fromkeys(validate_date(item) for item in trade_dates))
    previous_dates = [item for item in dates if item < normalized_pick_date]
    return previous_dates[-window:]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_codes(payload: dict) -> set[str]:
    rows = payload.get("candidates", [])
    if not isinstance(rows, list):
        return set()
    codes: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("code"), str):
            codes.add(row["code"])
    return codes


def collect_candidate_occurrences_from_payloads(
    payloads: Iterable[tuple[str, str, dict]]
) -> dict[str, list[CandidateOccurrence]]:
    occurrences: dict[str, list[CandidateOccurrence]] = defaultdict(list)
    for pick_date, method, payload in payloads:
        for code in sorted(candidate_codes(payload)):
            occurrences[code].append(CandidateOccurrence(pick_date=pick_date, method=method))
    return dict(occurrences)


def collect_candidate_occurrences(
    *,
    runtime_root: Path,
    dates: Sequence[str],
    methods: Sequence[str],
    intraday: bool = False,
) -> dict[str, list[CandidateOccurrence]]:
    payloads: list[tuple[str, str, dict]] = []
    for pick_date in dates:
        for method in methods:
            path = candidate_path(runtime_root, pick_date, method, intraday=intraday)
            if not path.exists():
                continue
            payloads.append((pick_date, method, load_json(path)))
    return collect_candidate_occurrences_from_payloads(payloads)


def review_signal_symbol(action: object) -> str:
    if not isinstance(action, str):
        return "-"
    match action.upper():
        case "KEEP":
            return "\u2191"
        case "CAUTION":
            return "\u2192"
        case "REJECT":
            return "\u2193"
        case _:
            return "-"


def format_score(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.6f}"
    return "-"


def format_repeat_marker(occurrences: Sequence[CandidateOccurrence]) -> str:
    if not occurrences:
        return "-"
    marker = ",".join(f"{item.method}@{item.pick_date}" for item in occurrences)
    return f"repeat:{marker}"


def format_recurring_lines(
    rows: Sequence[dict],
    occurrences: dict[str, list[CandidateOccurrence]],
) -> list[str]:
    lines: list[str] = []
    for row in rows:
        code = str(row.get("code", "-"))
        rank = row.get("model_rank")
        rank_text = str(rank) if rank is not None else "-"
        name = row.get("name") if row.get("name") else "-"
        industry = row.get("industry") if row.get("industry") else "-"
        score = format_score(row.get("model_score"))
        bias = review_signal_symbol(row.get("llm_action"))
        repeat = format_repeat_marker(occurrences.get(code, []))
        lines.append(f"{rank_text}\t{code}\t{name}\t{industry}\t{score}\t{bias}\t{repeat}")
    return lines


def format_recurring_lines_from_review_list(
    review_list_lines: Sequence[str],
    occurrences: dict[str, list[CandidateOccurrence]],
) -> list[str]:
    lines: list[str] = []
    for line in review_list_lines:
        columns = line.rstrip("\n").split("\t")
        if len(columns) < 2:
            continue
        code = columns[1]
        repeat = format_repeat_marker(occurrences.get(code, []))
        lines.append(f"{line.rstrip()}\t{repeat}")
    return lines


def resolve_binary(cli_binary: Path | None) -> Path:
    if cli_binary is not None:
        return cli_binary
    if DEFAULT_BINARY.exists():
        return DEFAULT_BINARY
    return Path("stock-select-rs")


def build_review_list_command(
    *,
    binary: Path,
    runtime_root: Path,
    pick_date: str,
    method: str,
    limit: int | None,
    intraday: bool = False,
) -> list[str]:
    command = [
        str(binary),
        "review-list",
        "--method",
        method,
        "--pick-date",
        pick_date,
        "--runtime-root",
        str(runtime_root),
    ]
    if limit is not None:
        command.extend(["--limit", str(limit)])
    if intraday:
        command.append("--intraday")
    return command


def load_review_list_lines(
    *,
    binary: Path,
    runtime_root: Path,
    pick_date: str,
    method: str,
    limit: int | None,
    intraday: bool = False,
) -> list[str] | None:
    command = build_review_list_command(
        binary=binary,
        runtime_root=runtime_root,
        pick_date=pick_date,
        method=method,
        limit=limit,
        intraday=intraday,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line.strip()]


def load_display_rows(
    *, runtime_root: Path, pick_date: str, method: str, intraday: bool = False
) -> list[dict]:
    path = select_dir(runtime_root, pick_date, method, intraday=intraday) / "display.json"
    if not path.exists():
        raise SystemExit(f"display artifact not found: {path}")
    payload = load_json(path)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise SystemExit(f"display artifact missing rows: {path}")
    return [row for row in rows if isinstance(row, dict)]


def limit_rows(rows: Sequence[dict], limit: int | None) -> list[dict]:
    if limit is None:
        return list(rows)
    if limit < 1:
        raise SystemExit("--limit must be positive")
    return list(rows[:limit])


def fetch_recent_trade_dates(dsn: str, pick_date: str, window: int) -> list[str]:
    try:
        import psycopg
    except ModuleNotFoundError:
        return recent_weekdays(pick_date, window)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct trade_date
                from stock_stk_factor_pro
                where trade_date <= %s
                order by trade_date desc
                limit %s
                """,
                (validate_date(pick_date), window + 1),
            )
            return sorted(row[0].isoformat() for row in cur.fetchall())


def recent_weekdays(pick_date: str, window: int) -> list[str]:
    current = date.fromisoformat(validate_date(pick_date)) - timedelta(days=1)
    dates: list[str] = []
    while len(dates) < window:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current -= timedelta(days=1)
    return sorted(dates)


def resolve_trade_dates(args: argparse.Namespace, dotenv_values: dict[str, str]) -> list[str]:
    if args.dates_file:
        return read_dates_file(args.dates_file)
    dsn = resolve_config_value(args.dsn, "POSTGRES_DSN", dotenv_values)
    if not dsn:
        raise SystemExit("POSTGRES_DSN is required; set it in .env, export it, pass --dsn, or use --dates-file.")
    return fetch_recent_trade_dates(dsn, args.pick_date, args.window)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pick-date", required=True, type=validate_date)
    parser.add_argument("--method", default=DEFAULT_METHOD, choices=sorted(SUPPORTED_METHODS))
    parser.add_argument("--candidate-methods", default=DEFAULT_METHOD, type=parse_methods)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--dates-file", type=Path)
    parser.add_argument("--dsn")
    parser.add_argument("--postgres-dsn", dest="dsn", help="Compatibility alias for --dsn.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--intraday", action="store_true")


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "recurring-candidates",
        help="mark final review rows that also appeared in recent candidate artifacts",
    )
    add_arguments(parser)
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    if args.window < 1:
        raise SystemExit("--window must be positive")

    dotenv_values = load_dotenv_values()
    runtime_root_value = resolve_config_value(
        str(args.runtime_root) if args.runtime_root else None,
        "STOCK_SELECT_RUNTIME_ROOT",
        dotenv_values,
    )
    if not runtime_root_value:
        raise SystemExit("STOCK_SELECT_RUNTIME_ROOT is required; set it in .env or pass --runtime-root.")
    runtime_root = Path(runtime_root_value).expanduser()

    trade_dates = resolve_trade_dates(args, dotenv_values)
    dates = recent_trade_dates(args.pick_date, trade_dates, window=args.window)
    occurrences = collect_candidate_occurrences(
        runtime_root=runtime_root,
        dates=dates,
        methods=args.candidate_methods,
        intraday=args.intraday,
    )
    rows = limit_rows(
        load_display_rows(
            runtime_root=runtime_root,
            pick_date=args.pick_date,
            method=args.method,
            intraday=args.intraday,
        ),
        args.limit,
    )
    review_list_lines = load_review_list_lines(
        binary=resolve_binary(args.binary),
        runtime_root=runtime_root,
        pick_date=args.pick_date,
        method=args.method,
        limit=args.limit,
        intraday=args.intraday,
    )
    if review_list_lines is not None:
        for line in format_recurring_lines_from_review_list(review_list_lines, occurrences):
            print(line)
        return 0
    for line in format_recurring_lines(rows, occurrences):
        print(line)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mark recurring candidate symbols in review-list output.")
    subparsers = parser.add_subparsers(dest="command")
    add_parser(subparsers)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not hasattr(args, "handler"):
        parser.print_usage()
        return 2
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
