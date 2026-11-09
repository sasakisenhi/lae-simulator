"""G8 CLI application orchestration; existing CF0 commands stay in cli.py."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import Field, TypeAdapter

from lae_simulator.adapters.interview_config import (
    Approval,
    EvaluationConfig,
    StrictConfig,
)
from lae_simulator.interview_evaluation import QuestionSet, approval_requests, evaluate
from lae_simulator.simulation.errors import (
    PersistenceError,
    PublicationError,
    SimulationError,
)
from lae_simulator.simulation.fixed_evidence import (
    employee_package,
    get_evidence,
    related_evidence,
    search_evidence,
)
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    save_local_run,
)
from lae_simulator.world.errors import WorldValidationError


class Command(StrictConfig):
    candidate_id: str = Field(min_length=1)
    target_id: str | None = None
    query: str | None = None
    patch_id: str | None = None
    check_id: str | None = None


class Commands(StrictConfig):
    commands: tuple[Command, ...] = Field(min_length=1, max_length=100)


def add_scenario_commands(subcommands: Any) -> None:
    run = subcommands.add_parser("run-scenario", help="#1955等の固定Scenarioを同じEngineで実行・保存・再生検査する")
    run.add_argument("path", type=Path)
    run.add_argument("--commands", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    for name in ("evidence", "prepare-interview", "interview"):
        command = subcommands.add_parser(name)
        command.add_argument("run_path", type=Path)
        command.add_argument("--scenario", type=Path, required=True)
        if name == "evidence":
            command.add_argument("--role", default="researcher")
            command.add_argument("--query", default="")
            command.add_argument("--id")
            command.add_argument("--related", action="store_true")
            command.add_argument("--issue")
            command.add_argument("--target")
            command.add_argument("--tick", type=int)
            command.add_argument("--through-tick", type=int)
        else:
            command.add_argument("--config", type=Path, required=True)
            command.add_argument("--questions", type=Path, required=True)
            command.add_argument("--actor-id")
            command.add_argument("--output", type=Path, required=True)
            if name == "interview":
                command.add_argument("--approval", type=Path)


def _run(args: argparse.Namespace) -> dict[str, object]:
    commands = Commands.model_validate_json(args.commands.read_bytes())
    execution = load_scenario_execution(args.path)
    kinds = {"issue.read": LocalEventKind.DOCUMENT_READ, "document.read": LocalEventKind.DOCUMENT_READ,
             "code.search": LocalEventKind.SEARCH, "symbol.navigate": LocalEventKind.NAVIGATE,
             "patch.apply": LocalEventKind.PATCH_APPLIED, "patch.revert": LocalEventKind.PATCH_REVERTED,
             "check.model": LocalEventKind.CHECK_EVALUATED}
    # Validate CLI binding before changing state; the reducer still enforces all permissions.
    bindings = []
    for command in commands.commands:
        candidate = next((row for row in execution.candidates if row.id == command.candidate_id), None)
        if candidate is None or candidate.operation not in kinds:
            raise ValueError("unsupported CLI operation binding")
        fields = {key for key, value in command.model_dump().items() if value is not None and key != "candidate_id"}
        required = {"issue.read": "target_id", "document.read": "target_id", "code.search": "query",
                    "symbol.navigate": "target_id", "patch.apply": "patch_id", "patch.revert": "patch_id",
                    "check.model": "check_id"}[candidate.operation]
        if fields != {required}:
            raise ValueError("operation requires exactly its target binding")
        bindings.append((command, kinds[candidate.operation]))
    session = LocalSession.start(execution)
    for command, kind in bindings:
        if session.state.outcome is not None:
            raise ValueError("run ended before command sequence completed")
        session.select(command.candidate_id)
        event = session.perform(kind=kind, input_version=session.state.workspace_version,
                                **command.model_dump(exclude_none=True))
        if event.kind != kind:
            raise ValueError("operation did not complete")
    result = session.finish()
    path = save_local_run(execution, result, args.output)
    stored = load_local_run(path, execution)
    return {"status": "valid", "business_outcome": stored.result.final_state.outcome,
            "run_path": str(path), "run_id": result.run_id, "replay": "PASS",
            "control": "explicit commands; not autonomous policy acceptance"}


def scenario_main(args: argparse.Namespace) -> int:
    try:
        if args.command == "run-scenario":
            report = _run(args)
        else:
            execution = load_scenario_execution(args.scenario)
            stored = load_local_run(args.run_path, execution)
            if args.command == "evidence":
                if args.related and not args.id:
                    raise ValueError("related requires id")
                if args.id:
                    fetch = related_evidence if args.related else get_evidence
                    value = fetch(execution, stored.result, role=args.role, evidence_id=args.id)
                else:
                    value = search_evidence(execution, stored.result, role=args.role, query=args.query,
                                            issue=args.issue, target=args.target, tick=args.tick, through_tick=args.through_tick)
                print(value.decode())
                return 0
            config = EvaluationConfig.model_validate_json(args.config.read_bytes())
            questions = QuestionSet.model_validate_json(args.questions.read_bytes())
            package = employee_package(execution, stored.result, actor_id=args.actor_id or execution.actor_id)
            if args.command == "prepare-interview":
                print(approval_requests(config, package, questions, evaluation_id=str(args.output.resolve())).decode())
                return 0
            output = args.output.resolve()
            if output == stored.path.resolve() or stored.path.resolve() in output.parents:
                raise ValueError("interview sidecars must be outside simulation bundle")
            approvals = (TypeAdapter(tuple[Approval, ...]).validate_json(args.approval.read_bytes())
                         if args.approval else ())
            report = evaluate(config, package, questions, actor_id=execution.actor_id,
                              run_id=stored.result.run_id, output=output, approvals=approvals)
            # Full report is private. CLI stdout exposes only operation status, never audits or package IDs.
            providers = report["providers"]
            assert isinstance(providers, list)
            abstained = any(item["abstention"] for row in providers for item in row["results"])
            statuses = [item["status"] for row in providers for item in row["results"]]
            code = (4 if "not-ready" in statuses else 5 if "budget-exceeded" in statuses else
                    3 if "generation-failed" in statuses else 7 if "rejected" in statuses else
                    8 if "inconclusive" in statuses else 6 if "unanswerable" in statuses or abstained else 0)
            print(json.dumps({"status": "recorded" if code == 0 else "not-ready" if code == 4 else "answered-unknown" if code == 6 else "not-accepted",
                              "acceptance": report["acceptance"], "output": str(output)}, sort_keys=True))
            return code
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except PublicationError:
        report = {"status": "unavailable"}
        code = 4
    except WorldValidationError:
        report = {"status": "invalid-input", "stage": "scenario-validation"}
        code = 2
    except PersistenceError:
        report = {"status": "internal-error", "stage": "store-validation"}
        code = 3
    except SimulationError:
        report = {"status": "internal-error", "stage": "execution"}
        code = 3
    except (ValueError, TypeError):
        report = {"status": "invalid-input"}
        code = 2
    except OSError:
        report = {"status": "internal-error", "stage": "local-io"}
        code = 3
    print(json.dumps(report, sort_keys=True), file=sys.stderr)
    return code
