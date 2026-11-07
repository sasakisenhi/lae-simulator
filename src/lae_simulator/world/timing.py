"""Typed fixed timing assumptions; no implicit calibration or live sampling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DurationModel:
    id: str
    ticks: int
    provenance_class: str
    source: str
    uncertainty: str
    scope: tuple[str, ...]
    jitter_ticks: int = 0


@dataclass(frozen=True)
class ReservationControl:
    id: str
    tick: int
    priority: int
    action: str
    target_candidate_id: str
    reason: str
    generation: int


@dataclass(frozen=True)
class TimingDefinition:
    seed: int
    deadline_tick: int
    max_same_tick_events: int
    models: tuple[DurationModel, ...]
    controls: tuple[ReservationControl, ...] = ()


def load_timing(value: Any, required_ids: set[str]) -> TimingDefinition:
    if not isinstance(value, dict) or not {
        "seed", "deadline_tick", "max_same_tick_events", "models"
    }.issubset(value) or set(value) - {
        "seed", "deadline_tick", "max_same_tick_events", "models", "controls"
    }:
        raise ValueError("timing requires seed, deadline, event bound, and models")
    for name in ("seed", "deadline_tick", "max_same_tick_events"):
        if type(value[name]) is not int:
            raise ValueError(f"{name} must be an integer")
    if value["deadline_tick"] < 0 or value["max_same_tick_events"] < 1:
        raise ValueError("invalid timing window or event bound")
    if not isinstance(value["models"], list):
        raise TypeError("timing models must be a list")
    models = []
    identifiers: set[str] = set()
    for item in value["models"]:
        if not isinstance(item, dict) or not {
            "id", "ticks", "provenance_class", "source", "uncertainty", "scope"
        }.issubset(item) or set(item) - {
            "id", "ticks", "provenance_class", "source", "uncertainty", "scope", "jitter_ticks"
        }:
            raise ValueError("duration model fields are incomplete or unsupported")
        if any(not isinstance(item[name], str) or not item[name].strip()
               for name in ("id", "provenance_class", "source", "uncertainty")):
            raise ValueError("duration model needs identifiers and provenance")
        if item["id"] in identifiers:
            raise ValueError("duration model identifiers must be unique")
        identifiers.add(item["id"])
        if type(item["ticks"]) is not int or item["ticks"] < 0:
            raise ValueError("duration must be a nonnegative integer tick count")
        jitter = item.get("jitter_ticks", 0)
        if type(jitter) is not int or jitter < 0:
            raise ValueError("jitter must be a nonnegative integer tick count")
        if item["provenance_class"] != "synthetic-assumption":
            raise ValueError("this timing profile accepts explicit synthetic assumptions only; measured or documented durations need a separate evidence contract")
        if (not isinstance(item["scope"], list) or not item["scope"]
                or any(not isinstance(scope, str) or not scope for scope in item["scope"])):
            raise ValueError("duration model must declare operation scope")
        models.append(DurationModel(item["id"], item["ticks"], item["provenance_class"],
                                    item["source"], item["uncertainty"], tuple(item["scope"]), jitter))
    if not required_ids.issubset(identifiers):
        raise ValueError("candidate refers to an undefined duration model")
    controls = []
    raw_controls = value.get("controls", [])
    if not isinstance(raw_controls, list):
        raise TypeError("controls must be a list")
    for row in raw_controls:
        if not isinstance(row, dict) or set(row) != {
            "id", "tick", "priority", "action", "target_candidate_id", "reason", "generation"
        }:
            raise ValueError("reservation control has invalid fields")
        if any(not isinstance(row[key], str) or not row[key].strip()
               for key in ("id", "target_candidate_id", "reason")):
            raise ValueError("control requires explicit identity, target, and reason")
        if row["id"] in identifiers:
            raise ValueError("duplicate control identifier")
        identifiers.add(row["id"])
        if (type(row["tick"]) is not int or not 0 <= row["tick"] <= value["deadline_tick"]
                or type(row["priority"]) is not int or row["priority"] not in {20, 40}
                or row["action"] not in {"cancelled", "invalidated"}
                or type(row["generation"]) is not int or row["generation"] != 1):
            raise ValueError("invalid control time, source class, action, or generation")
        controls.append(ReservationControl(**row))
    return TimingDefinition(value["seed"], value["deadline_tick"],
                            value["max_same_tick_events"], tuple(models), tuple(controls))
