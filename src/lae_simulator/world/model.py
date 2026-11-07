"""Immutable types produced by the world-definition loader."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProvenanceClass(StrEnum):
    SYNTHETIC_FIXTURE = "synthetic-fixture"
    EXERCISE_OSS = "exercise-oss"
    COMPANY_MATERIAL = "company-material"
    MEASURED = "measured"
    EXTERNAL_SPECIFICATION = "external-specification"
    SYNTHETIC_ASSUMPTION = "synthetic-assumption"


class Coverage(StrEnum):
    RECORDED = "recorded"
    UNRECORDED = "unrecorded"
    UNRESOLVED = "unresolved"


class ReferenceResolution(StrEnum):
    RESOLVED = "resolved"
    OUT_OF_SCOPE = "out-of-scope"
    UNKNOWN = "unknown"
    ABSENT = "absent"


class AccessOutcome(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class EpistemicState(StrEnum):
    UNKNOWN = "unknown"
    ACQUIRED = "acquired"
    TENTATIVE = "tentative"
    ACTOR_CONFIRMED = "actor-confirmed"


class Classification(StrEnum):
    ADMINISTRATIVE = "administrative"
    ACTOR_PRIVATE = "actor-private"
    PUBLIC_EVIDENCE = "public-evidence"


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    ACTOR_POLICY = "actor-policy"
    INTERVIEW_GENERATOR = "interview-generator"
    INVESTIGATOR = "investigator"


@dataclass(frozen=True)
class FixtureMetadata:
    kind: str
    synthetic: bool
    purpose: str


@dataclass(frozen=True)
class SourceRecord:
    id: str
    version: str
    provenance_class: ProvenanceClass
    origin: str
    license: str
    retrieval_status: str


@dataclass(frozen=True)
class Document:
    id: str
    source_id: str
    version: str
    media_type: str
    content_digest: str
    content: str
    classification: Classification


@dataclass(frozen=True)
class Issue:
    id: str
    source_id: str
    version: str
    title: str
    body_document_id: str


@dataclass(frozen=True)
class WorldFact:
    id: str
    statement: str
    evidence_ids: tuple[str, ...]
    provenance_class: ProvenanceClass
    classification: Classification


@dataclass(frozen=True)
class Reference:
    id: str
    source_id: str
    revision: str
    relation: str
    coverage: Coverage
    target_id: str | None


@dataclass(frozen=True)
class KnowledgeClaim:
    id: str
    statement: str
    epistemic_state: EpistemicState
    evidence_ids: tuple[str, ...]
    provenance_class: ProvenanceClass


@dataclass(frozen=True)
class Permission:
    resource_id: str
    actions: frozenset[str]


@dataclass(frozen=True)
class Actor:
    id: str
    initial_knowledge: tuple[KnowledgeClaim, ...]
    tool_ids: tuple[str, ...]
    permissions: tuple[Permission, ...]


@dataclass(frozen=True)
class Tool:
    id: str
    operations: frozenset[str]


@dataclass(frozen=True)
class ResourceAccess:
    actor_id: str
    resource_id: str
    outcome: AccessOutcome


@dataclass(frozen=True)
class Policy:
    id: str
    actor_id: str
    kind: str
    candidate_priority: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    id: str
    actor_id: str
    goal: str
    actor_visible_label: str
    operation_kind: str
    tool_id: str
    target_id: str
    target_refs: tuple[str, ...]
    duration_model_id: str
    evidence_refs: tuple[str, ...]
    required_information: tuple[str, ...]
    required_permissions: frozenset[str]
    required_version: str
    required_access: tuple[tuple[str, AccessOutcome], ...]
    knowledge_effects: tuple[KnowledgeClaim, ...]
    success_status: str
    failure_status: str
    failure_reason: str


@dataclass(frozen=True)
class TimeModel:
    id: str
    unit: str
    constant_value: int
    provenance_class: ProvenanceClass
    uncertainty: str
    scope: tuple[str, ...]


@dataclass(frozen=True)
class Timeline:
    start_tick: int
    deadline_tick: int
    observation_start_tick: int
    observation_end_tick: int
    time_unit: str


@dataclass(frozen=True)
class Disclosure:
    role_allowlists: tuple[tuple[Role, frozenset[Classification]], ...]


@dataclass(frozen=True)
class Retention:
    retained: bool
    retained_since_tick: int


@dataclass(frozen=True)
class WorldDefinition:
    schema_version: str
    exercise_id: str
    fixture: FixtureMetadata
    seed: int
    sources: tuple[SourceRecord, ...]
    documents: tuple[Document, ...]
    issue: Issue
    world_facts: tuple[WorldFact, ...]
    references: tuple[Reference, ...]
    actors: tuple[Actor, ...]
    tools: tuple[Tool, ...]
    access_outcomes: tuple[ResourceAccess, ...]
    policies: tuple[Policy, ...]
    candidates: tuple[Candidate, ...]
    time_models: tuple[TimeModel, ...]
    timeline: Timeline
    disclosure: Disclosure
    retention: Retention
    content_id: str
    canonical_bytes: bytes

    def reference_resolution(self, reference_id: str) -> ReferenceResolution:
        reference = next((item for item in self.references if item.id == reference_id), None)
        if reference is None:
            return ReferenceResolution.ABSENT
        if reference.coverage is Coverage.RECORDED:
            return ReferenceResolution.RESOLVED
        if reference.coverage is Coverage.UNRECORDED:
            return ReferenceResolution.OUT_OF_SCOPE
        return ReferenceResolution.UNKNOWN

    def access_outcome(self, actor_id: str, resource_id: str) -> AccessOutcome | None:
        access = next(
            (
                item
                for item in self.access_outcomes
                if item.actor_id == actor_id and item.resource_id == resource_id
            ),
            None,
        )
        return None if access is None else access.outcome

