"""Describe fixed VB contrasts without changing their conditions."""

import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs/vb-evidence"


def differences(a, b, path=""):
    if type(a) is not type(b):
        return [{"path": path, "control": a, "intervention": b}]
    if isinstance(a, dict):
        return [
            row
            for key in sorted(a.keys() | b.keys())
            for row in differences(a.get(key), b.get(key), path + "/" + key)
        ]
    if isinstance(a, list):
        return [
            row
            for i in range(max(len(a), len(b)))
            for row in differences(
                a[i] if i < len(a) else None,
                b[i] if i < len(b) else None,
                path + "/" + str(i),
            )
        ]
    return [] if a == b else [{"path": path, "control": a, "intervention": b}]


def main():
    rows = []
    for case in (
        "knowledge",
        "information",
        "access",
        "tool",
        "peer",
        "ai",
        "negative",
    ):
        a = OUT / f"{case}-control-1"
        b = OUT / f"{case}-intervention-1"
        if not (b / "summary.json").exists():
            rows.append(
                {
                    "case": case,
                    "verdict": "NOT EVALUATED",
                    "reason": "Intervention rejected before run creation",
                    "failure": json.loads((b / "failure.json").read_bytes()),
                }
            )
            continue
        ca = json.loads((a / "summary.json").read_bytes())
        cb = json.loads((b / "summary.json").read_bytes())
        sa = json.loads(next(a.glob("local-*/scenario.json")).read_bytes())
        sb = json.loads(next(b.glob("local-*/scenario.json")).read_bytes())
        ea = [{k: v for k, v in e.items() if k != "run_id"} for e in ca["events"]]
        eb = [{k: v for k, v in e.items() if k != "run_id"} for e in cb["events"]]
        event_diff = differences(ea, eb)
        rows.append(
            {
                "case": case,
                "scenario_differences": differences(sa, sb),
                "policy_control": [x["selected"] for x in ca["trace"]],
                "policy_intervention": [x["selected"] for x in cb["trace"]],
                "observation_differences": differences(
                    ca["trace"][-1]["observation"], cb["trace"][-1]["observation"]
                ),
                "first_event_difference": event_diff[0] if event_diff else None,
                "times": [ca["logical_time"], cb["logical_time"]],
                "outcomes": [ca["outcome"], cb["outcome"]],
                "replay_and_storage": all(
                    x["replay_equal"] and x["stored_equal"] for x in (ca, cb)
                ),
            }
        )
    (OUT / "contrasts.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )
    m = json.loads((OUT / "target-manifest.json").read_bytes())
    changed = [
        p
        for p, h in m["files"].items()
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h
    ]
    (OUT / "target-recheck.json").write_text(
        json.dumps({"changed_files": changed, "pass": not changed}, indent=2)
    )


if __name__ == "__main__":
    main()
