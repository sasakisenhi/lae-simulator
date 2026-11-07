"""Command-line entry points for the local simulator."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from lae_simulator import __version__
from lae_simulator.provenance import ProvenanceValidationError, verify_provenance_bundle
from lae_simulator.simulation import (
    PersistenceError,
    PublicationError,
    SimulationError,
    execute,
    load_run,
    project_public_log,
    save_run,
)
from lae_simulator.world import WorldValidationError, load_scenario_bundle, load_world

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
    validate_materials = subcommands.add_parser(
        "validate-materials",
        help="固定教材の来歴・内容digest・Git blobをオフライン検証する",
    )
    validate_materials.add_argument("manifest", type=Path)
    validate_scenario = subcommands.add_parser(
        "validate-scenario",
        help="固定候補・Patch・modeled Check教材を実行せずに検証する",
    )
    validate_scenario.add_argument("path", type=Path)
    run = subcommands.add_parser(
        "run",
        help="固定世界入力を実行し、検査済みrunを新規保存する",
    )
    run.add_argument("path", type=Path)
    run.add_argument("--output", type=Path, required=True)
    public_log = subcommands.add_parser(
        "public-log",
        help="保存済みrunを再検査し、調査者向け合成ログを取得する",
    )
    public_log.add_argument("run_path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report: dict[str, object]
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
    if args.command == "validate-materials":
        try:
            report = verify_provenance_bundle(args.manifest)
        except ProvenanceValidationError as error:
            print(
                json.dumps(
                    {"issues": [issue.as_dict() for issue in error.issues], "status": "invalid"},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    if args.command == "validate-scenario":
        try:
            scenario = load_scenario_bundle(args.path)
        except WorldValidationError as error:
            print(
                json.dumps(
                    {"issues": [issue.as_dict() for issue in error.issues], "status": "invalid"},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        report = {
            "candidates": len(scenario.candidate_ids),
            "checks": len(scenario.check_ids),
            "content_id": scenario.content_id,
            "exercise_id": scenario.exercise_id,
            "patches": len(scenario.patch_ids),
            "schema_version": scenario.schema_version,
            "status": "valid",
        }
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    if args.command == "run":
        try:
            world = load_world(args.path)
            result = execute(world)
            saved_path = save_run(world, result, args.output)
            stored = load_run(saved_path)
        except WorldValidationError as error:
            report = {
                "issues": [issue.as_dict() for issue in error.issues],
                "status": "invalid-input",
            }
            print(
                json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                file=sys.stderr,
            )
            return 2
        except PersistenceError as error:
            print(
                json.dumps(
                    error.record.as_dict(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 3
        except SimulationError as error:
            report = {
                "reason": str(error),
                "stage": "execution",
                "status": "internal-error",
                "target": str(args.path),
            }
            print(
                json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                file=sys.stderr,
            )
            return 3
        outcome = stored.result.final_state.outcome
        if outcome is None:
            raise AssertionError("validated stored run has no business outcome")
        report = {
            "business_outcome": outcome.value,
            "public_records": len(stored.result.public_log),
            "run_id": stored.result.run_id,
            "run_path": str(stored.path),
            "status": stored.result.validation.validity.value,
        }
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    if args.command == "public-log":
        try:
            stored = load_run(args.run_path)
            records = project_public_log(
                stored.world,
                stored.result.initial_state,
                stored.result.events,
                stored.result.final_state,
            )
        except (PersistenceError, PublicationError) as error:
            if isinstance(error, PersistenceError):
                report = dict[str, object](error.record.as_dict())
            else:
                report = {
                    "reason": str(error),
                    "stage": "publication",
                    "status": "internal-error",
                    "target": str(args.run_path),
                }
            print(
                json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                file=sys.stderr,
            )
            return 3
        print(
            json.dumps(
                [record.as_dict() for record in records],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
