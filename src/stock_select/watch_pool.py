from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

import fcntl
import pandas as pd


WATCH_POOL_COLUMNS = [
    "method",
    "pick_date",
    "code",
    "verdict",
    "total_score",
    "signal_type",
    "comment",
    "recorded_at",
]
WATCH_POOL_KEY_COLUMNS = ["method", "code"]
WATCH_POOL_ALLOWED_VERDICTS = {"PASS", "WATCH"}


def empty_watch_pool() -> pd.DataFrame:
    return pd.DataFrame(columns=WATCH_POOL_COLUMNS)


def load_watch_pool(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        return empty_watch_pool()

    frame = pd.read_csv(csv_path)
    if frame.empty:
        return empty_watch_pool()

    for column in WATCH_POOL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[WATCH_POOL_COLUMNS].copy()
    frame["method"] = frame["method"].fillna("").astype(str).str.strip().str.lower()
    frame["pick_date"] = frame["pick_date"].fillna("").astype(str).str.strip()
    frame["code"] = frame["code"].fillna("").astype(str).str.strip()
    frame["verdict"] = frame["verdict"].fillna("").astype(str).str.strip().str.upper()
    frame["signal_type"] = frame["signal_type"].fillna("").astype(str).str.strip()
    frame["comment"] = frame["comment"].fillna("").astype(str).str.strip()
    frame["recorded_at"] = frame["recorded_at"].fillna("").astype(str).str.strip()
    frame["total_score"] = pd.to_numeric(frame["total_score"], errors="coerce").fillna(0.0)
    return frame


def effective_watch_pool_symbols(rows: pd.DataFrame, *, screening_date: str) -> list[str]:
    if rows.empty:
        return []

    frame = rows.copy().reset_index(drop=True)
    frame = frame[
        frame["code"].astype(str).str.strip().ne("")
        & frame["pick_date"].astype(str).str.strip().ne("")
        & (frame["pick_date"].astype(str) <= screening_date)
    ].copy()
    if frame.empty:
        return []

    frame["_row_order"] = range(len(frame))
    frame = frame.sort_values(by=["pick_date", "_row_order"], ascending=[True, True], kind="stable")
    frame = frame.drop_duplicates(subset=["code"], keep="last")
    frame = frame.sort_values(by="_row_order", ascending=True, kind="stable")
    return frame["code"].astype(str).tolist()


def summary_to_watch_rows(
    summary_payload: dict[str, object],
    *,
    method: str,
    pick_date: str,
    recorded_at: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for section in ("recommendations", "excluded"):
        values = summary_payload.get(section, [])
        if not isinstance(values, list):
            raise ValueError(f"Invalid summary json: {section} must be a list.")
        for item in values:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if not code:
                raise ValueError("Invalid summary json: selected review item missing code.")
            verdict = str(item.get("verdict") or "").strip().upper()
            if verdict not in WATCH_POOL_ALLOWED_VERDICTS:
                continue
            rows.append(
                {
                    "method": method,
                    "pick_date": pick_date,
                    "code": code,
                    "verdict": verdict,
                    "total_score": float(item.get("total_score", 0.0)),
                    "signal_type": str(item.get("signal_type") or "").strip(),
                    "comment": str(item.get("comment") or "").strip(),
                    "recorded_at": recorded_at,
                }
            )
    if not rows:
        return empty_watch_pool()
    return pd.DataFrame(rows, columns=WATCH_POOL_COLUMNS)


def merge_watch_rows(existing: pd.DataFrame, incoming: pd.DataFrame, *, overwrite: bool) -> tuple[pd.DataFrame, int, int]:
    if incoming.empty:
        return existing.copy(), 0, 0

    if existing.empty:
        return incoming.copy(), 0, len(incoming)

    existing_keys = {tuple(str(row[column]) for column in WATCH_POOL_KEY_COLUMNS) for _, row in existing.iterrows()}
    incoming_keys = {tuple(str(row[column]) for column in WATCH_POOL_KEY_COLUMNS) for _, row in incoming.iterrows()}
    duplicate_count = len(existing_keys & incoming_keys)
    if duplicate_count and not overwrite:
        raise ValueError("Duplicate watch-pool rows found; rerun with --overwrite to replace them.")

    kept_existing = existing
    if duplicate_count:
        kept_existing = existing[
            ~existing.apply(
                lambda row: tuple(str(row[column]) for column in WATCH_POOL_KEY_COLUMNS) in incoming_keys,
                axis=1,
            )
        ].reset_index(drop=True)

    merged = pd.concat([kept_existing, incoming], ignore_index=True)
    return merged[WATCH_POOL_COLUMNS].copy(), duplicate_count, len(incoming)


def trim_and_sort_watch_rows(
    rows: pd.DataFrame,
    *,
    trade_dates_desc: list[str],
    execution_trade_date: str,
    cutoff_trade_date: str,
) -> tuple[pd.DataFrame, int]:
    if rows.empty:
        return empty_watch_pool(), 0

    trade_index = {trade_date: idx for idx, trade_date in enumerate(trade_dates_desc)}
    if execution_trade_date not in trade_index:
        raise ValueError(f"Execution trade date not found in trade calendar: {execution_trade_date}")
    if cutoff_trade_date not in trade_index:
        raise ValueError(f"Cutoff trade date not found in trade calendar: {cutoff_trade_date}")

    frame = rows.copy()
    before_count = len(frame)
    frame = frame[frame["pick_date"].astype(str) >= cutoff_trade_date].copy()
    frame["_trade_distance"] = frame["pick_date"].astype(str).map(trade_index)
    frame = frame[frame["_trade_distance"].notna()].copy()
    frame["_trade_distance"] = frame["_trade_distance"].astype(int)
    frame = frame.sort_values(
        by=["_trade_distance", "pick_date", "code"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)
    return frame[WATCH_POOL_COLUMNS].copy(), before_count - len(frame)


def write_watch_pool(csv_path: Path, rows: pd.DataFrame) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame = rows.copy() if not rows.empty else empty_watch_pool()
    frame = frame[WATCH_POOL_COLUMNS].copy()
    frame.to_csv(csv_path, index=False)


def update_watch_pool(
    csv_path: Path,
    updater: Callable[[pd.DataFrame], pd.DataFrame],
) -> pd.DataFrame:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = csv_path.with_name(f"{csv_path.name}.lock")

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        existing = load_watch_pool(csv_path)
        updated = updater(existing)
        frame = updated.copy() if not updated.empty else empty_watch_pool()
        frame = frame[WATCH_POOL_COLUMNS].copy()

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=csv_path.parent,
            prefix=f".{csv_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            frame.to_csv(handle, index=False)

        os.replace(temp_path, csv_path)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return frame
