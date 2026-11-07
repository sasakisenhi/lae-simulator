"""Command-line entry points for the local simulator."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from lae_simulator import __version__
from lae_simulator.world import WorldValidationError, load_world

SUPPORTED_PYTHON = (3, 14, 8)


def _doctor() -> int:
    actual = sys.version_info[:3]
    supported = actual == SUPPORTED_PYTHON
    report = {
        "application": "lae-simulator",
        "application_version": __version__,
        "python": ".".join(map(str, actual)),
        "status": "ok" if supported else "unsupported-runtime",
        "supported_python": ".".join(map(str, SUPPORTED_PYTHON)),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if supported else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lae-sim")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "doctor",
        help="固定ランタイムとローカル実行入口を検査する",
    )
    validate_world = subcommands.add_parser(
        "validate-world",
        help="固定世界入力を読み込み、実行せずに検証する",
    )
    validate_world.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "validate-world":
        try:
            world = load_world(args.path)
        except WorldValidationError as error:
            report = {
                "issues": [issue.as_dict() for issue in error.issues],
                "status": "invalid",
            }
            print(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        report = {
            "content_id": world.content_id,
            "exercise_id": world.exercise_id,
            "schema_version": world.schema_version,
            "status": "valid",
        }
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
