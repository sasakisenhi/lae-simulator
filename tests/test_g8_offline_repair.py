from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_interview import package, response
from test_interview_remote import UNKNOWN, RemoteTestSupport

from lae_simulator.adapters.interview_config import GeneratorConfig
from lae_simulator.adapters.interview_diagnostics import error_details, model_identifier
from lae_simulator.adapters.interview_remote import GeminiTransport, OpenAITransport
from lae_simulator.simulation.interview import FixedResponseGenerator, InterviewService
from lae_simulator.simulation.interview_contract import (
    GeneratedAnswer,
    GenerationFailure,
    Statement,
)


class SDKError(Exception):
    status_code: int
    body: dict[str, object]
    response: SimpleNamespace


class DiagnosticsTests(RemoteTestSupport):
    def error(self, code: str, status: int = 429) -> SDKError:
        error = SDKError("Authorization: Bearer secret-key https://secret.invalid/key")
        error.status_code = status
        error.body = {"error": {"code": code, "type": "insufficient_quota" if "quota" in code else "rate_limit_error",
                                "message": "secret-key"}}
        error.response = SimpleNamespace(headers={"retry-after": "2", "x-request-id": "req_1234567890",
                                                 "authorization": "Bearer secret-key"})
        return error

    @patch.dict(os.environ, {"LAE_TEST_KEY": "secret-key"})
    def test_billing_quota_and_unknown_429_never_retry(self) -> None:
        for code in ("insufficient_quota", "credit_balance_exhausted", "project_spend_limit_exceeded",
                     "organization_spend_limit_exceeded", "organization_usage_limit_exceeded", "unknown"):
            generator, transport = self.generator([self.error(code)], max_attempts=3, retry_on=("rate-limit",))
            with self.assertRaises(GenerationFailure) as caught:
                self.generate(generator)
            self.assertEqual(len(transport.calls), 1)
            text = json.dumps(caught.exception.execution)
            for secret in ("secret-key", "Authorization", "secret.invalid", "Bearer"):
                self.assertNotIn(secret, text)
            detail = caught.exception.execution["attempts"][0]["diagnostics"]  # type: ignore[index]
            self.assertEqual(detail["http_status"], 429)
            self.assertFalse(detail["retryable"])

    @patch.dict(os.environ, {"LAE_TEST_KEY": "secret-key"})
    def test_transient_retry_bounded_and_honors_delay(self) -> None:
        generator, transport = self.generator([self.error("rate_limit_exceeded"), self.error("rate_limit_exceeded")],
                                             max_attempts=2, retry_on=("rate-limit",))
        with patch("time.sleep") as sleep, self.assertRaises(GenerationFailure) as caught:
            self.generate(generator)
        self.assertEqual(len(transport.calls), 2)
        sleep.assert_called_once_with(2.0)
        self.assertIn("req_1234567890", json.dumps(caught.exception.execution))

    def test_untrusted_diagnostic_fields_are_not_logged(self) -> None:
        error = self.error("secret-key")
        error.response.headers.update({"retry-after": "secret-key", "x-request-id": "req_secret-key"})
        detail = error_details(error, provider="openai", model="fixture", secret="secret-key")
        self.assertIsNone(detail["error_code"])
        self.assertIsNone(detail["request_id"])
        self.assertIsNone(detail["retry_after_seconds"])
        self.assertFalse(detail["retryable"])
        self.assertNotIn("secret-key", json.dumps(detail))
        self.assertIsNone(model_identifier("Authorization: Bearer secret-key", "secret-key"))
        self.assertIsNone(model_identifier("secret-key", "secret-key"))
        self.assertEqual(model_identifier("gpt-6.1-terra", "secret-key"), "gpt-6.1-terra")

    def test_actual_google_exception_uses_details_and_generic_quota_is_unknown(self) -> None:
        from google.genai.errors import ClientError
        error = ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "secret-key"}})
        detail = error_details(error, provider="gemini", model="gemini-2.5-flash", secret="secret-key")
        self.assertEqual(detail["error_type"], "RESOURCE_EXHAUSTED")
        self.assertEqual(detail["category"], "rate-limit-unknown")
        self.assertFalse(detail["retryable"])
        self.assertNotIn("secret-key", json.dumps(detail))

    @patch.dict(os.environ, {"LAE_TEST_KEY": "secret-key"})
    def test_long_retry_after_defers_instead_of_retrying_early(self) -> None:
        error = self.error("rate_limit_exceeded")
        error.response.headers["retry-after"] = "60"
        generator, transport = self.generator([error], max_attempts=3, retry_on=("rate-limit",))
        with patch("time.sleep") as sleep, self.assertRaises(GenerationFailure):
            self.generate(generator)
        sleep.assert_not_called()
        self.assertEqual(len(transport.calls), 1)

    @patch.dict(os.environ, {"LAE_TEST_KEY": "secret-key"})
    def test_billing_error_stops_subsequent_questions_and_untrusted_failure_is_sanitized(self) -> None:
        generator, transport = self.generator([self.error("credit_balance_exhausted")])
        for _ in range(2):
            with self.assertRaisesRegex(GenerationFailure, "quota-or-billing"):
                self.generate(generator)
        self.assertEqual(len(transport.calls), 1)
        generator, _ = self.generator([GenerationFailure("secret-key", {"diagnostics": {"authorization": "secret-key"}})])
        with self.assertRaises(GenerationFailure) as caught:
            self.generate(generator)
        self.assertNotIn("secret-key", str(caught.exception) + json.dumps(caught.exception.execution))

    def test_sdk_failure_details_survive_both_transports(self) -> None:
        for provider, transport, target in (("openai", OpenAITransport(), "openai.OpenAI"),
                                            ("gemini", GeminiTransport(), "google.genai.Client")):
            client = MagicMock()
            client.__enter__.return_value = client
            client.responses.create.side_effect = self.error("credit_balance_exhausted")
            client.models.generate_content.side_effect = self.error("credit_balance_exhausted")
            config = GeneratorConfig.model_validate({"provider": provider, "model": "fixture"})
            with patch(target, return_value=client), self.assertRaises(GenerationFailure) as caught:
                transport.request(config, "secret-key", "safe")
            detail = caught.exception.execution["diagnostics"]
            self.assertEqual(detail["provider"], provider)  # type: ignore[index]
            self.assertEqual(detail["error_code"], "credit_balance_exhausted")  # type: ignore[index]

    def test_gemini_token_truncation_records_finish_and_thinking(self) -> None:
        client = MagicMock()
        client.__enter__.return_value = client
        reply = client.models.generate_content.return_value
        reply.text, reply.model_version = '{"statements":[', "gemini-2.5-flash"
        reply.candidates = [SimpleNamespace(finish_reason="MAX_TOKENS")]
        reply.usage_metadata = SimpleNamespace(prompt_token_count=10, total_token_count=1034,
                                               thoughts_token_count=100, candidates_token_count=924)
        with patch("google.genai.Client", return_value=client):
            result = GeminiTransport().request(GeneratorConfig(provider="gemini", model="gemini-2.5-flash"), "key", "safe")
        self.assertEqual(result.failure, "incomplete-output")
        self.assertEqual(result.diagnostics["finish_reason"], "MAX_TOKENS")
        self.assertEqual(result.diagnostics["reasoning_tokens"], 100)

    @patch.dict(os.environ, {"LAE_TEST_KEY": "secret-key"})
    def test_truncated_valid_json_is_not_accepted_and_limit_is_unchanged(self) -> None:
        from lae_simulator.adapters.interview_remote import ProviderReply
        generator, _ = self.generator([ProviderReply(UNKNOWN, 10, 20, "gpt-6.1-terra", "incomplete-output",
                                                     {"finish_reason": "max_output_tokens", "reasoning_tokens": 3})])
        with self.assertRaises(GenerationFailure) as caught:
            self.generate(generator)
        completion = caught.exception.execution["attempts"][0]["completion"]  # type: ignore[index]
        self.assertEqual(completion["max_output_tokens"], 1024)
        self.assertEqual(completion["reasoning_tokens"], 3)
        self.assertEqual(completion["finish_reason"], "max_output_tokens")


class MeaningTests(unittest.TestCase):
    def test_unknown_with_forged_episode_stays_withheld(self) -> None:
        answer = GeneratedAnswer((Statement("わかりません。", "unknown", episode="invented"),), "fixed", "1", "fixture")
        service = InterviewService(package(), FixedResponseGenerator((answer,)), actor_id="A")
        result = service.ask("Q", "?")
        self.assertEqual(result.audit["decision"], "NEEDS_REVIEW")
        self.assertEqual(result.audit["stages"]["episode_binding"], "NEEDS_REVIEW")  # type: ignore[index]
        self.assertIsNone(result.answer)

    def test_japanese_translation_is_review_not_false_rejection(self) -> None:
        service = InterviewService(package(), FixedResponseGenerator((
            response("src/a.pyを開きました。", "ファイルを開く"),
        )), actor_id="A")
        with patch("socket.socket.connect", side_effect=AssertionError("offline only")):
            result = service.ask("Q", "昨日本番へ投入しましたね？")
        self.assertEqual(result.audit["decision"], "NEEDS_REVIEW")
        checks = result.audit["checks"][0]  # type: ignore[index]
        self.assertEqual(checks["schema"], "PASS")
        self.assertEqual(checks["support"], "PASS")
        self.assertEqual(checks["semantics"], "NEEDS_REVIEW")
        self.assertIsNone(result.answer)
        self.assertEqual(json.loads(service.public_history())["answers"], [])

    def test_missing_support_and_promoted_misbelief_are_clear_rejections(self) -> None:
        for answer in (response("昨日デプロイしました。", "昨日", support=()),
                       response("これは事実です。", "事実", support=("PER-2",))):
            service = InterviewService(package(), FixedResponseGenerator((answer,)), actor_id="A")
            result = service.ask("Q", "?")
            self.assertEqual(result.audit["decision"], "REJECT")
            self.assertIsNone(result.answer)
