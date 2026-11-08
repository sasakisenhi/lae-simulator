"""Fail-closed VB harness. Old evidence is immutable; each invocation needs a new root."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lae_simulator.simulation.canonical_store import canonical_json_bytes
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    replay_local,
    save_local_run,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/vb-reassessment/plan.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_directories(a: Path, b: Path) -> dict[str, Any]:
    left = {str(p.relative_to(a)): digest(p) for p in a.rglob("*") if p.is_file()}
    right = {str(p.relative_to(b)): digest(p) for p in b.rglob("*") if p.is_file()}
    return {
        "status": "PASS" if left == right and left else "FAIL",
        "left_only": sorted(left.keys() - right.keys()),
        "right_only": sorted(right.keys() - left.keys()),
        "changed": sorted(k for k in left.keys() & right.keys() if left[k] != right[k]),
        "files": left,
    }


def check_worker(returncode: int, summary: dict[str, Any] | None) -> str:
    if returncode != 0 or not isinstance(summary, dict):
        return "FAIL"
    return (
        "PASS"
        if summary.get("replay_equal") is True and summary.get("stored_equal") is True
        else "FAIL"
    )


def aggregate(statuses: list[str]) -> tuple[str, int]:
    if not statuses or any(s not in {"PASS", "NOT EVALUATED"} for s in statuses):
        return "FAIL", 1
    return ("NOT EVALUATED", 2) if "NOT EVALUATED" in statuses else ("PASS", 0)


def worker(case: str, arm: str, destination: Path) -> None:
    plan = json.loads(PLAN.read_bytes())
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for directory in ("g1", "g2"):
            shutil.copytree(ROOT / "fixtures" / directory, root / directory)
        data = json.loads((root / "g2/scenario-collaboration.json").read_bytes())
        if case == "access" and arm == "intervention":
            data["participant_profile"]["permissions"].remove(
                {"resource_id": "D02", "action": "read"}
            )
        path = root / "g2/condition.json"
        path.write_bytes(canonical_json_bytes(data))
        execution = load_scenario_execution(path)
        s = LocalSession.start(execution)
        if case in ("access", "negative"):
            s.select("T01")
            s.perform(
                kind=LocalEventKind.DOCUMENT_READ,
                candidate_id="T01",
                target_id="D01",
                input_version="B0",
            )
            s.select("T11")
            s.perform(
                kind=LocalEventKind.CHECK_EVALUATED,
                candidate_id="T11",
                check_id="C01",
                input_version="B0",
            )
        if case == "negative" and arm == "intervention":
            s.select("T15")
        trace = []
        for _ in range(plan["cases"][case]["steps"]):
            observation = asdict(s.observation)
            selected = s.select_by_policy()
            if selected is None:
                raise AssertionError("Policy has no candidate")
            candidate = selected.candidate_id
            if candidate in ("T01", "T02", "T05", "T06"):
                event = s.perform(
                    kind=LocalEventKind.DOCUMENT_READ,
                    candidate_id=candidate,
                    target_id={"T01": "D01", "T02": "D02", "T05": "D04", "T06": "D06"}[
                        candidate
                    ],
                    input_version=s.state.workspace_version,
                )
            elif candidate == "T03":
                event = s.perform(
                    kind=LocalEventKind.SEARCH,
                    candidate_id=candidate,
                    query="metadata",
                    input_version=s.state.workspace_version,
                )
            elif candidate == "T04":
                event = s.perform(
                    kind=LocalEventKind.NAVIGATE,
                    candidate_id=candidate,
                    target_id=s.observation.search_result_refs[0],
                    input_version=s.state.workspace_version,
                )
            else:
                raise AssertionError(
                    f"No preregistered parameter binding for {candidate}"
                )
            trace.append(
                {
                    "observation": observation,
                    "candidate": candidate,
                    "selection_event_id": selected.id,
                    "completed_event_id": event.id,
                    "operation": event.kind.value,
                    "tick": s.state.logical_time,
                }
            )
        result = s.finish()
        saved = save_local_run(execution, result, destination)
        summary = {
            "case": case,
            "arm": arm,
            "trace": trace,
            "replay_equal": replay_local(execution, result.initial_state, result.events)
            == result.final_state,
            "stored_equal": load_local_run(saved, execution).result == result,
            "content_id": execution.content_id,
            "outcome": result.final_state.outcome,
            "logical_time": result.final_state.logical_time,
        }
        (destination / "summary.json").write_bytes(canonical_json_bytes(summary))
        if check_worker(0, summary) != "PASS":
            raise AssertionError("Replay or stored state mismatch")


def freeze(output: Path) -> dict[str, Any]:
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    files = {
        p: digest(ROOT / p)
        for p in sorted(set(paths))
        if p
        and (ROOT / p).is_file()
        and not (ROOT / p).is_relative_to(output)
        and not p.startswith("docs/vb-reassessment/")
    }
    files[str(PLAN.relative_to(ROOT))] = digest(PLAN)
    manifest = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT
        ).decode(),
        "files": files,
        "plan_sha256": digest(PLAN),
        "python": sys.version,
        "seed": 0,
        "versions": {
            "scenario": "1.2.0",
            "scheduler": "canonical-scheduler-1.0",
            "fixed_response": "g5-fixed-v1",
        },
        "dependencies": subprocess.check_output(
            ["uv", "pip", "freeze"], cwd=ROOT
        ).decode(),
        "command": sys.argv,
        "exclusions": "new evaluation outputs/history/report; plan explicitly included",
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    manifest = freeze(output)
    plan = json.loads(PLAN.read_bytes())
    rows = []
    for case in plan["cases"]:
        for arm in ("control", "intervention"):
            paths = []
            for repeat in plan["replicates"]:
                dest = output / f"{case}-{arm}-{repeat['id']}"
                dest.mkdir()
                paths.append(dest)
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        case,
                        arm,
                        str(dest),
                    ],
                    env={**os.environ, "PYTHONHASHSEED": repeat["PYTHONHASHSEED"]},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                try:
                    parsed = json.loads((dest / "summary.json").read_bytes())
                    summary = parsed if isinstance(parsed, dict) else None
                except OSError, ValueError:
                    summary = None
                status = check_worker(completed.returncode, summary)
                try:
                    choices = (
                        [t["candidate"] for t in summary["trace"]] if summary else []
                    )
                except KeyError, TypeError:
                    choices = []
                    status = "FAIL"
                if choices != plan["cases"][case]["expected_" + arm]:
                    status = "FAIL"
                rows.append(
                    {
                        "kind": "worker",
                        "case": case,
                        "arm": arm,
                        "repeat": repeat["id"],
                        "status": status,
                        "returncode": completed.returncode,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                        "choices": choices,
                    }
                )
            rows.append(
                {
                    "kind": "repeat",
                    "case": case,
                    "arm": arm,
                    **compare_directories(*paths),
                }
            )
    for case in plan["cases"]:
        if case not in {"autonomous", "access", "negative"}:
            continue
        try:
            left = output / f"{case}-control-1"
            right = output / f"{case}-intervention-1"
            a = json.loads((left / "summary.json").read_bytes())
            b = json.loads((right / "summary.json").read_bytes())
            sa = json.loads(next(left.glob("local-*/scenario.json")).read_bytes())
            sb = json.loads(next(right.glob("local-*/scenario.json")).read_bytes())
            if case == "access":
                sa["participant_profile"]["permissions"].remove(
                    {"resource_id": "D02", "action": "read"}
                )
            single_factor = sa == sb
            observations_equal = [t["observation"] for t in a["trace"]] == [
                t["observation"] for t in b["trace"]
            ]
            actions_equal = [
                (t["candidate"], t["operation"], t["tick"]) for t in a["trace"]
            ] == [(t["candidate"], t["operation"], t["tick"]) for t in b["trace"]]
            valid = single_factor and (
                (not actions_equal and not observations_equal)
                if case == "access"
                else actions_equal and observations_equal
            )
            rows.append(
                {
                    "kind": "contrast",
                    "case": case,
                    "status": "PASS" if valid else "FAIL",
                    "single_factor": single_factor,
                    "observations_equal": observations_equal,
                    "actions_equal": actions_equal,
                }
            )
        except OSError, ValueError, KeyError, StopIteration:
            rows.append(
                {
                    "kind": "contrast",
                    "case": case,
                    "status": "FAIL",
                    "reason": "Missing or malformed pair evidence",
                }
            )
    for case, reason in plan["blocked"].items():
        rows.append(
            {
                "kind": "required-condition",
                "case": case,
                "status": "NOT EVALUATED",
                "reason": reason,
            }
        )
    changed = [p for p, h in manifest["files"].items() if digest(ROOT / p) != h]
    rows.append(
        {
            "kind": "target-recheck",
            "status": "FAIL" if changed else "PASS",
            "changed": changed,
        }
    )
    status, code = aggregate([row["status"] for row in rows])
    (output / "results.json").write_bytes(
        canonical_json_bytes({"status": status, "exit_code": code, "rows": rows})
    )
    print(json.dumps({"status": status, "exit_code": code, "output": str(output)}))
    return code


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--output", type=Path, required=True)
        sys.exit(run(parser.parse_args().output.resolve()))
