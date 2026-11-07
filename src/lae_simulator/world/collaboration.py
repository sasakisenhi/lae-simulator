"""Fixed exercise-owned collaboration profiles, without runtime I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AvailabilityChange:
    tick: int
    available: bool


@dataclass(frozen=True)
class Collaborator:
    id: str
    kind: str
    knowledge_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    approval_scopes: tuple[str, ...]
    available: bool
    capacity: int
    input_ids: tuple[str, ...]
    availability_changes: tuple[AvailabilityChange, ...] = ()


@dataclass(frozen=True)
class ReplyRule:
    id: str
    collaborator_id: str
    operation: str
    topic: str
    required_input_ids: tuple[str, ...]
    response_evidence_ids: tuple[str, ...]
    response_claim_ids: tuple[str, ...]
    disposition: str
    delay_ticks: int
    expiry_ticks: int
    delivery_ticks: int
    text: str
    producer_revision: str
    acquisition: str
    overlay_patch_id: str | None
    required_scope: str | None
    approver_id: str | None


@dataclass(frozen=True)
class CollaborationDefinition:
    collaborators: tuple[Collaborator, ...]
    rules: tuple[ReplyRule, ...]


def _strings(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError("expected unique nonempty string identifiers")
    return tuple(value)


def load_collaboration(
    value: Any, claim_ids: set[str], evidence_ids: set[str], patch_ids: set[str]
) -> CollaborationDefinition:
    if not isinstance(value, dict) or set(value) != {"collaborators", "rules"}:
        raise ValueError("collaboration requires collaborators and rules")
    if not isinstance(value["collaborators"], list) or not isinstance(
        value["rules"], list
    ):
        raise TypeError("collaborators and rules must be arrays")
    collaborators = []
    seen: set[str] = set()
    for row in value["collaborators"]:
        if not isinstance(row, dict) or set(row) - {"availability_changes"} != {
            "id",
            "kind",
            "knowledge_ids",
            "evidence_ids",
            "approval_scopes",
            "available",
            "capacity",
            "input_ids",
        }:
            raise ValueError("invalid collaborator fields")
        if (
            not isinstance(row["id"], str)
            or not row["id"]
            or row["id"] in seen
            or row["kind"] not in {"peer", "ai"}
            or type(row["available"]) is not bool
            or type(row["capacity"]) is not int
            or row["capacity"] < 1
        ):
            raise ValueError(
                "invalid collaborator identity, kind, availability or capacity"
            )
        seen.add(row["id"])
        known = _strings(row["knowledge_ids"])
        evidence = _strings(row["evidence_ids"])
        inputs = _strings(row["input_ids"])
        if (
            not set(known).issubset(claim_ids)
            or not set(evidence).issubset(evidence_ids)
            or not set(inputs).issubset(claim_ids | evidence_ids)
        ):
            raise ValueError(
                "collaborator knowledge or evidence refers outside permitted input"
            )
        changes = row.get("availability_changes", [])
        if (
            not isinstance(changes, list)
            or any(
                not isinstance(change, dict)
                or set(change) != {"tick", "available"}
                or type(change["tick"]) is not int
                or change["tick"] < 0
                or type(change["available"]) is not bool
                for change in changes
            )
            or [change["tick"] for change in changes]
            != sorted({change["tick"] for change in changes})
        ):
            raise ValueError(
                "availability changes require strictly increasing integer ticks and explicit flags"
            )
        collaborators.append(
            Collaborator(
                row["id"],
                row["kind"],
                known,
                evidence,
                _strings(row["approval_scopes"]),
                row["available"],
                row["capacity"],
                inputs,
                tuple(AvailabilityChange(**change) for change in changes),
            )
        )
    profiles = {item.id: item for item in collaborators}
    rules = []
    fields = {
        "id",
        "collaborator_id",
        "operation",
        "topic",
        "required_input_ids",
        "response_evidence_ids",
        "response_claim_ids",
        "disposition",
        "delay_ticks",
        "expiry_ticks",
        "delivery_ticks",
        "text",
        "producer_revision",
        "acquisition",
        "overlay_patch_id",
        "required_scope",
        "approver_id",
    }
    for row in value["rules"]:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("invalid fixed response rule fields")
        if any(
            not isinstance(row[name], str) or not row[name]
            for name in (
                "id",
                "collaborator_id",
                "operation",
                "topic",
                "disposition",
                "text",
                "producer_revision",
                "acquisition",
            )
        ):
            raise ValueError(
                "fixed response rule requires explicit identifiers and provenance"
            )
        if row["id"] in seen or row["collaborator_id"] not in profiles:
            raise ValueError("duplicate rule or unknown collaborator")
        seen.add(row["id"])
        if (
            row["operation"] not in {"question.send", "ai.delegate", "approval.request"}
            or row["disposition"]
            not in {
                "answer",
                "approve",
                "deny",
                "unavailable",
                "no-response",
                "question",
            }
            or row["acquisition"] not in {"fixed", "prepared-generated"}
        ):
            raise ValueError("unsupported response operation, outcome or acquisition")
        for name in ("delay_ticks", "expiry_ticks", "delivery_ticks"):
            if type(row[name]) is not int or row[name] < 0:
                raise ValueError("response timing must be nonnegative integer ticks")
        required = _strings(row["required_input_ids"])
        evidence = _strings(row["response_evidence_ids"])
        claims = _strings(row["response_claim_ids"])
        peer = profiles[row["collaborator_id"]]
        if (
            not set(required).issubset(evidence_ids | claim_ids)
            or not set(evidence).issubset(set(peer.evidence_ids))
            or not set(claims).issubset(set(peer.knowledge_ids))
        ):
            raise ValueError("response exceeds declared knowledge or evidence scope")
        if (
            row["overlay_patch_id"] is not None
            and row["overlay_patch_id"] not in patch_ids
        ):
            raise ValueError("response overlay is not a fixed patch")
        if row["required_scope"] is not None and (
            not isinstance(row["required_scope"], str) or not row["required_scope"]
        ):
            raise ValueError("approval scope must be explicit")
        if row["disposition"] == "approve" and (
            row["operation"] != "approval.request"
            or row["required_scope"] not in peer.approval_scopes
        ):
            raise ValueError("approval rule cannot grant an undeclared scope")
        if row["approver_id"] is not None and row["approver_id"] not in profiles:
            raise ValueError("unknown approval contact")
        rules.append(
            ReplyRule(
                row["id"],
                peer.id,
                row["operation"],
                row["topic"],
                required,
                evidence,
                claims,
                row["disposition"],
                row["delay_ticks"],
                row["expiry_ticks"],
                row["delivery_ticks"],
                row["text"],
                row["producer_revision"],
                row["acquisition"],
                row["overlay_patch_id"],
                row["required_scope"],
                row["approver_id"],
            )
        )
    return CollaborationDefinition(tuple(collaborators), tuple(rules))


def collaboration_scopes(
    data: dict[str, Any], source_classes: dict[str, str]
) -> tuple[set[str], set[str]]:
    claims = {
        row["id"]
        for row in data.get("world_claims", [])
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and row.get("classification") != "administrative"
    }
    evidence = {
        row["id"]
        for row in data.get("documents", [])
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and row.get("classification") != "administrative"
        and source_classes.get(str(row.get("source_id"))) != "audit_only_comment"
    }
    evidence.update(
        row["id"]
        for row in data.get("references", [])
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and source_classes.get(str(row.get("source_id"))) != "audit_only_comment"
    )
    return claims, evidence
