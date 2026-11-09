"""Finite budget shared by all providers in one interview evaluation run.

Reservations are recorded before transmission. Unknown usage retains its full
reservation. This bounds estimated exposure, not an external provider's invoice.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from lae_simulator.adapters.interview_config import Budget, Price, amount
from lae_simulator.simulation.interview_contract import GenerationFailure


@dataclass
class BudgetLedger:
    limits: Budget
    requests: int = 0
    tokens: int = 0
    estimated_cost: Decimal = Decimal(0)
    stopped: bool = False
    checkpoint: Callable[[dict[str, object]], None] | None = None

    def reserve(self, input_tokens: int, output_tokens: int, price: Price) -> dict[str, object]:
        tokens = input_tokens + output_tokens
        cost = price.cost(input_tokens, output_tokens)
        if (self.stopped or self.requests + 1 > self.limits.max_requests
                or tokens > self.limits.max_request_tokens
                or self.tokens + tokens > self.limits.max_total_tokens
                or self.estimated_cost + cost > amount(self.limits.max_estimated_cost_usd)):
            self.stopped = True
            raise GenerationFailure("budget-exceeded", {"ledger": self.snapshot()})
        self.requests += 1
        self.tokens += tokens
        self.estimated_cost += cost
        if self.checkpoint is not None:
            self.checkpoint(self.snapshot())
        return {"estimated_input_tokens": input_tokens, "reserved_output_tokens": output_tokens,
                "estimated_cost_usd": str(cost),
                "method": "UTF-8-byte-count plus schema/framing allowance; not a provider token count"}

    def settle(self, reserved_input: int, reserved_output: int, price: Price,
               actual_input: int | None, actual_output: int | None) -> Decimal | None:
        if actual_input is None or actual_output is None:
            # Cannot reliably account for unreported billed work: stop this run.
            self.stopped = True
            if self.checkpoint is not None:
                self.checkpoint(self.snapshot())
            return None
        self.tokens += actual_input + actual_output - reserved_input - reserved_output
        cost = price.cost(actual_input, actual_output)
        self.estimated_cost += cost - price.cost(reserved_input, reserved_output)
        if (actual_input + actual_output > self.limits.max_request_tokens
                or self.tokens > self.limits.max_total_tokens
                or self.estimated_cost > amount(self.limits.max_estimated_cost_usd)):
            self.stopped = True
        if self.checkpoint is not None:
            self.checkpoint(self.snapshot())
        return cost

    def snapshot(self) -> dict[str, object]:
        return {"requests": self.requests, "accounted_tokens": self.tokens,
                "estimated_cost_usd": str(self.estimated_cost), "stopped": self.stopped,
                "limits": self.limits.model_dump(mode="json"),
                "boundary": "evaluation-run; reservations include failed requests with unknown usage; provider billing is not guaranteed"}
