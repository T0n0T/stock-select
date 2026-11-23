from __future__ import annotations

import argparse


MAX_WORKERS = 8


def validate_worker_count(value: int) -> int:
    if not 1 <= value <= MAX_WORKERS:
        raise ValueError(f"parallelism must be between 1 and {MAX_WORKERS}")
    return value


def parse_worker_count(value: str) -> int:
    try:
        return validate_worker_count(int(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"parallelism must be between 1 and {MAX_WORKERS}") from exc


def resolve_num_threads(value: int) -> int:
    return validate_worker_count(MAX_WORKERS if value == 0 else value)
