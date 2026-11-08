"""Independent VA acceptance driver; no production mutation or test helpers."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.errors import (
    PersistenceError,
    PublicationError,
    SimulationError,
)
from lae_simulator.simulation.fixed_evidence import (
    employee_package,
    get_evidence,
    public_evidence,
    search_evidence,
)
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    local_event_bytes,
    replay_local,
    save_local_run,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/va-evidence"
SCENARIO = ROOT / "fixtures/g2/scenario-collaboration.json"


def generate(hidden=False):
    s = LocalSession.start(load_scenario_execution(SCENARIO))
    if hidden:
        s.select("T15")
    s.select("T01")
    s.perform(
        kind=LocalEventKind.DOCUMENT_READ,
        candidate_id="T01",
        target_id="D01",
        input_version="B0",
    )
    s.select("T07")
    request = s.request(candidate_id="T07", rule_id="PEER-ANSWER", input_ids=("D01",))
    rid = request.collaboration.request_id
    s.cancel_request(rid, 1)
    for _ in range(2):
        s.select("T03")
        s.perform(
            kind=LocalEventKind.SEARCH,
            candidate_id="T03",
            query="metadata",
            input_version="B0",
        )
    s.select("T10")
    s.perform(
        kind=LocalEventKind.PATCH_APPLIED,
        candidate_id="T10",
        patch_id="P2",
        input_version="B0",
    )
    s.select("T11")
    s.perform(
        kind=LocalEventKind.CHECK_EVALUATED,
        candidate_id="T11",
        check_id="C04",
        input_version=s.state.workspace_version,
    )
    return s, s.finish()


def worker(destination):
    s, r = generate()
    p = save_local_run(s.execution, r, destination)
    print(p)


def main():
    OUT.mkdir(exist_ok=True)
    paths = []
    for label, seed in [("a", "2"), ("b", "71")]:
        destination = OUT / ("run-" + label)
        destination.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    str(destination),
                ],
                env={**os.environ, "PYTHONHASHSEED": seed, "TMPDIR": tmp},
                capture_output=True,
                text=True,
                check=True,
            )
        paths.append(Path(result.stdout.strip()))
    a, b = paths
    comparisons = {
        p.name: p.read_bytes() == (b / p.name).read_bytes() for p in a.iterdir()
    }
    s, r = generate()
    restored = load_local_run(a, s.execution).result
    replay = replay_local(s.execution, r.initial_state, r.events)
    cases = []

    def record(name, expected, actual, detail=""):
        cases.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "status": "PASS" if expected == actual else "FAIL",
                "detail": detail,
            }
        )

    record(
        "independent-all-artifacts",
        True,
        all(comparisons.values()),
        json.dumps(comparisons),
    )
    record(
        "replay-state-queue-resources",
        True,
        replay == r.final_state == restored.final_state,
    )
    record(
        "stored-package-reconstruction",
        True,
        (a / "employee-package.json").read_bytes()
        == employee_package(s.execution, restored, actor_id=s.execution.actor_id),
    )
    hidden_s, hidden_r = generate(True)
    record(
        "hidden-internal-selection-noninterference",
        True,
        employee_package(s.execution, r, actor_id=s.execution.actor_id)
        == employee_package(
            hidden_s.execution, hidden_r, actor_id=hidden_s.execution.actor_id
        )
        and public_evidence(s.execution, r)
        == public_evidence(hidden_s.execution, hidden_r),
    )
    record(
        "no-canonical-id-in-package",
        False,
        b"LEV-" in (a / "employee-package.json").read_bytes(),
    )
    for kind in [
        "event-edit",
        "event-delete",
        "event-reorder",
        "final-state",
        "public-log",
        "employee-package",
        "audit-mapping",
        "manifest",
        "missing",
    ]:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / a.name
            shutil.copytree(a, p)
            name = "events.jsonl"
            if kind.startswith("event-"):
                rows = [
                    json.loads(line) for line in (p / name).read_bytes().splitlines()
                ]
                if kind == "event-edit":
                    rows[3]["caused_by"] = ["LEV-999999"]
                if kind == "event-delete":
                    del rows[3]
                if kind == "event-reorder":
                    rows[3], rows[4] = rows[4], rows[3]
                data = b"".join(canonical_json_bytes(row) for row in rows)
            elif kind in (
                "final-state",
                "public-log",
                "employee-package",
                "audit-mapping",
            ):
                name = kind + ".json"
                value = json.loads((p / name).read_bytes())
                if isinstance(value, list):
                    value[0]["target_id"] = "FORGED"
                else:
                    value["invented"] = "FORGED"
                data = canonical_json_bytes(value)
            elif kind == "manifest":
                name = "manifest.json"
                value = json.loads((p / name).read_bytes())
                value["definition_id"] = "FORGED"
                data = canonical_json_bytes(value)
            else:
                (p / "closure.json").unlink()
                data = None
            if data is not None:
                (p / name).write_bytes(data)
                if name != "manifest.json":
                    m = json.loads((p / "manifest.json").read_bytes())
                    m["artifacts"][name] = content_digest(data)
                    (p / "manifest.json").write_bytes(canonical_json_bytes(m))
            exposed = False
            try:
                bad = load_local_run(p, s.execution).result
                search_evidence(s.execution, bad, role="researcher")
                exposed = True
            except PersistenceError, PublicationError:
                pass
            record(
                kind + "-load-and-public-gate",
                False,
                exposed,
                "artifact digest refreshed for semantic mutations",
            )
    bad = replace(
        r, events=r.events[1:], canonical_bytes=local_event_bytes(r.events[1:])
    )
    for label, action in [
        ("catalog", lambda: search_evidence(s.execution, bad, role="researcher")),
        (
            "employee",
            lambda: employee_package(s.execution, bad, actor_id=s.execution.actor_id),
        ),
        ("public", lambda: public_evidence(s.execution, bad)),
        (
            "private",
            lambda: get_evidence(
                s.execution, r, role="researcher", evidence_id="document:D07"
            ),
        ),
        ("unknown-role", lambda: search_evidence(s.execution, r, role="admin")),
    ]:
        denied = False
        try:
            action()
        except SimulationError:
            denied = True
        record(label + "-denied", True, denied)
    with tempfile.TemporaryDirectory() as tmp:
        original = Path.write_bytes
        count = 0

        def fail_midway(path, data):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("VA injected disk failure")
            return original(path, data)

        denied = False
        try:
            with patch.object(Path, "write_bytes", fail_midway):
                save_local_run(s.execution, r, tmp)
        except PersistenceError as error:
            denied = error.record.status == "internal-error"
        record(
            "mid-write-failure-cleanup",
            True,
            denied and not list(Path(tmp).iterdir()),
            f"writes attempted={count}",
        )
    for tick, action in ((0, "cancelled"), (0, "invalidated"), (1, "invalidated")):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ("g1", "g2"):
                shutil.copytree(ROOT / "fixtures" / directory, root / directory)
            data = json.loads((ROOT / "fixtures/g2/scenario-timed.json").read_bytes())
            data["timing"]["controls"] = [
                {
                    "id": "CTRL",
                    "tick": tick,
                    "priority": 20,
                    "action": action,
                    "target_candidate_id": "T03",
                    "reason": "VA synthetic control",
                    "generation": 1,
                }
            ]
            scenario = root / "g2/scenario.json"
            scenario.write_bytes(canonical_json_bytes(data))
            execution = load_scenario_execution(scenario)
            session = LocalSession.start(execution)
            session.select("T03")
            session.perform(
                kind=LocalEventKind.SEARCH,
                candidate_id="T03",
                query="metadata",
                input_version="B0",
            )
            if tick == 1:
                session.advance_next()
            result = session.finish()
            saved = save_local_run(execution, result, root / "runs")
            equal = (
                load_local_run(saved, execution).result == result
                and replay_local(execution, result.initial_state, result.events)
                == result.final_state
            )
            record(
                f"control-{tick}-{action}",
                True,
                equal and (bool(result.final_state.observations) == (tick == 1)),
                str(result.final_state.scheduler),
            )
            target = OUT / f"control-{tick}-{action}"
            if not target.exists():
                shutil.copytree(saved, target)
            (OUT / f"control-{tick}-{action}-input.json").write_bytes(
                execution.canonical_bytes
            )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for directory in ("g1", "g2"):
            shutil.copytree(ROOT / "fixtures" / directory, root / directory)
        data = json.loads(SCENARIO.read_bytes())
        data["world_claims"].append(
            {
                "id": "VA-LEAK",
                "classification": "actor-private",
                "source_ids": ["I1955-C1"],
                "statement": "VA-AUDIT-SECRET",
                "origin": "real-oss",
                "status": "provisional",
            }
        )
        data["participant_profile"]["initial_claim_ids"].append("VA-LEAK")
        data["actor_view"]["initial_claim_ids"].append("VA-LEAK")
        path = root / "g2/va.json"
        path.write_bytes(canonical_json_bytes(data))
        session = LocalSession.start(load_scenario_execution(path))
        result = session.finish()
        denied = False
        try:
            employee_package(
                session.execution, result, actor_id=session.execution.actor_id
            )
        except PublicationError:
            denied = True
        record("audit-source-relabel-denied", True, denied)
        record(
            "audit-source-absent-catalog",
            False,
            b"VA-AUDIT-SECRET"
            in search_evidence(session.execution, result, role="researcher"),
        )
    for case in ("cancelled", "repeated", "submitted"):
        old = next((ROOT / "tests/fixtures/g6" / case).glob("local-*"))
        legacy = load_local_run(old, s.execution).result
        record("legacy-" + case, False, b"LEV-" in public_evidence(s.execution, legacy))
    report = {
        "cases": cases,
        "artifact_comparison": comparisons,
        "scenario_content_id": s.execution.content_id,
        "scheduler": r.final_state.scheduler.as_dict()
        if hasattr(r.final_state.scheduler, "as_dict")
        else str(r.final_state.scheduler),
        "event_kinds": [e.kind.value for e in r.events],
        "manifest": json.loads((a / "manifest.json").read_bytes()),
    }
    (OUT / "results.json").write_bytes(canonical_json_bytes(report))
    print(json.dumps(cases, indent=2))
    return int(any(c["status"] == "FAIL" for c in cases))


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker(sys.argv[-1])
    else:
        sys.exit(main())
