"""Validated, updateable remote settings, prices, budgets, and exact input grants."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.interview_contract import PROMPT_VERSION


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def amount(value: str) -> Decimal:
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise ValueError("invalid nonnegative monetary amount")
        return result
    except InvalidOperation:
        raise ValueError("invalid monetary amount") from None


class GeneratorConfig(StrictConfig):
    provider: Literal["gemini", "openai", "fixed"]
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._-]+$")
    prompt_version: Literal["employee-interview-v2"] = PROMPT_VERSION
    api_key_env: str = Field(default="UNUSED", pattern=r"^[A-Za-z_][A-Za-z_0-9]*$")
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    max_output_tokens: int = Field(default=1024, ge=16, le=32768)
    timeout_seconds: float = Field(default=30.0, gt=0, le=120, allow_inf_nan=False)
    max_attempts: int = Field(default=1, ge=1, le=3)
    retry_on: tuple[Literal["timeout", "rate-limit", "provider-unavailable"], ...] = ()
    retry_delay_seconds: float = Field(default=0.0, ge=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def fixed_model(self) -> Self:
        if self.provider == "fixed" and self.model != "fixture":
            raise ValueError("fixed provider requires fixture model")
        return self


class Price(StrictConfig):
    provider: Literal["gemini", "openai"]
    model: str
    input_per_million_usd: str
    output_per_million_usd: str
    source: str
    checked_on: str
    valid_until: str

    @model_validator(mode="after")
    def check_price(self) -> Self:
        amount(self.input_per_million_usd)
        amount(self.output_per_million_usd)
        if date.fromisoformat(self.checked_on) > date.fromisoformat(self.valid_until):
            raise ValueError("invalid pricing interval")
        return self

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        # Cached input is conservatively priced as full input; no tool costs (no tools).
        return (amount(self.input_per_million_usd) * input_tokens
                + amount(self.output_per_million_usd) * output_tokens) / 1_000_000


class Budget(StrictConfig):
    max_requests: int = Field(ge=1, le=1000)
    max_request_tokens: int = Field(ge=16)
    max_total_tokens: int = Field(ge=16)
    max_estimated_cost_usd: str

    @model_validator(mode="after")
    def check_cost(self) -> Self:
        amount(self.max_estimated_cost_usd)
        return self


class EvaluationConfig(StrictConfig):
    mode: Literal["single", "comparative"]
    generators: tuple[GeneratorConfig, ...]
    prices: tuple[Price, ...] = ()
    budget: Budget

    @model_validator(mode="after")
    def check_mode(self) -> Self:
        if len(self.generators) != (1 if self.mode == "single" else 2):
            raise ValueError("mode and generator count differ")
        keys = [(row.provider, row.model) for row in self.generators]
        prices = [(row.provider, row.model) for row in self.prices]
        if len(keys) != len(set(keys)) or len(prices) != len(set(prices)):
            raise ValueError("duplicate model or price")
        if self.mode == "comparative" and {row.provider for row in self.generators} != {"gemini", "openai"}:
            raise ValueError("comparison requires one Gemini and one OpenAI")
        if any(key not in prices for key in keys if key[0] != "fixed"):
            raise ValueError("missing provider/model price")
        return self

    def digest(self) -> str:
        return content_digest(canonical_json_bytes(self.model_dump(mode="json")))


class Approval(StrictConfig):
    provider: Literal["gemini", "openai"]
    model: str
    evaluation_id: str
    package_digest: str
    questions_digest: str
    config_digest: str
    approved: bool = False
    approval_reference: str = ""

    def permits(self, *, provider: str, model: str, package_digest: str,
                questions_digest: str, config_digest: str, evaluation_id: str) -> bool:
        return (self.approved and bool(self.approval_reference.strip())
                and (self.provider, self.model, self.package_digest, self.questions_digest, self.config_digest, self.evaluation_id)
                == (provider, model, package_digest, questions_digest, config_digest, evaluation_id))
