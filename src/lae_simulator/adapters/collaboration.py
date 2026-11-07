"""Acquires exercise-frozen responses; never invokes a live model or network.

Prepared-generated content must already be frozen in the verified definition.
The reducer independently checks the returned record. Replay never uses adapters.
"""

from typing import Protocol

from lae_simulator.simulation.collaboration_model import (
    RequestState,
    ResponseArtifact,
    bind_response,
)
from lae_simulator.world.collaboration import ReplyRule


class ResponseAdapter(Protocol):
    def acquire(
        self, request: RequestState, rule: ReplyRule, disposition: str
    ) -> ResponseArtifact: ...


class FixedResponseAdapter:
    def acquire(
        self, request: RequestState, rule: ReplyRule, disposition: str
    ) -> ResponseArtifact:
        return bind_response(request, rule, disposition)
