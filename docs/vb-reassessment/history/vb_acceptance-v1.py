"""VB independent fixed-plan runs, without importing implementation tests."""

import hashlib
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
from lae_simulator.simulation.local_model import PolicyInput
from lae_simulator.simulation.local_policy import select_local_candidate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/vb-evidence"


def worker(case, arm, destination):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for d in ("g1", "g2"):
            shutil.copytree(ROOT / "fixtures" / d, root / d)
        data = json.loads((root / "g2/scenario-collaboration.json").read_bytes())
        if arm == "intervention":
            if case == "knowledge":
                for obj in (data["actor_view"], data["participant_profile"]):
                    obj["initial_claim_ids"].append("PEER-NOTE")
            if case == "access":
                data["participant_profile"]["permissions"].remove(
                    {"resource_id": "D02", "action": "read"}
                )
            if case == "tool":
                data["participant_profile"]["operation_capabilities"].remove(
                    "code.search"
                )
            if case in ("peer", "ai"):
                data["collaboration"]["rules"][0 if case == "peer" else 2][
                    "delay_ticks"
                ] = 45
        path = root / "g2/vb.json"
        path.write_bytes(canonical_json_bytes(data))
        execution = load_scenario_execution(path)
        s = LocalSession.start(execution)
        trace = []

        def measure(label):
            before = s.observation
            selected = select_local_candidate(PolicyInput(before))
            trace.append(
                {
                    "label": label,
                    "observation": asdict(before),
                    "selected": selected.id if selected else None,
                    "event_index": len(s.events) if hasattr(s, "events") else None,
                }
            )

        def read():
            s.select("T01")
            s.perform(
                kind=LocalEventKind.DOCUMENT_READ,
                candidate_id="T01",
                target_id="D01",
                input_version="B0",
            )

        def patch(p):
            s.select("T10")
            s.perform(
                kind=LocalEventKind.PATCH_APPLIED,
                candidate_id="T10",
                patch_id=p,
                input_version=s.state.workspace_version,
            )

        def check(c):
            s.select("T11")
            s.perform(
                kind=LocalEventKind.CHECK_EVALUATED,
                candidate_id="T11",
                check_id=c,
                input_version=s.state.workspace_version,
            )

        measure("initial")
        if case == "negative" and arm == "intervention":
            s.select("T15")
        if case in ("knowledge", "negative"):
            measure("same-time")
        else:
            read()
            if case == "information":
                s.select("T03")
                s.perform(
                    kind=LocalEventKind.SEARCH,
                    candidate_id="T03",
                    query="metadata" if arm == "control" else "VA-NO-SUCH-TOKEN-94821",
                    input_version="B0",
                )
            elif case == "access":
                check("C01")
            elif case in ("peer", "ai"):
                candidate = "T07" if case == "peer" else "T08"
                rule = "PEER-ANSWER" if case == "peer" else "AI-PROPOSAL"
                s.select(candidate)
                event = s.request(
                    candidate_id=candidate, rule_id=rule, input_ids=("D01",)
                )
                rid = event.collaboration.request_id
                s.wait_for(rid, 1)
                for _ in range(8):
                    request = next(
                        r for r in s.state.collaboration.requests if r.id == rid
                    )
                    if request.delivered_tick is not None:
                        s.observe_response(rid, 1)
                        break
                    if s.state.outcome is not None or request.status in (
                        "expired",
                        "cancelled",
                    ):
                        break
                    s.advance_next()
            elif case.startswith("demo-"):
                if case == "demo-mistake":
                    patch("P3")
                    check("C02")
                    s.revert_patch("P3")
                if case != "demo-no-ai":
                    patch("P1")
                    check("C01")
                    s.submit(
                        "T14",
                        target_id="SIMULATED-SUBMISSION",
                        explanation="VB bounded synthetic demo",
                        check_event_ids=(s.state.observations[-1].event_id,),
                        coverage="modeled",
                        limitations="C11/C12 unexecuted",
                    )
            if s.state.outcome is None:
                measure("after-intervention")
        result = s.finish()
        p = save_local_run(execution, result, destination)
        restored = load_local_run(p, execution).result
        summary = {
            "case": case,
            "arm": arm,
            "content_id": execution.content_id,
            "trace": trace,
            "replay_equal": replay_local(execution, result.initial_state, result.events)
            == result.final_state,
            "stored_equal": restored == result,
            "outcome": result.final_state.outcome,
            "logical_time": result.final_state.logical_time,
            "events": [
                e.as_dict() if hasattr(e, "as_dict") else asdict(e)
                for e in result.events
            ],
        }
        (Path(destination) / "summary.json").write_bytes(canonical_json_bytes(summary))


def main():
    for case in (
        "knowledge",
        "information",
        "access",
        "tool",
        "peer",
        "ai",
        "negative",
        "demo-normal",
        "demo-mistake",
        "demo-no-ai",
    ):
        for arm in (
            ("control",) if case.startswith("demo-") else ("control", "intervention")
        ):
            for repeat, seed in ((1, "2"), (2, "71")):
                dest = OUT / f"{case}-{arm}-{repeat}"
                dest.mkdir(exist_ok=True)
                if (dest / "summary.json").exists():
                    continue
                completed = subprocess.run(
                    [sys.executable, __file__, "worker", case, arm, str(dest)],
                    env={**os.environ, "PYTHONHASHSEED": seed},
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode:
                    (dest / "failure.json").write_text(
                        json.dumps(
                            {"exit": completed.returncode, "stderr": completed.stderr}
                        )
                    )
    comparisons = []
    for case in (
        "knowledge",
        "information",
        "access",
        "tool",
        "peer",
        "ai",
        "negative",
        "demo-normal",
        "demo-mistake",
        "demo-no-ai",
    ):
        arms = ("control",) if case.startswith("demo-") else ("control", "intervention")
        summaries = []
        for arm in arms:
            a = OUT / f"{case}-{arm}-1"
            b = OUT / f"{case}-{arm}-2"
            if not (a / "summary.json").exists() or not (b / "summary.json").exists():
                comparisons.append(
                    {
                        "case": case,
                        "arm": arm,
                        "not_evaluated": "worker rejected; see failure.json",
                    }
                )
                continue
            equal = {
                str(p.relative_to(a)): hashlib.sha256(p.read_bytes()).hexdigest()
                == hashlib.sha256((b / p.relative_to(a)).read_bytes()).hexdigest()
                for p in a.rglob("*")
                if p.is_file()
            }
            summaries.append(json.loads((a / "summary.json").read_bytes()))
            comparisons.append(
                {
                    "case": case,
                    "arm": arm,
                    "repeat_all_files_equal": all(equal.values()),
                    "files": equal,
                }
            )
        (OUT / f"{case}-comparison.json").write_bytes(canonical_json_bytes(summaries))
    (OUT / "repeat-comparison.json").write_bytes(canonical_json_bytes(comparisons))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        worker(*sys.argv[2:])
    else:
        main()
