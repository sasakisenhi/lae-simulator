"""Closed values in world-definition schema version 1.0."""

from __future__ import annotations

from lae_simulator.world.model import Classification, Role

SCHEMA_VERSION = "1.0"

SUPPORTED_OPERATIONS = frozenset({"document.read", "issue.read"})
SUPPORTED_ACTIONS = frozenset({"read"})

ROLE_CEILINGS: dict[Role, frozenset[Classification]] = {
    Role.ADMINISTRATOR: frozenset(Classification),
    Role.ACTOR_POLICY: frozenset(
        {Classification.ACTOR_PRIVATE, Classification.PUBLIC_EVIDENCE}
    ),
    Role.INTERVIEW_GENERATOR: frozenset(
        {Classification.ACTOR_PRIVATE, Classification.PUBLIC_EVIDENCE}
    ),
    Role.INVESTIGATOR: frozenset({Classification.PUBLIC_EVIDENCE}),
}

