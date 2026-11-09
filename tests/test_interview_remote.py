from __future__ import annotations

import json
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from lae_simulator.adapters.interview_budget import BudgetLedger
from lae_simulator.adapters.interview_config import (
    Approval,
    Budget,
    EvaluationConfig,
    GeneratorConfig,
    Price,
)
from lae_simulator.adapters.interview_remote import (
    GeminiInterviewGenerator,
    GeminiTransport,
    OpenAIInterviewGenerator,
    OpenAITransport,
    ProviderReply,
)
from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.interview import InterviewService
from lae_simulator.simulation.interview_contract import (
    PROMPT_VERSION,
    GenerationFailure,
    parse_statements,
)

PACKAGE: dict[str, object] = {"actor_id":"A", "background":[], "perceptions":[], "belief_history":[]}
QUESTIONS = (("Q", "知らない原因は？"),)
UNKNOWN = json.dumps({"statements":[{"text":"わかりません。", "epistemic_kind":"unknown", "private_support_ids":[],
                                     "topic":None,"value":None,"episode":None}]}, ensure_ascii=False)


def price(provider: str = "openai") -> Price:
    return Price(provider=provider, model="gpt-6.1-terra" if provider == "openai" else "gemini-2.5-flash",  # type: ignore[arg-type]
                 input_per_million_usd="1", output_per_million_usd="5", source="fixture",
                 checked_on=date.today().isoformat(), valid_until=(date.today()+timedelta(days=1)).isoformat())


def budget(**changes: Any) -> Budget:
    return Budget.model_validate({"max_requests":3,"max_request_tokens":100000,"max_total_tokens":300000,
                                  "max_estimated_cost_usd":"1", **changes})


class FakeTransport:
    def __init__(self, replies: list[ProviderReply | Exception]):
        self.replies = iter(replies)
        self.calls: list[tuple[GeneratorConfig, str]] = []

    def request(self, config: GeneratorConfig, api_key: str, prompt: str) -> ProviderReply:
        self.calls.append((config, prompt))
        result = next(self.replies)
        if isinstance(result, Exception):
            raise result
        return result


class RemoteTestSupport(unittest.TestCase):
    def generator(self, replies: list[ProviderReply | Exception], *, provider: str = "openai",
                  limits: Budget | None = None, approved: bool = True, **settings: Any) -> tuple[OpenAIInterviewGenerator | GeminiInterviewGenerator, FakeTransport]:
        config = GeneratorConfig.model_validate({"provider":provider,"model":price(provider).model,"api_key_env":"LAE_TEST_KEY",**settings})
        grant = Approval(provider=provider, model=config.model, package_digest=content_digest(canonical_json_bytes(PACKAGE)),  # type: ignore[arg-type]
                         questions_digest=content_digest(canonical_json_bytes(QUESTIONS)), config_digest="config", evaluation_id="unit-test",
                         approved=approved, approval_reference="unit-test mock only")
        transport = FakeTransport(replies)
        cls = OpenAIInterviewGenerator if provider == "openai" else GeminiInterviewGenerator
        generator = cls(config, price(provider), BudgetLedger(limits or budget()), approval=grant,
                        config_digest="config", evaluation_id="unit-test", questions=QUESTIONS, transport=transport)
        return generator, transport

    def generate(self, generator: OpenAIInterviewGenerator | GeminiInterviewGenerator, **changes: Any) -> object:
        return generator.generate(**{"question":QUESTIONS[0][1], "package":PACKAGE, "retrieved":(), "prompt_version":PROMPT_VERSION, **changes})

class RemoteTests(RemoteTestSupport):
    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_both_providers_account_usage_and_same_allowed_payload(self) -> None:
        for provider in ("gemini", "openai"):
            with self.subTest(provider=provider):
                generator, transport = self.generator([ProviderReply(UNKNOWN, 100, 20, price(provider).model)], provider=provider)
                result = self.generate(generator)
                self.assertEqual(result.statements[0].epistemic_kind, "unknown")  # type: ignore[attr-defined]
                self.assertEqual(generator.ledger.tokens, 120)
                self.assertEqual(generator.ledger.estimated_cost, Decimal("0.0002"))
                payload = json.loads(transport.calls[0][1])
                self.assertEqual(payload["package"], PACKAGE)
                self.assertNotIn("test-secret", transport.calls[0][1])
                self.assertNotIn("world", payload)

    def test_missing_credentials_is_not_ready_without_transport(self) -> None:
        generator, transport = self.generator([])
        with patch.dict(os.environ, {}, clear=True):
            service = InterviewService(canonical_json_bytes(PACKAGE), generator, actor_id="A")
            result = service.ask(*QUESTIONS[0])
        self.assertEqual(result.status, "not-ready")
        self.assertEqual(result.audit["failure_type"], "missing-credentials")
        self.assertEqual(transport.calls, [])

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_approval_is_exact_and_provider_scoped(self) -> None:
        for changes in ({}, {"question":"different"}, {"package": {**PACKAGE, "actor_id":"B"}}, {"prompt_version":"other"}):
            generator, transport = self.generator([], approved=bool(changes))
            with self.assertRaisesRegex(GenerationFailure, "missing-approval"):
                self.generate(generator, **changes)
            self.assertEqual(transport.calls, [])

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_timeout_retry_is_bounded_reserved_and_redacted(self) -> None:
        generator, transport = self.generator([TimeoutError("key=test-secret-value"), TimeoutError("again")],
                                               max_attempts=2, retry_on=("timeout",))
        with self.assertRaises(GenerationFailure) as caught:
            self.generate(generator)
        self.assertEqual(caught.exception.code, "timeout")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(generator.ledger.requests, 2)
        self.assertNotIn("test-secret", json.dumps(caught.exception.execution))
        self.assertEqual(len(caught.exception.execution["attempts"]), 2)  # type: ignore[arg-type]

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_auth_failure_and_invalid_json_do_not_retry(self) -> None:
        for reply, expected in ((GenerationFailure("authentication-failed"), "authentication-failed"),
                                (ProviderReply("not-json", 20, 20, "gpt-6.1-terra"), "invalid-output")):
            generator, transport = self.generator([reply], max_attempts=3, retry_on=("timeout",))
            with self.assertRaisesRegex(GenerationFailure, expected):
                self.generate(generator)
            self.assertEqual(len(transport.calls), 1)

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_request_token_cost_and_run_limits_stop_before_send(self) -> None:
        for limits in (budget(max_request_tokens=16), budget(max_total_tokens=16), budget(max_estimated_cost_usd="0")):
            generator, transport = self.generator([], limits=limits)
            with self.assertRaisesRegex(GenerationFailure, "budget-exceeded"):
                self.generate(generator)
            self.assertEqual(transport.calls, [])
        generator, transport = self.generator([ProviderReply(UNKNOWN, 10, 10, "gpt-6.1-terra")], limits=budget(max_requests=1))
        self.generate(generator)
        with self.assertRaisesRegex(GenerationFailure, "budget-exceeded"):
            self.generate(generator)
        self.assertEqual(len(transport.calls), 1)

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_missing_usage_and_actual_overrun_stop_further_calls(self) -> None:
        for reply, code in ((ProviderReply(UNKNOWN, None, None, "gpt-6.1-terra"), "usage-unavailable"),
                            (ProviderReply(UNKNOWN, 100001, 10, "gpt-6.1-terra"), "budget-exceeded")):
            generator, transport = self.generator([reply])
            with self.assertRaisesRegex(GenerationFailure, code):
                self.generate(generator)
            with self.assertRaisesRegex(GenerationFailure, "budget-exceeded"):
                self.generate(generator)
            self.assertEqual(len(transport.calls), 1)

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_price_expiry_model_replacement_and_secret_echo_fail_closed(self) -> None:
        generator, transport = self.generator([])
        generator.price = generator.price.model_copy(update={"valid_until":(date.today()-timedelta(days=1)).isoformat()})
        with self.assertRaisesRegex(GenerationFailure, "pricing-expired"):
            self.generate(generator)
        self.assertEqual(transport.calls, [])
        for reply, code in ((ProviderReply(UNKNOWN, 1, 1, "other-model"), "model-mismatch"),
                            (ProviderReply("test-secret-value", 1, 1, "gpt-6.1-terra"), "credential-in-output")):
            generator, _ = self.generator([reply])
            with self.assertRaisesRegex(GenerationFailure, code) as caught:
                self.generate(generator)
            self.assertNotIn("test-secret", json.dumps(caught.exception.execution))

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_ledger_persistence_failure_prevents_send(self) -> None:
        generator, transport = self.generator([])
        def failure(_: dict[str, object]) -> None:
            raise OSError("unwritable ledger")
        generator.ledger.checkpoint = failure
        with self.assertRaisesRegex(GenerationFailure, "ledger-persistence-failed"):
            self.generate(generator)
        self.assertEqual(transport.calls, [])

    def test_schema_rejects_duplicate_unknown_fields_wrong_types_and_nonfinite(self) -> None:
        for text in ('{"statements":[],"statements":[]}', '{"statements":[],"extra":1}', '{"statements":null}',
                     UNKNOWN.replace('"private_support_ids": []', '"private_support_ids": [1]'),
                     UNKNOWN.replace('"topic": null', '"topic": NaN'), UNKNOWN.replace('"text": "わかりません。"', '"text": 3')):
            with self.subTest(text=text), self.assertRaises(GenerationFailure):
                parse_statements(text)

    def test_configs_reject_invalid_prices_infinite_retry_and_hybrid_mode(self) -> None:
        for change in ({"max_attempts":0}, {"max_attempts":4}, {"temperature":float("nan")}, {"timeout_seconds":0.0}):
            with self.assertRaises(ValueError):
                GeneratorConfig.model_validate({"provider":"openai","model":"gpt-6.1-terra",**change})
        for cost in ("NaN", "-1", "Infinity"):
            with self.assertRaises(ValueError):
                Price.model_validate({**price().model_dump(), "input_per_million_usd":cost})
        with self.assertRaises(ValueError):
            EvaluationConfig.model_validate_json('{"mode":"fallback","generators":[],"prices":[],"budget":{}}')


class SDKShapeTests(unittest.TestCase):
    def test_openai_uses_responses_schema_no_store_no_sdk_retry_and_usage_on_refusal(self) -> None:
        fake = MagicMock()
        fake.__enter__.return_value = fake
        response = fake.responses.create.return_value
        response.output_text, response.model, response.status = UNKNOWN, "gpt-6.1-terra", "completed"
        response.output = []
        response.usage.input_tokens, response.usage.output_tokens = 13, 4
        config = GeneratorConfig(provider="openai",model="gpt-6.1-terra")
        with patch("openai.OpenAI", return_value=fake) as constructor:
            reply = OpenAITransport().request(config, "mock-key", "allowed input")
        self.assertEqual((reply.input_tokens, reply.output_tokens), (13,4))
        self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)
        kwargs = fake.responses.create.call_args.kwargs
        self.assertFalse(kwargs["store"])
        self.assertTrue(kwargs["text"]["format"]["strict"])
        self.assertEqual(kwargs["reasoning"], {"effort":"none"})
        self.assertNotIn("previous_response_id", kwargs)

    def test_gemini_counts_thinking_and_sets_json_schema_and_timeout_ms(self) -> None:
        fake = MagicMock()
        fake.__enter__.return_value = fake
        response = fake.models.generate_content.return_value
        response.text, response.model_version = UNKNOWN, "gemini-2.5-flash"
        response.candidates = [MagicMock(finish_reason="STOP")]
        response.usage_metadata.prompt_token_count, response.usage_metadata.total_token_count = 10, 25
        config = GeneratorConfig(provider="gemini",model="gemini-2.5-flash", timeout_seconds=2.0)
        with patch("google.genai.Client", return_value=fake) as constructor:
            reply = GeminiTransport().request(config, "mock-key", "allowed input")
        self.assertEqual(reply.output_tokens, 15)
        options = constructor.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 2000)
        self.assertEqual(options.retry_options.attempts, 1)
        settings = fake.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(settings.response_mime_type, "application/json")
        self.assertIsNotNone(settings.response_json_schema)
        self.assertEqual(settings.thinking_config.thinking_budget, 0)
        self.assertFalse(settings.automatic_continuation)
        self.assertFalse(settings.store)

class RemoteReviewRegressionTests(RemoteTestSupport):
    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_grant_cannot_be_reused_for_different_evaluation(self) -> None:
        generator, transport = self.generator([])
        generator.evaluation_id = "another-run"
        with self.assertRaisesRegex(GenerationFailure, "missing-approval"):
            self.generate(generator)
        self.assertEqual(transport.calls, [])

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_retrieval_must_be_derived_from_approved_package(self) -> None:
        generator, transport = self.generator([])
        with self.assertRaisesRegex(GenerationFailure, "invalid-retrieval"):
            self.generate(generator, retrieved=({"admin":"secret cause"},))
        self.assertEqual(transport.calls, [])

    @patch.dict(os.environ, {"LAE_TEST_KEY":"test-secret-value"})
    def test_post_response_ledger_failure_keeps_response_and_usage_in_audit(self) -> None:
        generator, _ = self.generator([ProviderReply(UNKNOWN, 10, 20, "gpt-6.1-terra")])
        calls = 0
        def persist(_: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("disk full")
        generator.ledger.checkpoint = persist
        service = InterviewService(canonical_json_bytes(PACKAGE), generator, actor_id="A")
        result = service.ask(*QUESTIONS[0])
        self.assertEqual(result.status, "generation-failed")
        self.assertEqual(result.audit["failure_type"], "ledger-persistence-failed")
        audit = json.loads(service.audit_records())["attempts"][0]
        attempt = audit["execution"]["attempts"][0]
        self.assertEqual(attempt["raw_output"], UNKNOWN)
        self.assertEqual(attempt["usage"], {"input_tokens":10,"output_tokens":20})
        self.assertEqual(json.loads(service.public_history())["answers"], [])


class SDKFailureTests(unittest.TestCase):
    def test_sdk_error_categories_never_expose_error_text(self) -> None:
        for code, expected in ((401,"authentication-failed"), (403,"authentication-failed"),
                               (429,"rate-limit"), (503,"provider-unavailable"), (400,"provider-error")):
            error = RuntimeError("secret URL key=forbidden-key")
            error.status_code = code  # type: ignore[attr-defined]
            for provider, transport, target, call in (
                ("openai", OpenAITransport(), "openai.OpenAI", "responses.create"),
                ("gemini", GeminiTransport(), "google.genai.Client", "models.generate_content"),
            ):
                fake = MagicMock()
                fake.__enter__.return_value = fake
                parent, method = call.split(".")
                getattr(getattr(fake,parent), method).side_effect = error
                config = GeneratorConfig.model_validate({"provider":provider,"model":price(provider).model})
                with self.subTest(provider=provider, code=code), patch(target,return_value=fake), self.assertRaisesRegex(GenerationFailure,expected) as caught:
                    transport.request(config, "forbidden-key", "safe input")
                self.assertNotIn("forbidden-key", str(caught.exception))

    def test_refusal_and_incomplete_openai_reply_retain_billed_usage(self) -> None:
        fake = MagicMock()
        fake.__enter__.return_value = fake
        response = fake.responses.create.return_value
        response.output_text, response.model = "", "gpt-6.1-terra"
        response.usage.input_tokens, response.usage.output_tokens = 15, 6
        config = GeneratorConfig(provider="openai",model="gpt-6.1-terra")
        for status, parts, expected in (("completed",[MagicMock(type="refusal")],"refused"),
                                        ("incomplete",[],"incomplete-output")):
            response.status, response.output = status, [MagicMock(content=parts)]
            with patch("openai.OpenAI",return_value=fake):
                reply = OpenAITransport().request(config,"fake-key","allowed input")
            self.assertEqual(reply.failure,expected)
            self.assertEqual((reply.input_tokens,reply.output_tokens), (15,6))
