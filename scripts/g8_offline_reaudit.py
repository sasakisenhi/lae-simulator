"""Reaudit pinned G8 evidence without SDKs, network or rewriting historical runs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from lae_simulator.simulation.interview_contract import parse_statements
from lae_simulator.simulation.interview_validation import (
    CHECKER_VERSION,
    package_support,
    private_identifiers,
    validate_statements,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/g8-offline-repair-20261109"
OUT = BASE / "reaudit-final"
RUNS = ("g8-live-comparison-20261109-approved", "g8-live-comparison-20261109-repeat-1")
DECISIONS = {"accepted": "ACCEPT", "rejected": "REJECT", "inconclusive": "NEEDS_REVIEW"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name, value):
    path = OUT / name
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT, help="new directory only; never overwrite results")
    OUT = parser.parse_args().output.resolve()
    OUT.mkdir(exist_ok=False)
    pinned = json.loads((BASE / "prior-evidence-hashes.json").read_bytes())
    assert all(digest(ROOT / path) == expected for path, expected in pinned.items())
    spec = importlib.util.spec_from_file_location("g8_legacy_validator", BASE / "legacy_validator.py")
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy
    spec.loader.exec_module(legacy)
    inventory = []
    for path in sorted(pinned):
        if path.endswith("evaluation.json"):
            data = json.loads((ROOT / path).read_bytes())
            inventory.append({"path": path, "evaluation_id": data["evaluation_id"],
                              "reserved_requests": data["remote_attempts_reserved"],
                              "acceptance": data["acceptance"]})
    rows, revised = [], []
    for run in RUNS:
        directory = ROOT / ".lae-runs" / run
        inputs = json.loads((directory / "inputs.json").read_bytes())
        package = inputs["package"]
        supports, private = package_support(package), private_identifiers(package)
        for provider in (1, 2):
            old_history, new_history = [], []
            for raw in (directory / f"provider-{provider}/attempts.jsonl").read_bytes().splitlines():
                audit = json.loads(raw)
                attempts = audit.get("execution", {}).get("attempts", [])
                responses = [x for x in attempts if x.get("provider_response")]
                row = {"run": run, "provider": audit["generator"]["provider"],
                       "model": audit["generator"]["model"], "question": audit["question_id"],
                       "send_attempts": len(attempts), "api_response_success": bool(responses),
                       "generation_complete": bool(responses) and audit["failure_type"] not in {"incomplete-output", "refused"},
                       "structure": "NOT_RUN", "reference_access": "NOT_RUN", "disclosure": "NOT_RUN",
                       "support": "NOT_RUN", "cross_question": "NOT_RUN", "old_semantics": "NOT_RUN", "new_semantics": "NOT_RUN",
                       "old_status": audit["status"], "new_decision": None, "public_allowed": False,
                       "failure": audit["failure_type"],
                       "finish_reason": None, "reasoning_tokens": None,
                       "output_tokens": responses[0]["usage"]["output_tokens"] if responses else None,
                       "max_output_tokens": inputs["config"]["generators"][provider - 1]["max_output_tokens"]}
                if not audit["failure_type"]:
                    statements = parse_statements(json.dumps({"statements": audit["answer"]}))
                    old_status, old_checks = legacy.validate_statements(statements, supports, tuple(old_history), private)
                    assert old_status == audit["status"] and old_checks == audit["checks"]
                    if old_status == "accepted":
                        old_history.extend(statements)
                    status, checks = validate_statements(statements, supports, tuple(new_history), private)
                    if status == "accepted":
                        new_history.extend(statements)
                    semantic = lambda values: "FAIL" if any(x["semantics"] == "FAIL" for x in values) else "PASS" if all(x["semantics"] == "PASS" for x in values) else "NEEDS_REVIEW"
                    for stage in ("reference_access", "disclosure", "support", "cross_question"):
                        row[stage] = ("FAIL" if any(c[stage] == "FAIL" for c in checks) else
                                      "NEEDS_REVIEW" if any(c[stage] == "UNKNOWN" for c in checks) else "PASS")
                    row.update(structure="PASS", old_semantics=semantic(old_checks), new_semantics=semantic(checks),
                               new_decision=DECISIONS[status], public_allowed=status == "accepted")
                    revised.append({"run": run, "provider": row["provider"], "model": row["model"],
                                    "question": row["question"], "question_text": audit["question"],
                                    "answer": audit["answer"], "old_status": old_status, "old_checks": old_checks,
                                    "new_decision": DECISIONS[status], "new_checks": checks,
                                    "reason": "value labels and translations are not semantic evidence; unverified meaning withheld"
                                              if old_status == "rejected" and status == "inconclusive" else
                                              "restricted proof unchanged; unverified prose remains withheld",
                                    "checker_version": CHECKER_VERSION, "public_allowed": status == "accepted"})
                rows.append(row)
    assert len(rows) == 44 and len(revised) == 17
    assert sum(r["failure"] == "rate-limit" for r in rows) == 24
    assert sum(r["api_response_success"] for r in rows) == 19
    assert all(digest(ROOT / path) == expected for path, expected in pinned.items())
    with (OUT / "question-stages.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json("reaudited-answers.json", revised)
    write_json("evidence-inventory.json", inventory)
    summary = []
    for provider in ("gemini", "openai"):
        subset = [r for r in rows if r["provider"] == provider]
        summary.append({"provider": provider, "model": subset[0]["model"], "sent": sum(r["send_attempts"] for r in subset),
                        "api_response_success": sum(r["api_response_success"] for r in subset),
                        "generation_complete": sum(r["generation_complete"] for r in subset),
                        "structure_pass": sum(r["structure"] == "PASS" for r in subset),
                        "old_status": dict(Counter(r["old_status"] for r in subset)),
                        "new_decisions": dict(Counter(r["new_decision"] for r in subset if r["new_decision"])),
                        "new_semantics": dict(Counter(r["new_semantics"] for r in subset)),
                        "public_allowed": sum(r["public_allowed"] for r in subset)})
    write_json("summary.json", {"acceptance_task_6_3": "INCONCLUSIVE", "providers": summary,
                               "prior_evidence_verified_files": len(pinned),
                               "legacy_diagnostics": "finish/reasoning/status detail unknown; never inferred as fact",
                               "duplicates": "documentation copies and zero-send NOT READY run are inventoried, not double-counted"})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    with patch("socket.socket.connect", side_effect=AssertionError("offline reaudit forbids network")):
        main()
