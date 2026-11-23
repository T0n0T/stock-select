"""统一已核验证券身份；历史产物的因子值保持原样，标签只用连续行情。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ml.db import query_rows


def fetch_security_aliases(source: str, symbols: Sequence[str]) -> list[dict[str, Any]]:
    if not any(code.endswith(".BJ") and not code.startswith("920") for code in symbols):
        return []
    sql = Path(__file__).with_name("security_aliases.sql").read_text(encoding="utf-8")
    return query_rows(source, sql, [])


def canonicalize_security_rows(
    rows: Sequence[dict[str, Any]], aliases: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    reverse: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        old, new = alias["old_code"], alias["new_code"]
        if old in mapping or new in reverse or old == new:
            raise ValueError("ambiguous security identity")
        if alias["identical_raw_bars"] < 20:
            raise ValueError("insufficient security identity evidence")
        mapping[old] = alias
        reverse[new] = alias
    selected: dict[tuple[str, str], tuple[int, str, dict[str, Any]]] = {}
    seen_sources: set[tuple[str, str]] = set()
    removed = []
    remapped = 0
    for original in rows:
        source = str(original["code"])
        day = str(original["date"])
        if (day, source) in seen_sources:
            raise ValueError(f"duplicate source row: {day} {source}")
        seen_sources.add((day, source))
        alias = mapping.get(source) or reverse.get(source)
        code = alias["new_code"] if alias else source
        preferred = alias["old_code"] if alias and day <= str(alias["old_last_date"]) else code
        score = int(source == preferred)
        remapped += int(source != code)
        row = dict(original, code=code) if code != source else original
        key = (day, code)
        previous = selected.get(key)
        if previous is None:
            selected[key] = (score, source, row)
            continue
        if score > previous[0]:
            selected[key] = (score, source, row)
            kept, dropped = source, previous[1]
        else:
            kept, dropped = previous[1], source
        removed.append({"date": day, "canonical_code": code,
                        "kept_source": kept, "removed_source": dropped})
    return [selected[key][2] for key in sorted(selected)], {
        "source_row_count": len(rows),
        "output_row_count": len(selected),
        "duplicate_row_count": len(removed),
        "remapped_source_row_count": remapped,
        "aliases": list(aliases),
        "duplicates_removed": removed,
    }
