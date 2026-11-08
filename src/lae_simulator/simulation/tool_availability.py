"""Fixed World search condition, separate from actor-observed availability."""

from __future__ import annotations

import json

from lae_simulator.simulation.local_model import ScenarioExecution

SEARCH_UNAVAILABLE = "tool-unavailable:code.search"


def search_available(execution: ScenarioExecution) -> bool:
    """Read the validated immutable definition, never an actor observation."""
    value = json.loads(execution.canonical_bytes).get(
        "tool_availability", {"code.search": True}
    )
    return value["code.search"] is True
