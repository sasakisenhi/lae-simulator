"""Local interview evaluation runner, private sidecars, and review metrics.

This is an application boundary, outside the deterministic simulation core.
Providers receive identical fixed inputs and never see each other's responses.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field

from lae_simulator.adapters.interview_budget import BudgetLedger
from lae_simulator.adapters.interview_config import (
    Approval,
    EvaluationConfig,
    StrictConfig,
)
from lae_simulator.adapters.interview_remote import (
    GeminiInterviewGenerator,
    OpenAIInterviewGenerator,
)
from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.interview import (
    FixedResponseGenerator,
    InterviewGenerator,
    InterviewService,
)


class Question(StrictConfig):
    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=16000)
    category: Literal["normal", "grounded", "hidden-cause", "leading", "new-fact", "paraphrase",
                      "contradiction", "misunderstanding", "ambiguous", "unknown", "unanswerable"]
    expected_abstention: bool | None = None


class QuestionSet(StrictConfig):
    questions: tuple[Question, ...] = Field(min_length=1, max_length=100)

    def pairs(self) -> tuple[tuple[str, str], ...]:
        if len({row.id for row in self.questions}) != len(self.questions):
            raise ValueError("duplicate question IDs")
        return tuple((row.id, row.text) for row in self.questions)


def approval_requests(config: EvaluationConfig, package: bytes, questions: QuestionSet, *, evaluation_id: str) -> bytes:
    return canonical_json_bytes([Approval(
        provider=row.provider, model=row.model, evaluation_id=evaluation_id,
        package_digest=content_digest(canonical_json_bytes(json.loads(package))),
        questions_digest=content_digest(canonical_json_bytes(questions.pairs())),
        config_digest=config.digest(),
    ).model_dump(mode="json") for row in config.generators if row.provider != "fixed"])


def _write_new(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _append(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "ab") as stream:
        stream.write(value.rstrip(b"\n") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def evaluate(config: EvaluationConfig, package: bytes, questions: QuestionSet, *, actor_id: str,
             run_id: str, output: Path, approvals: tuple[Approval, ...] = ()) -> dict[str, object]:
    pairs = questions.pairs()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    # A new directory defines one evaluation run. No append/resume may reset its budget.
    ledger = BudgetLedger(config.budget, checkpoint=lambda value: _append(output / "ledger.jsonl", canonical_json_bytes(value)))
    _write_new(output / "inputs.json", canonical_json_bytes({"simulation_run_id": run_id,
        "package": json.loads(package), "questions": questions.model_dump(mode="json"),
        "config": config.model_dump(mode="json"), "config_digest": config.digest(),
        "approvals": [grant.model_dump(mode="json") for grant in approvals]}))
    summaries: list[dict[str, object]] = []
    live_responses = False
    for index, row in enumerate(config.generators):
        generator: InterviewGenerator
        if row.provider == "fixed":
            generator = FixedResponseGenerator(())
        else:
            price = next(price for price in config.prices if (price.provider, price.model) == (row.provider, row.model))
            grant = next((grant for grant in approvals if (grant.provider, grant.model) == (row.provider, row.model)), None)
            adapter = GeminiInterviewGenerator if row.provider == "gemini" else OpenAIInterviewGenerator
            generator = adapter(row, price, ledger, approval=grant, config_digest=config.digest(), evaluation_id=str(output.resolve()), questions=pairs)
        service = InterviewService(package, generator, actor_id=actor_id, run_id=run_id, prompt_version=row.prompt_version)
        prefix = output / f"provider-{index + 1}"
        prefix.mkdir(mode=0o700)
        results: list[dict[str, object]] = []
        provider_live = False
        citation_count = valid_citation_count = 0
        api_input = api_output = unknown_usage = 0
        latency = 0.0
        estimated_cost = Decimal(0)
        for question in questions.questions:
            result = service.ask(question.id, question.text)
            # Durably record the attempt before publishing any adopted answer.
            _append(prefix / "attempts.jsonl", canonical_json_bytes(result.audit))
            available = set(cast(list[str], result.audit["retrieved_support_ids"]))
            for statement in cast(list[dict[str, Any]], result.audit["answer"]):
                for sid in statement["private_support_ids"]:
                    citation_count += 1
                    valid_citation_count += sid in available
            metadata = result.audit.get("execution", {})
            if isinstance(metadata, dict):
                provider_live |= any(attempt.get("transport") == "sdk" and attempt.get("provider_response")
                                     for attempt in metadata.get("attempts", []))
                for attempt in metadata.get("attempts", []):
                    latency += float(attempt.get("latency_seconds", 0))
                    usage = attempt.get("usage")
                    if usage and usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
                        api_input += usage["input_tokens"]
                        api_output += usage["output_tokens"]
                    else:
                        unknown_usage += 1
                    if attempt.get("estimated_cost_usd") is not None:
                        estimated_cost += Decimal(attempt["estimated_cost_usd"])
            live_responses |= provider_live
            abstention = result.status == "accepted" and set(result.epistemic_kinds) <= {"unknown", "not_remembered"}
            results.append({"question_id": question.id, "status": result.status,
                            "abstention": abstention,
                            "expected_abstention": question.expected_abstention,
                            "abstention_match": (abstention == question.expected_abstention
                                                 if question.expected_abstention is not None and result.status == "accepted" else None)})
        _write_new(prefix / "public.json", service.public_history())
        summaries.append({"provider": row.provider, "model": row.model, "results": results,
                          "metrics": {"citation_id_precision": valid_citation_count / citation_count if citation_count else None,
                                      "citation_count": citation_count, "api_reported_input_tokens": api_input,
                                      "api_reported_output_tokens": api_output, "unknown_usage_attempts": unknown_usage,
                                      "latency_seconds": latency, "estimated_cost_usd_for_reported_usage": str(estimated_cost),
                                      "scope": "ID validity is not semantic entailment; injected transports are offline tests"},
                          "live_api_response_observed": provider_live,
                          "acceptance": "INCONCLUSIVE" if provider_live else "NOT READY"})
    report: dict[str, object] = {"schema": "g8-evaluation-1", "simulation_run_id": run_id,
        "mode": config.mode, "providers": summaries, "ledger": ledger.snapshot(),
        "live_evaluation": live_responses, "remote_attempts_reserved": ledger.requests,
        "evaluation_id": str(output.resolve()),
        "acceptance": "INCONCLUSIVE" if live_responses else "NOT READY",
        "manual_review": {name: None for name in ("unsupported_fact_rate", "support_entailment_accuracy",
            "appropriate_unknown_rate", "leading_question_compliance_rate", "paraphrase_consistency", "japanese_naturalness")},
        "metric_definitions": {
            "unsupported_fact_rate": "human-confirmed unsupported concrete claims / all concrete claims, including rejected attempts",
            "support_entailment_accuracy": "human-confirmed supporting citations / all citations; ID existence alone is insufficient",
            "appropriate_unknown_rate": "appropriate abstentions / human-labelled unknown-required questions; API failures are not abstentions",
            "leading_question_compliance_rate": "human-confirmed invented premises adopted / leading questions",
            "paraphrase_consistency": "human-confirmed consistent episode/topic claim groups / reviewed groups",
            "japanese_naturalness": "independent human rubric 1-5; not generator self-scoring",
            "latency_tokens_cost": "per-attempt execution metadata; failed/unknown usage reservations are separate from API counts"},
        "limitations": "No independent semantic or live acceptance verdict is inferred from schema success. Fixed runs test plumbing only."}
    _write_new(output / "evaluation.json", canonical_json_bytes(report))
    return report
