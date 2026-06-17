from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .promote import DEFAULT_METHOD, list_archived_models, print_archive_list, resolve_default_target_dir


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("archives", description="列出可切换的归档模型")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--target-dir", type=Path)
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    try:
        target_dir = args.target_dir or resolve_default_target_dir(args.runtime_root, method=args.method)
        print_archive_list(list_archived_models(target_dir, expected_method=args.method))
        return 0
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
