"""Fixed OpenAI-only G8 protocol. Adds pacing, never replaces generated results."""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from lae_simulator.adapters.interview_config import (
    Approval,
    EvaluationConfig,
    GeneratorConfig,
)
from lae_simulator.adapters.interview_remote import OpenAITransport, ProviderReply
from lae_simulator.interview_evaluation import QuestionSet, evaluate
from lae_simulator.simulation.canonical_store import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/g8-openai-acceptance-20261109"


class PacedOpenAITransport(OpenAITransport):
    """One real SDK call per request, at least 65 seconds between starts."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep,
                 record: Callable[[dict[str, object]], None] = lambda _: None):
        self.clock, self.sleeper, self.record = clock, sleeper, record
        self.previous_start: float | None = None
        self.calls = 0

    def request(self, config: GeneratorConfig, api_key: str, prompt: str) -> ProviderReply:
        if self.previous_start is not None:
            remaining = 65.0 - (self.clock() - self.previous_start)
            while remaining > 0:
                self.sleeper(min(remaining, 30.0))
                remaining = 65.0 - (self.clock() - self.previous_start)
        self.previous_start = self.clock()
        self.calls += 1
        self.record({"stage": "sdk-request-start", "request": self.calls,
                     "monotonic_start": self.previous_start, "minimum_interval_seconds": 65})
        # No mock reply, SDK retry, context change, token-limit change, or fallback.
        return super().request(config, api_key, prompt)


def main() -> None:
    import hashlib

    manifest = json.loads((PLAN / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("fixed protocol digest mismatch")
    config = EvaluationConfig.model_validate_json((PLAN / "config.json").read_bytes())
    assert config.mode == "single" and config.generators[0].provider == "openai"
    assert config.generators[0].max_attempts == 1 and config.generators[0].retry_on == ()
    assert config.generators[0].max_output_tokens == 1024 and config.budget.max_requests == 11
    questions = QuestionSet.model_validate_json((PLAN / "questions.json").read_bytes())
    package = (PLAN / "employee-package.json").read_bytes()
    approval = tuple(Approval.model_validate(row) for row in json.loads((PLAN / "approval.json").read_bytes()))
    protocol = json.loads((PLAN / "protocol.json").read_bytes())
    output = Path(protocol["evaluation_output"])

    def record(row: dict[str, object]) -> None:
        fd = os.open(output / "pacing.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(canonical_json_bytes(row) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"request_started": row["request"], "planned_total": 11}), flush=True)

    transport = PacedOpenAITransport(record=record)
    # Replace construction only. Every request still uses OpenAITransport.request
    # and its fixed endpoint/settings, and the ordinary budget and consent gates.
    with patch("lae_simulator.adapters.interview_remote.OpenAITransport", return_value=transport):
        result = evaluate(config, package, questions, actor_id=json.loads(package)["actor_id"],
                          run_id=protocol["simulation_run_id"], output=output, approvals=approval)
    print(json.dumps({"acceptance": result["acceptance"], "output": str(output),
                      "reserved_requests": result["remote_attempts_reserved"]}), flush=True)


if __name__ == "__main__":
    main()
