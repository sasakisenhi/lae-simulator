"""Read-only interviews over a previously validated G7 personal package.

Only the caller holding the package may construct this service. The CLI obtains
it through employee_package, after store/replay validation and disclosure gates.
No simulation state, canonical history, or other participant is available here.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict

from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.interview_contract import (
    PROMPT_VERSION,
    GeneratedAnswer,
    GenerationFailure,
    InterviewGenerator,
    InterviewResult,
    Statement,
    parse_statements,
)
from lae_simulator.simulation.interview_validation import (
    CHECKER_VERSION,
    package_support,
    private_identifiers,
    support_catalog,
    validate_statements,
)

__all__ = ["FixedResponseGenerator", "GeneratedAnswer", "InterviewGenerator", "InterviewResult",
           "InterviewService", "Statement"]


class FixedResponseGenerator:
    """Deterministic offline adapter. Exhaustion abstains, never invents an answer."""

    name = "fixed-response"
    version = "2"
    model = "fixture"
    settings = "no external service"

    def __init__(self, answers: tuple[GeneratedAnswer, ...]):
        self._answers = iter(answers)

    def generate(self, *, question: str, package: dict[str, object],
                 retrieved: tuple[dict[str, object], ...], prompt_version: str) -> GeneratedAnswer:
        del question, package, retrieved, prompt_version
        return next(self._answers, GeneratedAnswer((Statement("わかりません。", "unknown"),),
                    self.name, self.version, self.model, self.settings))


class InterviewService:
    """Attempt history is private; only adopted responses enter public history."""

    def __init__(self, package_bytes: bytes, generator: InterviewGenerator, *, actor_id: str,
                 run_id: str = "unspecified", prompt_version: str = PROMPT_VERSION):
        package = json.loads(package_bytes)
        if not isinstance(package, dict) or package.get("actor_id") != actor_id:
            raise ValueError("unavailable")
        if prompt_version != PROMPT_VERSION:
            raise ValueError("unsupported prompt version")
        self._package = package
        self._package_digest = content_digest(canonical_json_bytes(package))
        self._actor_id, self._run_id = actor_id, run_id
        self._generator, self._prompt_version = generator, prompt_version
        self._attempts: list[dict[str, object]] = []
        self._adopted: list[Statement] = []
        self._public: list[dict[str, object]] = []
        self._results: list[InterviewResult] = []

    def ask(self, question_id: str, question: str) -> InterviewResult:
        if not question_id.strip() or not question.strip() or len(question) > 16000:
            raise ValueError("invalid question")
        supports = package_support(self._package)
        # A finite personal catalog, not a search against the world or raw logs.
        retrieved = support_catalog(self._package)
        request = {"question": question, "package": self._package, "retrieved": retrieved,
                   "prompt_version": self._prompt_version}
        failure: str | None = None
        execution: dict[str, object] = {}
        raw_statements: list[dict[str, object]] = []
        statements: tuple[Statement, ...] = ()
        try:
            generated = self._generator.generate(question=question, package=deepcopy(self._package),
                                                 retrieved=deepcopy(retrieved), prompt_version=self._prompt_version)
            execution = deepcopy(generated.execution)
            raw_statements = [asdict(statement) for statement in generated.statements]
            # Apply the same full schema to fixed and remote generators.
            statements = parse_statements(json.dumps({"statements": raw_statements}, allow_nan=False))
        except GenerationFailure as error:
            failure, execution = error.code, deepcopy(error.execution)
        except Exception:  # noqa: BLE001 -- untrusted generator boundary, audited failure
            failure = "generator-error"  # raw exceptions may contain API keys or forbidden information
        if failure:
            status = ("not-ready" if failure in {"missing-credentials", "missing-approval", "missing-sdk", "pricing-expired"}
                      else "budget-exceeded" if failure == "budget-exceeded" else "generation-failed")
            checks: list[dict[str, object]] = []
        else:
            status, checks = validate_statements(statements, supports, tuple(self._adopted), private_identifiers(self._package))
        accepted = status == "accepted"
        answer = " ".join(statement.text for statement in statements) if accepted else None
        if accepted:
            self._adopted.extend(statements)
            self._public.append({"question_id": question_id, "question": question, "answer": answer,
                                 "epistemic_kinds": [row.epistemic_kind for row in statements],
                                 "synthetic": True, "validation": "restricted-quotation-or-abstention"})
        audit: dict[str, object] = {
            "schema": "interview-audit-2", "run_id": self._run_id,
            "attempt": len(self._attempts) + 1, "question_id": question_id, "question": question,
            "actor_id": self._actor_id, "package_digest": self._package_digest,
            "retrieved_support_ids": sorted(supports),
            "cited_support_ids": sorted({sid for row in statements for sid in row.private_support_ids}),
            "generator": {"provider": self._generator.name, "version": self._generator.version,
                          "model": self._generator.model, "settings": self._generator.settings},
            "prompt_template_version": self._prompt_version,
            "input_digest": content_digest(canonical_json_bytes(request)),
            "answer": raw_statements, "checks": checks, "status": status,
            "failure_type": failure, "execution": execution, "checker_version": CHECKER_VERSION,
            "meaning_validation": "restricted quotations only; paraphrases INCONCLUSIVE",
            "reason": failure or ("validated-restricted-response" if accepted else
                                   "independent-semantic-review-required" if status == "inconclusive" else
                                   "empty-response" if status == "unanswerable" else "failed-check"),
        }
        self._attempts.append(deepcopy(audit))
        result = InterviewResult(status, answer, tuple(row.epistemic_kind for row in statements) if accepted else (), audit)
        self._results.append(result)
        return result

    def audit_records(self) -> bytes:
        return canonical_json_bytes({"schema": "interview-audits-2", "attempts": self._attempts})

    def public_history(self) -> bytes:
        return canonical_json_bytes({"schema": "interview-public-1", "answers": self._public})

    def publication(self, result: InterviewResult) -> bytes:
        if not any(item is result for item in self._results):
            raise ValueError("unavailable")
        if result.status != "accepted" or result.answer is None:
            return canonical_json_bytes({"status": result.status, "answer": None})
        return canonical_json_bytes({"status": "accepted", "answer": result.answer,
                                     "epistemic_kinds": list(result.epistemic_kinds),
                                     "synthetic": True, "validation": "restricted-quotation-or-abstention"})
