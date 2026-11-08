"""Preregistered A/B intervention and existing-coverage preliminary experiment."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from lae_simulator.simulation.canonical_store import canonical_json_bytes
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    replay_local,
    save_local_run,
)
from scripts.vb_acceptance import aggregate, check_worker, compare_directories

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/vb-contract-evidence"


def worker(case: str, arm: str, destination: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("g1", "g2"):
            shutil.copytree(ROOT / "fixtures" / name, root / name)
        data = json.loads((root / "g2/scenario-collaboration.json").read_bytes())
        data["schema_version"] = "1.3.0"
        if case == "tool":
            data["tool_availability"] = {"code.search": arm == "control"}
        if case == "knowledge":
            data["world_claims"].append(
                {
                    "id": "QUERY-KNOWN",
                    "statement": "Synthetic trial assumption: actor knows how to formulate the source query metadata; no correctness claim.",
                    "source_ids": ["B0"],
                    "origin": "synthetic-assumption",
                    "status": "additional-assumption",
                    "classification": "actor-private",
                }
            )
            next(c for c in data["candidates"] if c["id"] == "T03")[
                "required_claims"
            ] = ["QUERY-KNOWN"]
            if arm == "control":
                for key in ("actor_view", "participant_profile"):
                    data[key]["initial_claim_ids"].append("QUERY-KNOWN")
        if case == "coverage" and arm == "intervention":
            ref = next(r for r in data["references"] if r["id"] == "R02")
            ref["coverage"] = "unrecorded"
            ref.pop("target_id")
        path = root / "g2/condition.json"
        path.write_bytes(canonical_json_bytes(data))
        execution = load_scenario_execution(path)
        s = LocalSession.start(execution)
        initial = asdict(s.observation)
        s.select("T01")
        s.perform(
            kind=LocalEventKind.DOCUMENT_READ,
            candidate_id="T01",
            target_id="D01",
            input_version="B0",
        )
        trace = []
        for _ in range(1 if case == "knowledge" else 2):
            observation = asdict(s.observation)
            selected = s.select_by_policy()
            assert selected is not None
            candidate = selected.candidate_id
            if candidate == "T03":
                completed = s.perform(
                    kind=LocalEventKind.SEARCH,
                    candidate_id=candidate,
                    query="metadata",
                    input_version="B0",
                )
            elif candidate == "T04":
                completed = s.perform(
                    kind=LocalEventKind.NAVIGATE,
                    candidate_id=candidate,
                    target_id=s.state.search_result_refs[0],
                    input_version="B0",
                )
            elif candidate == "T02":
                completed = s.perform(
                    kind=LocalEventKind.DOCUMENT_READ,
                    candidate_id=candidate,
                    target_id="D02",
                    input_version="B0",
                )
            else:
                raise AssertionError(f"Unexpected preregistered choice {candidate}")
            trace.append(
                {
                    "before": observation,
                    "selected": candidate,
                    "selection_event": selected.id,
                    "completed_event": completed.id,
                    "operation": completed.kind.value,
                    "result": completed.observed_result,
                    "target": completed.target_id,
                    "after": asdict(s.observation),
                }
            )
        r = s.finish()
        saved = save_local_run(execution, r, destination)
        summary = {
            "initial": initial,
            "trace": trace,
            "outcome": r.final_state.outcome,
            "replay_equal": replay_local(execution, r.initial_state, r.events)
            == r.final_state,
            "stored_equal": load_local_run(saved, execution).result == r,
            "workspace": r.final_state.as_dict()["workspace_digest"],
        }
        (destination / "summary.json").write_bytes(canonical_json_bytes(summary))
        assert check_worker(0, summary) == "PASS"


def main() -> int:
    runroot = OUT / "runs"
    runroot.mkdir(exist_ok=False)
    rows = []
    for case in ("tool", "knowledge", "coverage"):
        for arm in ("control", "intervention"):
            paths = []
            for repeat, seed in ((1, "2"), (2, "71")):
                dest = runroot / f"{case}-{arm}-{repeat}"
                dest.mkdir()
                paths.append(dest)
                process = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "scripts.vb_contract_acceptance",
                        "worker",
                        case,
                        arm,
                        str(dest),
                    ],
                    env={**os.environ, "PYTHONHASHSEED": seed},
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=ROOT,
                )
                try:
                    summary = json.loads((dest / "summary.json").read_bytes())
                except OSError, ValueError:
                    summary = None
                rows.append(
                    {
                        "case": case,
                        "arm": arm,
                        "repeat": repeat,
                        "status": check_worker(process.returncode, summary),
                        "exit": process.returncode,
                        "stderr": process.stderr,
                    }
                )
            rows.append(
                {
                    "case": case,
                    "arm": arm,
                    "comparison": True,
                    **compare_directories(*paths),
                }
            )
    for case in ("tool", "knowledge", "coverage"):
        try:
            a = json.loads((runroot / f"{case}-control-1/summary.json").read_bytes())
            b = json.loads(
                (runroot / f"{case}-intervention-1/summary.json").read_bytes()
            )
            choices = (
                [t["selected"] for t in a["trace"]],
                [t["selected"] for t in b["trace"]],
            )
            if case == "tool":
                valid = (
                    a["initial"] == b["initial"]
                    and a["trace"][0]["before"] == b["trace"][0]["before"]
                    and choices == (["T03", "T04"], ["T03", "T02"])
                    and b["trace"][0]["result"] == "tool-unavailable"
                )
            elif case == "knowledge":
                valid = (
                    choices == (["T03"], ["T02"])
                    and not a["initial"]["acquired_document_content"]
                    and not a["initial"]["search_result_refs"]
                )
            else:
                aa = a["trace"][0]["after"]["search_result_refs"]
                bb = b["trace"][0]["after"]["search_result_refs"]
                valid = (
                    a["workspace"] == b["workspace"]
                    and "R02" in aa
                    and "R02" not in bb
                    and [x for x in aa if "#" in x] == [x for x in bb if "#" in x]
                    and choices == (["T03", "T04"], ["T03", "T04"])
                )
            rows.append(
                {
                    "case": case,
                    "expectations": True,
                    "status": "PASS" if valid else "FAIL",
                    "choices": choices,
                    "behavioral_acceptance": "NOT EVALUATED"
                    if case == "coverage"
                    else ("PASS" if valid else "FAIL"),
                }
            )
        except OSError, ValueError, KeyError:
            rows.append(
                {"case": case, "status": "FAIL", "reason": "missing pair evidence"}
            )
    rows.append(
        {
            "case": "C-behavior",
            "status": "NOT EVALUATED",
            "reason": "coverage information variation is not a Policy candidate branch",
        }
    )
    status, code = aggregate([r["status"] for r in rows])
    (OUT / "results.json").write_bytes(
        canonical_json_bytes({"status": status, "exit_code": code, "rows": rows})
    )
    print(json.dumps({"status": status, "exit": code}))
    return code


if __name__ == "__main__":
    if len(sys.argv) > 1:
        worker(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        sys.exit(main())
