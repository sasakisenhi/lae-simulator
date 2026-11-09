from __future__ import annotations

import unittest
from unittest.mock import patch

from lae_simulator.adapters.interview_config import GeneratorConfig
from lae_simulator.adapters.interview_remote import OpenAITransport, ProviderReply
from scripts.g8_openai_acceptance import PacedOpenAITransport


class OpenAIPacingTests(unittest.TestCase):
    def test_pacing_preserves_real_sdk_arguments_and_never_retries(self) -> None:
        now = [100.0]
        sleeps: list[float] = []
        records: list[dict[str, object]] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        transport = PacedOpenAITransport(clock=lambda: now[0], sleeper=sleep, record=records.append)
        config = GeneratorConfig(provider="openai", model="gpt-6.1-terra")
        reply = ProviderReply("{}", 1, 1, config.model)
        with patch.object(OpenAITransport, "request", side_effect=[reply, TimeoutError()]) as sdk:
            self.assertIs(transport.request(config, "fake-key", "unchanged input"), reply)
            now[0] += 5
            with self.assertRaises(TimeoutError):
                transport.request(config, "fake-key", "unchanged input")
        self.assertEqual(sdk.call_count, 2)
        sdk.assert_called_with(config, "fake-key", "unchanged input")
        self.assertEqual(sleeps, [30.0, 30.0])
        self.assertEqual(records[1]["monotonic_start"], 165.0)
        self.assertEqual(transport.mode, "sdk")

    def test_already_elapsed_interval_has_no_additional_sleep(self) -> None:
        clock = [0.0]
        transport = PacedOpenAITransport(clock=lambda: clock[0])
        config = GeneratorConfig(provider="openai", model="gpt-6.1-terra")
        with patch.object(OpenAITransport, "request", return_value=ProviderReply("{}", 1, 1, config.model)), patch.object(transport, "sleeper") as sleep:
            transport.request(config, "fake-key", "input")
            clock[0] = 70
            transport.request(config, "fake-key", "input")
        sleep.assert_not_called()
