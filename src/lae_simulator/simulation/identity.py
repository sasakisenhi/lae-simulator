"""Stable engine and run identity independent of wall-clock metadata."""

from __future__ import annotations

import hashlib

from lae_simulator.world.model import WorldDefinition

ENGINE_VERSION = "walking-skeleton-1.0"


def compute_run_id(world: WorldDefinition) -> str:
    material = (
        f"{ENGINE_VERSION}\n{world.content_id}\n{world.seed}\n{world.schema_version}"
    ).encode()
    return "run-" + hashlib.sha256(material).hexdigest()
