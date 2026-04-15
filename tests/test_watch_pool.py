from __future__ import annotations

from multiprocessing import Process
from pathlib import Path

import pandas as pd

from stock_select.watch_pool import load_watch_pool


def _update_watch_pool_worker(csv_path_str: str, row: dict[str, object]) -> None:
    import time
    from pathlib import Path

    import pandas as pd

    from stock_select.watch_pool import (
        merge_watch_rows,
        trim_and_sort_watch_rows,
        update_watch_pool,
    )

    csv_path = Path(csv_path_str)
    incoming = pd.DataFrame([row])

    def apply(existing: pd.DataFrame) -> pd.DataFrame:
        merged, _, _ = merge_watch_rows(existing, incoming, overwrite=True)
        time.sleep(0.2)
        final_rows, _ = trim_and_sort_watch_rows(
            merged,
            trade_dates_desc=["2026-04-14", "2026-04-10", "2026-04-09", "2026-04-08"],
            execution_trade_date="2026-04-14",
            cutoff_trade_date="2026-04-08",
        )
        return final_rows

    update_watch_pool(csv_path, apply)


def test_update_watch_pool_serializes_concurrent_writers(tmp_path: Path) -> None:
    csv_path = tmp_path / "watch_pool.csv"

    row_a = {
        "method": "b1",
        "pick_date": "2026-04-10",
        "code": "AAA.SZ",
        "verdict": "PASS",
        "total_score": 4.5,
        "signal_type": "trend_start",
        "comment": "first",
        "recorded_at": "2026-04-14T10:00:00+08:00",
    }
    row_b = {
        "method": "hcr",
        "pick_date": "2026-04-10",
        "code": "BBB.SZ",
        "verdict": "WATCH",
        "total_score": 3.8,
        "signal_type": "rebound",
        "comment": "second",
        "recorded_at": "2026-04-14T10:01:00+08:00",
    }

    first = Process(target=_update_watch_pool_worker, args=(str(csv_path), row_a))
    second = Process(target=_update_watch_pool_worker, args=(str(csv_path), row_b))

    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.exitcode == 0
    assert second.exitcode == 0

    rows = load_watch_pool(csv_path).to_dict(orient="records")
    assert {(row["method"], row["code"]) for row in rows} == {("b1", "AAA.SZ"), ("hcr", "BBB.SZ")}
