"""Stable keyed draws for audited synthetic execution assumptions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class RandomKey:
    purpose: str
    actor_id: str
    task_id: str
    semantic_event_key: str
    occurrence: int


def draw_u64(seed: int, key: RandomKey) -> int:
    """SHA-256 v1 draw; the seed and key together identify the draw."""
    if type(seed) is not int or type(key.occurrence) is not int or key.occurrence < 0:
        raise ValueError("seed and nonnegative occurrence must be integers")
    if any(not isinstance(value, str) or not value for value in (
        key.purpose, key.actor_id, key.task_id, key.semantic_event_key
    )):
        raise ValueError("random draw identifiers must be nonempty strings")
    payload = json.dumps(
        ["lae-keyed-sha256-v1", seed, key.purpose, key.actor_id, key.task_id,
         key.semantic_event_key, key.occurrence],
        ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
