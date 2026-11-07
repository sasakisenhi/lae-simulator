"""Immutable collaboration evidence and resource accounting value types.

These helpers own no execution loop, clock, I/O or independent event history.
Canonical local reducers remain responsible for accepting their transitions.
"""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from typing import TYPE_CHECKING

from lae_simulator.simulation.model import ScheduledEvent

if TYPE_CHECKING:
    from lae_simulator.world.collaboration import ReplyRule
from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseArtifact:
    id: str
    request_id: str
    generation: int
    base_version: str
    evidence_ids: tuple[str, ...]
    acquisition: str
    producer_revision: str
    text: str
    digest: str


def response_digest(record: ResponseArtifact) -> str:
    value = [
        record.id,
        record.request_id,
        record.generation,
        record.base_version,
        record.evidence_ids,
        record.acquisition,
        record.producer_revision,
        record.text,
    ]
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_response(
    record: ResponseArtifact,
    request_id: str,
    generation: int,
    base_version: str,
    permitted_evidence: set[str],
) -> None:
    if (
        not record.id
        or record.request_id != request_id
        or type(record.generation) is not int
        or record.generation != generation
        or record.base_version != base_version
        or not set(record.evidence_ids).issubset(permitted_evidence)
        or record.acquisition not in {"fixed", "prepared-generated"}
        or not record.producer_revision
        or not record.text
        or response_digest(record) != record.digest
    ):
        raise ValueError(
            "response content, provenance, version, generation or evidence mismatch"
        )


@dataclass(frozen=True)
class WorkInterval:
    resource_id: str
    task_id: str
    generation: int
    start_tick: int
    end_tick: int
    kind: str


def account_time(
    intervals: tuple[WorkInterval, ...], resource_id: str
) -> tuple[int, int, int]:
    selected = tuple(item for item in intervals if item.resource_id == resource_id)
    for item in selected:
        if (
            type(item.start_tick) is not int
            or type(item.end_tick) is not int
            or item.start_tick < 0
            or item.end_tick < item.start_tick
            or type(item.generation) is not int
            or item.generation < 1
            or item.kind not in {"active", "wait", "resume"}
        ):
            raise ValueError("invalid resource interval")
    ordered = sorted(
        (item for item in selected if item.end_tick > item.start_tick),
        key=lambda item: (item.start_tick, item.end_tick, item.task_id),
    )
    for prior, following in pairwise(ordered):
        if prior.end_tick > following.start_tick:
            raise ValueError("human resource intervals overlap")
    active = sum(
        item.end_tick - item.start_tick
        for item in selected
        if item.kind in {"active", "resume"}
    )
    waiting = sum(
        item.end_tick - item.start_tick for item in selected if item.kind == "wait"
    )
    elapsed = active + waiting
    return elapsed, active, waiting


@dataclass(frozen=True)
class RequestPayload:
    rule_id: str
    request_id: str
    generation: int
    base_version: str
    input_ids: tuple[str, ...]
    parent_request_id: str | None = None


@dataclass(frozen=True)
class ArrivalPayload:
    artifact: ResponseArtifact
    disposition: str


@dataclass(frozen=True)
class RequestAction:
    request_id: str
    generation: int


CollaborationPayload = RequestPayload | ArrivalPayload | RequestAction


@dataclass(frozen=True)
class RequestState:
    id: str
    generation: int
    rule_id: str
    base_version: str
    input_ids: tuple[str, ...]
    request_event_id: str
    requested_tick: int
    status: str
    response: ResponseArtifact | None = None
    response_event_id: str | None = None
    response_tick: int | None = None
    delivered_tick: int | None = None
    delivered_event_id: str | None = None
    observed_tick: int | None = None
    observed_event_id: str | None = None
    parent_request_id: str | None = None
    disposition: str | None = None
    acknowledged_tick: int | None = None
    acknowledged_event_id: str | None = None
    authorized: bool = False
    executing: bool = False
    result_event_id: str | None = None


@dataclass(frozen=True)
class HumanTask:
    candidate_id: str
    generation: int
    base_version: str
    start_tick: int
    due_tick: int
    remaining_ticks: int
    reservation_id: str
    status: str
    cause_event_id: str
    resumed: bool = False


@dataclass(frozen=True)
class CollaborationState:
    human_task: HumanTask | None = None
    paused_tasks: tuple[HumanTask, ...] = ()
    availability: tuple[tuple[str, bool], ...] = ()
    requests: tuple[RequestState, ...] = ()
    intervals: tuple[WorkInterval, ...] = ()
    waiting_for: tuple[str, int] | None = None
    waiting_since: int | None = None
    grants: tuple[tuple[str, str, int, str], ...] = ()
    reservation_obligations: tuple[ScheduledEvent, ...] = ()
    consumed_slot: ScheduledEvent | None = None
    consumed_event_id: str | None = None
    obligation_cause: str | None = None
    waiting_event_id: str | None = None


def payload_dict(payload: CollaborationPayload) -> dict[str, object]:
    from dataclasses import asdict

    if isinstance(payload, RequestPayload):
        return {"type": "request", **asdict(payload)}
    if isinstance(payload, ArrivalPayload):
        return {"type": "arrival", **asdict(payload)}
    return {"type": "action", **asdict(payload)}


def payload_from_dict(value: dict[str, object]) -> CollaborationPayload:
    from typing import Any, cast

    row = cast(dict[str, Any], value)
    kind = row["type"]
    if kind == "request" and set(row) == {
        "type",
        "rule_id",
        "request_id",
        "generation",
        "base_version",
        "input_ids",
        "parent_request_id",
    }:
        return RequestPayload(
            row["rule_id"],
            row["request_id"],
            row["generation"],
            row["base_version"],
            tuple(row["input_ids"]),
            row["parent_request_id"],
        )
    if kind == "arrival" and set(row) == {"type", "artifact", "disposition"}:
        artifact = dict(row["artifact"])
        artifact["evidence_ids"] = tuple(artifact["evidence_ids"])
        return ArrivalPayload(ResponseArtifact(**artifact), row["disposition"])
    if kind == "action" and set(row) == {"type", "request_id", "generation"}:
        return RequestAction(row["request_id"], row["generation"])
    raise ValueError("unknown or malformed collaboration payload")


def collaboration_dict(state: CollaborationState) -> dict[str, object]:
    from dataclasses import asdict

    return asdict(state)


def collaboration_from_dict(value: dict[str, object]) -> CollaborationState:
    from typing import Any, cast

    from lae_simulator.simulation.scheduler import reservation_from_dict

    row = cast(dict[str, Any], value)
    requests = []
    for entry in row["requests"]:
        item = dict(entry)
        item["input_ids"] = tuple(item["input_ids"])
        if item["response"] is not None:
            artifact = dict(item["response"])
            artifact["evidence_ids"] = tuple(artifact["evidence_ids"])
            item["response"] = ResponseArtifact(**artifact)
        requests.append(RequestState(**item))
    return CollaborationState(
        human_task=None
        if row.get("human_task") is None
        else HumanTask(**row["human_task"]),
        paused_tasks=tuple(HumanTask(**entry) for entry in row.get("paused_tasks", [])),
        availability=tuple(tuple(entry) for entry in row.get("availability", [])),
        requests=tuple(requests),
        intervals=tuple(WorkInterval(**entry) for entry in row["intervals"]),
        waiting_for=None if row["waiting_for"] is None else tuple(row["waiting_for"]),
        waiting_since=row["waiting_since"],
        grants=tuple(tuple(entry) for entry in row["grants"]),
        reservation_obligations=tuple(
            reservation_from_dict(entry) for entry in row["reservation_obligations"]
        ),
        consumed_slot=None
        if row["consumed_slot"] is None
        else reservation_from_dict(row["consumed_slot"]),
        consumed_event_id=row["consumed_event_id"],
        obligation_cause=row.get("obligation_cause"),
        waiting_event_id=row.get("waiting_event_id"),
    )


def bind_response(
    request: RequestState, rule: ReplyRule, disposition: str
) -> ResponseArtifact:
    from dataclasses import replace

    text = rule.text
    evidence = rule.response_evidence_ids
    if disposition == "unavailable":
        text, evidence = "The declared collaborator is unavailable.", ()
    elif disposition == "approval-required":
        text, evidence = (
            "Additional editing scope requires approval from the declared approver.",
            (),
        )
    elif disposition == "question":
        text, evidence = "More permitted request input is required.", ()
    record = ResponseArtifact(
        f"REPLY-{request.id}-g{request.generation}",
        request.id,
        request.generation,
        request.base_version,
        evidence,
        rule.acquisition,
        rule.producer_revision,
        text,
        "",
    )
    return replace(record, digest=response_digest(record))


def response_disposition(
    request: RequestState, rule: ReplyRule, available: bool
) -> str:
    if not available or request.status == "unavailable":
        return "unavailable"
    if not set(rule.required_input_ids).issubset(request.input_ids):
        return "question"
    if (
        rule.operation == "ai.delegate"
        and rule.required_scope is not None
        and not request.authorized
    ):
        return "approval-required"
    return rule.disposition
