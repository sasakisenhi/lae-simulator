"""Parse, validate, and freeze a world definition without executing it."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Never

from lae_simulator.world.contract import (
    ROLE_CEILINGS,
    SCHEMA_VERSION,
    SUPPORTED_ACTIONS,
    SUPPORTED_OPERATIONS,
)
from lae_simulator.world.errors import ValidationIssue, WorldValidationError
from lae_simulator.world.model import (
    AccessOutcome,
    Actor,
    Candidate,
    Classification,
    Coverage,
    Disclosure,
    Document,
    EpistemicState,
    FixtureMetadata,
    Issue,
    KnowledgeClaim,
    Permission,
    Policy,
    ProvenanceClass,
    Reference,
    ResourceAccess,
    Retention,
    Role,
    SourceRecord,
    Timeline,
    TimeModel,
    Tool,
    WorldDefinition,
    WorldFact,
)

JsonObject = dict[str, Any]


class _DuplicateKeyError(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _invalid_constant(value: str) -> Never:
    raise ValueError(f"non-finite JSON number is not supported: {value}")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def load_world(path: str | Path) -> WorldDefinition:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WorldValidationError(
            [ValidationIssue("$", "input-read-failed", str(error))]
        ) from error
    return load_world_text(text)


def load_world_text(text: str) -> WorldDefinition:
    try:
        data = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_invalid_constant,
        )
    except _DuplicateKeyError as error:
        raise WorldValidationError(
            [
                ValidationIssue(
                    "$", "duplicate-key", f"JSON object key is duplicated: {error}"
                )
            ]
        ) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise WorldValidationError(
            [ValidationIssue("$", "invalid-json", str(error))]
        ) from error
    return load_world_data(data)


def load_world_data(data: Any) -> WorldDefinition:
    validator = _Validator(data)
    validator.validate()
    if validator.issues:
        raise WorldValidationError(validator.issues)
    return validator.build()


class _Validator:
    _TOP_LEVEL_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
        "access_outcomes",
        "actors",
        "candidates",
        "checks",
        "disclosure",
        "documents",
        "exercise_id",
        "fixture",
        "issue",
        "patches",
        "policies",
        "references",
        "response_models",
        "retention",
        "schema_version",
        "seed",
        "source_manifest",
        "time_models",
        "timeline",
        "tools",
            "world_facts",
        }
    )

    def __init__(self, data: Any) -> None:
        self.data = data
        self.root: JsonObject = {}
        self.issues: list[ValidationIssue] = []
        self.ids: dict[str, str] = {}
        self.sources: dict[str, JsonObject] = {}
        self.documents: dict[str, JsonObject] = {}
        self.references: dict[str, JsonObject] = {}
        self.actors: dict[str, JsonObject] = {}
        self.tools: dict[str, JsonObject] = {}
        self.policies: dict[str, JsonObject] = {}
        self.candidates: dict[str, JsonObject] = {}
        self.time_models: dict[str, JsonObject] = {}
        self.world_facts: dict[str, JsonObject] = {}
        self.knowledge: dict[str, JsonObject] = {}
        self.expected_information: dict[str, JsonObject] = {}
        self.access: dict[tuple[str, str], JsonObject] = {}

    def issue(self, path: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(path, code, message))

    def obj(self, value: Any, path: str) -> JsonObject:
        if not isinstance(value, dict):
            self.issue(path, "invalid-type", "expected an object")
            return {}
        return value

    def array(self, value: Any, path: str) -> list[Any]:
        if not isinstance(value, list):
            self.issue(path, "invalid-type", "expected an array")
            return []
        return value

    def keys(
        self,
        value: JsonObject,
        path: str,
        required: set[str] | frozenset[str],
        optional: set[str] | frozenset[str] | None = None,
    ) -> None:
        optional = optional or set()
        for key in sorted(required - value.keys()):
            self.issue(f"{path}.{key}", "missing-field", "required field is missing")
        for key in sorted(value.keys() - required - optional):
            self.issue(f"{path}.{key}", "unsupported-field", "field is not supported")

    def text(self, value: Any, path: str, *, allow_empty: bool = False) -> str | None:
        if not isinstance(value, str):
            self.issue(path, "invalid-type", "expected a string")
            return None
        if not allow_empty and not value:
            self.issue(path, "invalid-value", "string must not be empty")
            return None
        return value

    def integer(self, value: Any, path: str, *, minimum: int = 0) -> int | None:
        if type(value) is not int:
            self.issue(path, "invalid-type", "expected an integer")
            return None
        if value < minimum:
            self.issue(path, "invalid-value", f"must be at least {minimum}")
            return None
        return value

    def boolean(self, value: Any, path: str) -> bool | None:
        if type(value) is not bool:
            self.issue(path, "invalid-type", "expected a boolean")
            return None
        return value

    def string_array(self, value: Any, path: str) -> list[str]:
        result: list[str] = []
        for index, item in enumerate(self.array(value, path)):
            parsed = self.text(item, f"{path}[{index}]")
            if parsed is not None:
                result.append(parsed)
        return result

    def enum(self, value: Any, enum_type: type[Any], path: str) -> Any | None:
        parsed = self.text(value, path)
        if parsed is None:
            return None
        try:
            return enum_type(parsed)
        except ValueError:
            allowed = ", ".join(item.value for item in enum_type)
            self.issue(path, "invalid-value", f"expected one of: {allowed}")
            return None

    def register(self, identifier: Any, path: str, target: dict[str, JsonObject], item: JsonObject) -> str | None:
        parsed = self.text(identifier, path)
        if parsed is None:
            return None
        if parsed in self.ids:
            self.issue(
                path,
                "duplicate-id",
                f"identifier {parsed!r} is already defined at {self.ids[parsed]}",
            )
            return None
        self.ids[parsed] = path
        target[parsed] = item
        return parsed

    def validate(self) -> None:
        self.root = self.obj(self.data, "$")
        self.keys(self.root, "$", self._TOP_LEVEL_KEYS)
        self._validate_header()
        self._validate_sources()
        self._validate_documents()
        self._validate_issue()
        self._validate_world_facts()
        self._validate_references()
        self._validate_tools()
        self._validate_actors()
        self._validate_access()
        self._validate_time_models()
        self._validate_candidates()
        self._validate_policies()
        self._validate_future_sections()
        self._validate_timeline()
        self._validate_disclosure()
        self._validate_retention()
        self._validate_evidence_links()

    def _validate_header(self) -> None:
        version = self.text(self.root.get("schema_version"), "$.schema_version")
        if version is not None and version != SCHEMA_VERSION:
            self.issue(
                "$.schema_version",
                "unsupported-version",
                f"schema version {version!r} is unsupported; expected {SCHEMA_VERSION!r}",
            )
        self.text(self.root.get("exercise_id"), "$.exercise_id")
        self.integer(self.root.get("seed"), "$.seed")

        fixture = self.obj(self.root.get("fixture"), "$.fixture")
        self.keys(fixture, "$.fixture", {"kind", "purpose", "synthetic"})
        kind = self.text(fixture.get("kind"), "$.fixture.kind")
        if kind is not None and kind != "conformance":
            self.issue("$.fixture.kind", "invalid-value", "expected 'conformance'")
        synthetic = self.boolean(fixture.get("synthetic"), "$.fixture.synthetic")
        if synthetic is False:
            self.issue(
                "$.fixture.synthetic",
                "invalid-value",
                "a conformance fixture must be explicitly synthetic",
            )
        self.text(fixture.get("purpose"), "$.fixture.purpose")

    def _validate_sources(self) -> None:
        for index, raw in enumerate(
            self.array(self.root.get("source_manifest"), "$.source_manifest")
        ):
            path = f"$.source_manifest[{index}]"
            item = self.obj(raw, path)
            self.keys(
                item,
                path,
                {"id", "license", "origin", "provenance_class", "retrieval_status", "version"},
            )
            self.register(item.get("id"), f"{path}.id", self.sources, item)
            self.text(item.get("version"), f"{path}.version")
            self.enum(item.get("provenance_class"), ProvenanceClass, f"{path}.provenance_class")
            self.text(item.get("origin"), f"{path}.origin")
            self.text(item.get("license"), f"{path}.license")
            self.text(item.get("retrieval_status"), f"{path}.retrieval_status")
        if not self.sources:
            self.issue("$.source_manifest", "invalid-value", "at least one source is required")

    def _validate_documents(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("documents"), "$.documents")):
            path = f"$.documents[{index}]"
            item = self.obj(raw, path)
            self.keys(
                item,
                path,
                {"classification", "content", "content_digest", "id", "media_type", "source_id", "version"},
            )
            self.register(item.get("id"), f"{path}.id", self.documents, item)
            source_id = self.text(item.get("source_id"), f"{path}.source_id")
            version = self.text(item.get("version"), f"{path}.version")
            self.text(item.get("media_type"), f"{path}.media_type")
            digest = self.text(item.get("content_digest"), f"{path}.content_digest")
            content = self.text(item.get("content"), f"{path}.content", allow_empty=True)
            self.enum(item.get("classification"), Classification, f"{path}.classification")
            self._check_source_version(source_id, version, path)
            if digest is not None and content is not None:
                actual = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
                if digest != actual:
                    self.issue(
                        f"{path}.content_digest",
                        "digest-mismatch",
                        f"declared digest does not match content; expected {actual}",
                    )

    def _validate_issue(self) -> None:
        item = self.obj(self.root.get("issue"), "$.issue")
        self.keys(item, "$.issue", {"body_document_id", "id", "source_id", "title", "version"})
        self.register(item.get("id"), "$.issue.id", {}, item)
        source_id = self.text(item.get("source_id"), "$.issue.source_id")
        version = self.text(item.get("version"), "$.issue.version")
        self.text(item.get("title"), "$.issue.title")
        body_id = self.text(item.get("body_document_id"), "$.issue.body_document_id")
        self._check_source_version(source_id, version, "$.issue")
        if body_id is not None and body_id not in self.documents:
            self.issue("$.issue.body_document_id", "unknown-reference", f"document {body_id!r} is not defined")

    def _validate_world_facts(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("world_facts"), "$.world_facts")):
            path = f"$.world_facts[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"classification", "evidence_ids", "id", "provenance_class", "statement"})
            self.register(item.get("id"), f"{path}.id", self.world_facts, item)
            self.text(item.get("statement"), f"{path}.statement")
            self.string_array(item.get("evidence_ids"), f"{path}.evidence_ids")
            self.enum(item.get("provenance_class"), ProvenanceClass, f"{path}.provenance_class")
            self.enum(item.get("classification"), Classification, f"{path}.classification")

    def _validate_references(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("references"), "$.references")):
            path = f"$.references[{index}]"
            item = self.obj(raw, path)
            self.keys(
                item,
                path,
                {"coverage", "id", "relation", "revision", "source_id"},
                {"target_id"},
            )
            self.register(item.get("id"), f"{path}.id", self.references, item)
            source_id = self.text(item.get("source_id"), f"{path}.source_id")
            revision = self.text(item.get("revision"), f"{path}.revision")
            self.text(item.get("relation"), f"{path}.relation")
            coverage = self.enum(item.get("coverage"), Coverage, f"{path}.coverage")
            self._check_source_version(source_id, revision, path)
            target_id = item.get("target_id")
            if coverage is Coverage.RECORDED:
                if "target_id" not in item:
                    self.issue(
                        f"{path}.target_id",
                        "missing-field",
                        "recorded references require a target",
                    )
                    parsed_target = None
                else:
                    parsed_target = self.text(target_id, f"{path}.target_id")
                if parsed_target is not None and parsed_target not in self.ids:
                    self.issue(f"{path}.target_id", "unknown-reference", f"target {parsed_target!r} is not defined")
            elif coverage is not None and "target_id" in item:
                self.issue(
                    f"{path}.target_id",
                    "coverage-conflict",
                    "unrecorded or unresolved references must not assert a target",
                )

    def _validate_tools(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("tools"), "$.tools")):
            path = f"$.tools[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"id", "operations"})
            self.register(item.get("id"), f"{path}.id", self.tools, item)
            operations = self.string_array(item.get("operations"), f"{path}.operations")
            for op_index, operation in enumerate(operations):
                if operation not in SUPPORTED_OPERATIONS:
                    self.issue(
                        f"{path}.operations[{op_index}]",
                        "unsupported-operation",
                        f"operation {operation!r} is not supported",
                    )

    def _validate_actors(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("actors"), "$.actors")):
            path = f"$.actors[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"id", "initial_knowledge", "permissions", "tool_ids"})
            actor_id = self.register(item.get("id"), f"{path}.id", self.actors, item)
            tool_ids = self.string_array(item.get("tool_ids"), f"{path}.tool_ids")
            for tool_index, tool_id in enumerate(tool_ids):
                if tool_id not in self.tools:
                    self.issue(f"{path}.tool_ids[{tool_index}]", "unknown-reference", f"tool {tool_id!r} is not defined")
            self._validate_knowledge(item.get("initial_knowledge"), f"{path}.initial_knowledge")
            self._validate_permissions(item.get("permissions"), f"{path}.permissions", actor_id)
        if len(self.actors) != 1:
            self.issue("$.actors", "invalid-value", "schema 1.0 requires exactly one actor")

    def _validate_knowledge(self, value: Any, path: str) -> None:
        for index, raw in enumerate(self.array(value, path)):
            item_path = f"{path}[{index}]"
            item = self.obj(raw, item_path)
            self.keys(item, item_path, {"epistemic_state", "evidence_ids", "id", "provenance_class", "statement"})
            self.register(item.get("id"), f"{item_path}.id", self.knowledge, item)
            self.text(item.get("statement"), f"{item_path}.statement")
            self.enum(item.get("epistemic_state"), EpistemicState, f"{item_path}.epistemic_state")
            self.string_array(item.get("evidence_ids"), f"{item_path}.evidence_ids")
            self.enum(item.get("provenance_class"), ProvenanceClass, f"{item_path}.provenance_class")

    def _validate_permissions(self, value: Any, path: str, actor_id: str | None) -> None:
        seen: set[str] = set()
        for index, raw in enumerate(self.array(value, path)):
            item_path = f"{path}[{index}]"
            item = self.obj(raw, item_path)
            self.keys(item, item_path, {"actions", "resource_id"})
            resource_id = self.text(item.get("resource_id"), f"{item_path}.resource_id")
            actions = self.string_array(item.get("actions"), f"{item_path}.actions")
            if resource_id is not None:
                if resource_id in seen:
                    self.issue(f"{item_path}.resource_id", "duplicate-permission", f"permission for {resource_id!r} is duplicated")
                seen.add(resource_id)
                if not self._is_resource(resource_id):
                    self.issue(f"{item_path}.resource_id", "unknown-reference", f"resource {resource_id!r} is not defined")
                classification = self._resource_classification(resource_id)
                if "read" in actions and classification not in ROLE_CEILINGS[Role.ACTOR_POLICY]:
                    self.issue(
                        f"{item_path}.resource_id",
                        "visibility-conflict",
                        f"actor {actor_id!r} cannot receive read permission for {classification.value if classification else 'unknown'} content",
                    )
            for action_index, action in enumerate(actions):
                if action not in SUPPORTED_ACTIONS:
                    self.issue(f"{item_path}.actions[{action_index}]", "unsupported-action", f"action {action!r} is not supported")

    def _validate_access(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("access_outcomes"), "$.access_outcomes")):
            path = f"$.access_outcomes[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"actor_id", "outcome", "resource_id"})
            actor_id = self.text(item.get("actor_id"), f"{path}.actor_id")
            resource_id = self.text(item.get("resource_id"), f"{path}.resource_id")
            self.enum(item.get("outcome"), AccessOutcome, f"{path}.outcome")
            if actor_id is not None and actor_id not in self.actors:
                self.issue(f"{path}.actor_id", "unknown-reference", f"actor {actor_id!r} is not defined")
            if resource_id is not None and not self._is_resource(resource_id):
                self.issue(f"{path}.resource_id", "unknown-reference", f"resource {resource_id!r} is not defined")
            if actor_id is not None and resource_id is not None:
                key = (actor_id, resource_id)
                if key in self.access:
                    self.issue(path, "duplicate-access-outcome", f"access outcome for {key!r} is duplicated")
                else:
                    self.access[key] = item

    def _validate_time_models(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("time_models"), "$.time_models")):
            path = f"$.time_models[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"formula", "id", "provenance_class", "scope", "source", "uncertainty", "unit", "variables"})
            self.register(item.get("id"), f"{path}.id", self.time_models, item)
            self.text(item.get("unit"), f"{path}.unit")
            self.string_array(item.get("variables"), f"{path}.variables")
            formula = self.obj(item.get("formula"), f"{path}.formula")
            self.keys(formula, f"{path}.formula", {"kind", "value"})
            kind = self.text(formula.get("kind"), f"{path}.formula.kind")
            if kind is not None and kind != "constant":
                self.issue(f"{path}.formula.kind", "unsupported-definition", "only constant duration is supported in schema 1.0")
            self.integer(formula.get("value"), f"{path}.formula.value", minimum=1)
            provenance = self.enum(item.get("provenance_class"), ProvenanceClass, f"{path}.provenance_class")
            if provenance is not None and provenance is not ProvenanceClass.SYNTHETIC_ASSUMPTION:
                self.issue(f"{path}.provenance_class", "invalid-value", "CF0 duration must be identified as a synthetic assumption")
            self.text(item.get("source"), f"{path}.source")
            self.text(item.get("uncertainty"), f"{path}.uncertainty")
            scope = self.string_array(item.get("scope"), f"{path}.scope")
            for scope_index, operation in enumerate(scope):
                if operation not in SUPPORTED_OPERATIONS:
                    self.issue(f"{path}.scope[{scope_index}]", "unsupported-operation", f"operation {operation!r} is not supported")

    def _validate_candidates(self) -> None:
        required = {
            "actor_id", "actor_visible_label", "availability", "duration_model_id",
            "evidence_refs", "expected_information", "goal", "id", "knowledge_effects",
            "next_goal_options", "on_failure", "on_success", "operation",
            "operation_preconditions", "required_information", "target_refs",
        }
        for index, raw in enumerate(self.array(self.root.get("candidates"), "$.candidates")):
            path = f"$.candidates[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required)
            self.register(item.get("id"), f"{path}.id", self.candidates, item)
            actor_id = self.text(item.get("actor_id"), f"{path}.actor_id")
            self.text(item.get("goal"), f"{path}.goal")
            self.text(item.get("actor_visible_label"), f"{path}.actor_visible_label")
            required_information = self.string_array(item.get("required_information"), f"{path}.required_information")
            for info_index, info_id in enumerate(required_information):
                if info_id not in self.knowledge:
                    self.issue(f"{path}.required_information[{info_index}]", "unknown-reference", f"knowledge {info_id!r} is not defined")
            operation = self.obj(item.get("operation"), f"{path}.operation")
            self.keys(operation, f"{path}.operation", {"kind", "target_id", "tool_id"})
            kind = self.text(operation.get("kind"), f"{path}.operation.kind")
            tool_id = self.text(operation.get("tool_id"), f"{path}.operation.tool_id")
            target_id = self.text(operation.get("target_id"), f"{path}.operation.target_id")
            if actor_id is not None and actor_id not in self.actors:
                self.issue(f"{path}.actor_id", "unknown-reference", f"actor {actor_id!r} is not defined")
            self._validate_candidate_operation(path, actor_id, kind, tool_id, target_id)
            target_refs = self.string_array(item.get("target_refs"), f"{path}.target_refs")
            self._check_references(target_refs, f"{path}.target_refs")
            self._validate_availability(item.get("availability"), f"{path}.availability", actor_id)
            self._validate_preconditions(item.get("operation_preconditions"), f"{path}.operation_preconditions", actor_id, target_id)
            self._validate_expected_information(item.get("expected_information"), f"{path}.expected_information")
            self._validate_outcome(item.get("on_success"), f"{path}.on_success", success=True)
            self._validate_outcome(item.get("on_failure"), f"{path}.on_failure", success=False)
            self._validate_knowledge(item.get("knowledge_effects"), f"{path}.knowledge_effects")
            self.string_array(item.get("next_goal_options"), f"{path}.next_goal_options")
            duration_id = self.text(item.get("duration_model_id"), f"{path}.duration_model_id")
            if duration_id is not None and duration_id not in self.time_models:
                self.issue(f"{path}.duration_model_id", "unknown-reference", f"time model {duration_id!r} is not defined")
            evidence_refs = self.string_array(item.get("evidence_refs"), f"{path}.evidence_refs")
            self._check_references(evidence_refs, f"{path}.evidence_refs")

    def _validate_candidate_operation(self, path: str, actor_id: str | None, kind: str | None, tool_id: str | None, target_id: str | None) -> None:
        if kind is not None and kind not in SUPPORTED_OPERATIONS:
            self.issue(f"{path}.operation.kind", "unsupported-operation", f"operation {kind!r} is not supported")
        if tool_id is not None:
            tool = self.tools.get(tool_id)
            if tool is None:
                self.issue(f"{path}.operation.tool_id", "unknown-reference", f"tool {tool_id!r} is not defined")
            elif kind is not None and kind not in tool.get("operations", []):
                self.issue(f"{path}.operation.kind", "unsupported-capability", f"tool {tool_id!r} does not provide {kind!r}")
            if actor_id in self.actors and tool_id not in self.actors[actor_id].get("tool_ids", []):
                self.issue(f"{path}.operation.tool_id", "unavailable-tool", f"actor {actor_id!r} does not have tool {tool_id!r}")
        if target_id is not None and not self._is_resource(target_id):
            self.issue(f"{path}.operation.target_id", "unknown-reference", f"resource {target_id!r} is not defined")
        issue_id = self.root.get("issue", {}).get("id") if isinstance(self.root.get("issue"), dict) else None
        if kind == "issue.read" and target_id is not None and target_id != issue_id:
            self.issue(f"{path}.operation.target_id", "target-type-mismatch", "issue.read requires the defined issue")
        if kind == "document.read" and target_id is not None and target_id not in self.documents:
            self.issue(f"{path}.operation.target_id", "target-type-mismatch", "document.read requires a document")

    def _validate_availability(self, value: Any, path: str, actor_id: str | None) -> None:
        item = self.obj(value, path)
        self.keys(item, path, {"required_access"})
        for index, raw in enumerate(self.array(item.get("required_access"), f"{path}.required_access")):
            item_path = f"{path}.required_access[{index}]"
            condition = self.obj(raw, item_path)
            self.keys(condition, item_path, {"outcome", "resource_id"})
            resource_id = self.text(condition.get("resource_id"), f"{item_path}.resource_id")
            outcome = self.enum(condition.get("outcome"), AccessOutcome, f"{item_path}.outcome")
            if actor_id is not None and resource_id is not None:
                declared = self.access.get((actor_id, resource_id))
                if declared is None:
                    self.issue(item_path, "unknown-access-outcome", "candidate access condition has no matching declared outcome")
                elif outcome is not None and declared.get("outcome") != outcome.value:
                    self.issue(f"{item_path}.outcome", "access-conflict", "candidate condition contradicts the declared access outcome")

    def _validate_preconditions(self, value: Any, path: str, actor_id: str | None, target_id: str | None) -> None:
        item = self.obj(value, path)
        self.keys(item, path, {"permissions", "required_version"})
        permissions = self.string_array(item.get("permissions"), f"{path}.permissions")
        required_version = self.text(item.get("required_version"), f"{path}.required_version")
        target_version = self._resource_version(target_id)
        if required_version is not None and target_version is not None and required_version != target_version:
            self.issue(f"{path}.required_version", "version-mismatch", f"required version {required_version!r} does not match target version {target_version!r}")
        if actor_id in self.actors and target_id is not None:
            grants = {
                permission.get("resource_id"): set(permission.get("actions", []))
                for permission in self.actors[actor_id].get("permissions", [])
                if isinstance(permission, dict)
            }
            for index, permission in enumerate(permissions):
                if permission not in grants.get(target_id, set()):
                    self.issue(f"{path}.permissions[{index}]", "permission-missing", f"actor {actor_id!r} lacks {permission!r} on {target_id!r}")

    def _validate_expected_information(self, value: Any, path: str) -> None:
        for index, raw in enumerate(self.array(value, path)):
            item_path = f"{path}[{index}]"
            item = self.obj(raw, item_path)
            self.keys(item, item_path, {"classification", "id"})
            self.register(
                item.get("id"),
                f"{item_path}.id",
                self.expected_information,
                item,
            )
            self.enum(item.get("classification"), Classification, f"{item_path}.classification")

    def _validate_outcome(self, value: Any, path: str, *, success: bool) -> None:
        item = self.obj(value, path)
        required = {"status"} if success else {"reason", "status"}
        self.keys(item, path, required)
        status = self.text(item.get("status"), f"{path}.status")
        allowed = "completed" if success else "incomplete"
        if status is not None and status != allowed:
            self.issue(f"{path}.status", "invalid-value", f"expected {allowed!r}")
        if not success:
            self.text(item.get("reason"), f"{path}.reason")

    def _validate_policies(self) -> None:
        for index, raw in enumerate(self.array(self.root.get("policies"), "$.policies")):
            path = f"$.policies[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"actor_id", "candidate_priority", "id", "kind"})
            self.register(item.get("id"), f"{path}.id", self.policies, item)
            actor_id = self.text(item.get("actor_id"), f"{path}.actor_id")
            if actor_id is not None and actor_id not in self.actors:
                self.issue(
                    f"{path}.actor_id",
                    "unknown-reference",
                    f"actor {actor_id!r} is not defined",
                )
            kind = self.text(item.get("kind"), f"{path}.kind")
            if kind is not None and kind != "deterministic-priority":
                self.issue(f"{path}.kind", "unsupported-definition", "only deterministic-priority is supported in schema 1.0")
            candidate_ids = self.string_array(item.get("candidate_priority"), f"{path}.candidate_priority")
            for candidate_index, candidate_id in enumerate(candidate_ids):
                if candidate_id not in self.candidates:
                    self.issue(f"{path}.candidate_priority[{candidate_index}]", "unknown-reference", f"candidate {candidate_id!r} is not defined")
                elif (
                    actor_id is not None
                    and self.candidates[candidate_id].get("actor_id") != actor_id
                ):
                    self.issue(
                        f"{path}.candidate_priority[{candidate_index}]",
                        "actor-policy-mismatch",
                        f"candidate {candidate_id!r} belongs to another actor",
                    )
            if len(candidate_ids) != len(set(candidate_ids)):
                self.issue(f"{path}.candidate_priority", "duplicate-reference", "candidate priority contains a duplicate")
        if not self.policies:
            self.issue("$.policies", "invalid-value", "at least one policy is required")

    def _validate_future_sections(self) -> None:
        for key in ("patches", "checks", "response_models"):
            values = self.array(self.root.get(key), f"$.{key}")
            if values:
                self.issue(f"$.{key}", "unsupported-definition", f"{key} are not supported until a later task")

    def _validate_timeline(self) -> None:
        item = self.obj(self.root.get("timeline"), "$.timeline")
        required = {"deadline_tick", "observation_end_tick", "observation_start_tick", "start_tick", "time_unit"}
        self.keys(item, "$.timeline", required)
        start = self.integer(item.get("start_tick"), "$.timeline.start_tick")
        deadline = self.integer(item.get("deadline_tick"), "$.timeline.deadline_tick")
        observation_start = self.integer(item.get("observation_start_tick"), "$.timeline.observation_start_tick")
        observation_end = self.integer(item.get("observation_end_tick"), "$.timeline.observation_end_tick")
        self.text(item.get("time_unit"), "$.timeline.time_unit")
        if start is not None and deadline is not None and deadline <= start:
            self.issue("$.timeline.deadline_tick", "invalid-timeline", "deadline must be later than start")
        if None not in (start, deadline, observation_start, observation_end):
            assert start is not None and deadline is not None
            assert observation_start is not None and observation_end is not None
            if not (start <= observation_start <= observation_end <= deadline):
                self.issue("$.timeline", "invalid-timeline", "observation window must be inside the execution window")

    def _validate_disclosure(self) -> None:
        item = self.obj(self.root.get("disclosure"), "$.disclosure")
        self.keys(item, "$.disclosure", {"role_allowlists"})
        allowlists = self.obj(item.get("role_allowlists"), "$.disclosure.role_allowlists")
        expected_roles = {role.value for role in Role}
        self.keys(allowlists, "$.disclosure.role_allowlists", expected_roles)
        for role in Role:
            values = self.string_array(allowlists.get(role.value), f"$.disclosure.role_allowlists.{role.value}")
            parsed: set[Classification] = set()
            for index, raw in enumerate(values):
                try:
                    parsed.add(Classification(raw))
                except ValueError:
                    self.issue(f"$.disclosure.role_allowlists.{role.value}[{index}]", "invalid-value", f"classification {raw!r} is not defined")
            excess = parsed - ROLE_CEILINGS[role]
            if excess:
                names = ", ".join(sorted(item.value for item in excess))
                self.issue(f"$.disclosure.role_allowlists.{role.value}", "role-ceiling-exceeded", f"allowlist exceeds the fixed role ceiling: {names}")

    def _validate_retention(self) -> None:
        item = self.obj(self.root.get("retention"), "$.retention")
        self.keys(item, "$.retention", {"retained", "retained_since_tick"})
        retained = self.boolean(item.get("retained"), "$.retention.retained")
        retained_since = self.integer(item.get("retained_since_tick"), "$.retention.retained_since_tick")
        timeline = self.root.get("timeline")
        start = timeline.get("start_tick") if isinstance(timeline, dict) else None
        if retained is False:
            self.issue("$.retention.retained", "invalid-value", "CF0 must be retained for later conformance checks")
        if retained_since is not None and type(start) is int and retained_since > start:
            self.issue("$.retention.retained_since_tick", "invalid-value", "retention must begin no later than the run start")

    def _check_source_version(self, source_id: str | None, version: str | None, path: str) -> None:
        if source_id is None:
            return
        source = self.sources.get(source_id)
        if source is None:
            self.issue(f"{path}.source_id", "unknown-reference", f"source {source_id!r} is not defined")
            return
        source_version = source.get("version")
        if version is not None and isinstance(source_version, str) and version != source_version:
            field = "revision" if "revision" in self.obj(self._lookup_path_object(path), path) else "version"
            self.issue(f"{path}.{field}", "version-mismatch", f"{version!r} does not match source version {source_version!r}")

    def _lookup_path_object(self, path: str) -> Any:
        # Only used to select a precise error field; callers have already validated objects.
        if path.startswith("$.references["):
            index = int(path.removeprefix("$.references[").split("]", 1)[0])
            values = self.root.get("references", [])
            if isinstance(values, list) and index < len(values):
                return values[index]
        return {}

    def _check_references(self, reference_ids: Sequence[str], path: str) -> None:
        for index, reference_id in enumerate(reference_ids):
            if reference_id not in self.references:
                self.issue(f"{path}[{index}]", "unknown-reference", f"reference {reference_id!r} is not defined")

    def _is_resource(self, identifier: str) -> bool:
        issue = self.root.get("issue")
        issue_id = issue.get("id") if isinstance(issue, dict) else None
        return identifier == issue_id or identifier in self.documents

    def _resource_version(self, identifier: str | None) -> str | None:
        if identifier is None:
            return None
        if identifier in self.documents:
            value = self.documents[identifier].get("version")
            return value if isinstance(value, str) else None
        issue = self.root.get("issue")
        if isinstance(issue, dict) and issue.get("id") == identifier:
            value = issue.get("version")
            return value if isinstance(value, str) else None
        return None

    def _resource_classification(self, identifier: str) -> Classification | None:
        if identifier in self.documents:
            raw = self.documents[identifier].get("classification")
            if not isinstance(raw, str):
                return None
            try:
                return Classification(raw)
            except ValueError:
                return None
        issue = self.root.get("issue")
        if isinstance(issue, dict) and issue.get("id") == identifier:
            body_id = issue.get("body_document_id")
            if isinstance(body_id, str):
                return self._resource_classification(body_id)
        return None

    def _evidence_ids(self) -> set[str]:
        issue = self.root.get("issue")
        issue_id = issue.get("id") if isinstance(issue, dict) else None
        values = set(self.documents) | set(self.references) | set(self.world_facts)
        if isinstance(issue_id, str):
            values.add(issue_id)
        return values

    def _validate_evidence_links(self) -> None:
        available = self._evidence_ids()
        sections: list[tuple[str, list[Any]]] = []
        for name in ("world_facts",):
            raw = self.root.get(name)
            if isinstance(raw, list):
                sections.append((f"$.{name}", raw))
        actors = self.root.get("actors")
        if isinstance(actors, list):
            for actor_index, actor in enumerate(actors):
                if isinstance(actor, dict) and isinstance(actor.get("initial_knowledge"), list):
                    sections.append((f"$.actors[{actor_index}].initial_knowledge", actor["initial_knowledge"]))
        candidates = self.root.get("candidates")
        if isinstance(candidates, list):
            for candidate_index, candidate in enumerate(candidates):
                if isinstance(candidate, dict) and isinstance(candidate.get("knowledge_effects"), list):
                    sections.append((f"$.candidates[{candidate_index}].knowledge_effects", candidate["knowledge_effects"]))
        for section_path, items in sections:
            for item_index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                evidence = item.get("evidence_ids")
                if not isinstance(evidence, list):
                    continue
                for evidence_index, identifier in enumerate(evidence):
                    if isinstance(identifier, str) and identifier not in available:
                        self.issue(
                            f"{section_path}[{item_index}].evidence_ids[{evidence_index}]",
                            "unknown-reference",
                            f"evidence {identifier!r} is not defined",
                        )

    def build(self) -> WorldDefinition:
        root = self.root
        canonical = canonical_json_bytes(root)
        content_id = "sha256:" + hashlib.sha256(canonical).hexdigest()

        sources = tuple(
            SourceRecord(
                id=item["id"], version=item["version"],
                provenance_class=ProvenanceClass(item["provenance_class"]),
                origin=item["origin"], license=item["license"],
                retrieval_status=item["retrieval_status"],
            )
            for item in root["source_manifest"]
        )
        documents = tuple(
            Document(
                id=item["id"], source_id=item["source_id"], version=item["version"],
                media_type=item["media_type"], content_digest=item["content_digest"],
                content=item["content"], classification=Classification(item["classification"]),
            )
            for item in root["documents"]
        )
        issue = Issue(**root["issue"])
        world_facts = tuple(
            WorldFact(
                id=item["id"], statement=item["statement"],
                evidence_ids=tuple(item["evidence_ids"]),
                provenance_class=ProvenanceClass(item["provenance_class"]),
                classification=Classification(item["classification"]),
            )
            for item in root["world_facts"]
        )
        references = tuple(
            Reference(
                id=item["id"], source_id=item["source_id"], revision=item["revision"],
                relation=item["relation"], coverage=Coverage(item["coverage"]),
                target_id=item.get("target_id"),
            )
            for item in root["references"]
        )
        actors = tuple(self._build_actor(item) for item in root["actors"])
        tools = tuple(Tool(id=item["id"], operations=frozenset(item["operations"])) for item in root["tools"])
        access_outcomes = tuple(
            ResourceAccess(
                actor_id=item["actor_id"], resource_id=item["resource_id"],
                outcome=AccessOutcome(item["outcome"]),
            )
            for item in root["access_outcomes"]
        )
        policies = tuple(
            Policy(
                id=item["id"],
                actor_id=item["actor_id"],
                kind=item["kind"],
                candidate_priority=tuple(item["candidate_priority"]),
            )
            for item in root["policies"]
        )
        candidates = tuple(self._build_candidate(item) for item in root["candidates"])
        time_models = tuple(
            TimeModel(
                id=item["id"], unit=item["unit"], constant_value=item["formula"]["value"],
                provenance_class=ProvenanceClass(item["provenance_class"]),
                uncertainty=item["uncertainty"], scope=tuple(item["scope"]),
            )
            for item in root["time_models"]
        )
        timeline = Timeline(**root["timeline"])
        disclosure = Disclosure(
            role_allowlists=tuple(
                (role, frozenset(Classification(value) for value in root["disclosure"]["role_allowlists"][role.value]))
                for role in Role
            )
        )
        retention = Retention(**root["retention"])
        fixture = FixtureMetadata(**root["fixture"])
        return WorldDefinition(
            schema_version=root["schema_version"], exercise_id=root["exercise_id"],
            fixture=fixture, seed=root["seed"], sources=sources, documents=documents,
            issue=issue, world_facts=world_facts, references=references, actors=actors,
            tools=tools, access_outcomes=access_outcomes, policies=policies,
            candidates=candidates, time_models=time_models, timeline=timeline,
            disclosure=disclosure, retention=retention, content_id=content_id,
            canonical_bytes=canonical,
        )

    def _build_actor(self, item: JsonObject) -> Actor:
        return Actor(
            id=item["id"],
            initial_knowledge=tuple(
                KnowledgeClaim(
                    id=claim["id"], statement=claim["statement"],
                    epistemic_state=EpistemicState(claim["epistemic_state"]),
                    evidence_ids=tuple(claim["evidence_ids"]),
                    provenance_class=ProvenanceClass(claim["provenance_class"]),
                )
                for claim in item["initial_knowledge"]
            ),
            tool_ids=tuple(item["tool_ids"]),
            permissions=tuple(
                Permission(resource_id=permission["resource_id"], actions=frozenset(permission["actions"]))
                for permission in item["permissions"]
            ),
        )

    def _build_candidate(self, item: JsonObject) -> Candidate:
        operation = item["operation"]
        availability = item["availability"]
        preconditions = item["operation_preconditions"]
        return Candidate(
            id=item["id"], actor_id=item["actor_id"], goal=item["goal"],
            actor_visible_label=item["actor_visible_label"],
            operation_kind=operation["kind"], tool_id=operation["tool_id"],
            target_id=operation["target_id"], target_refs=tuple(item["target_refs"]),
            duration_model_id=item["duration_model_id"],
            evidence_refs=tuple(item["evidence_refs"]),
            required_information=tuple(item["required_information"]),
            required_permissions=frozenset(preconditions["permissions"]),
            required_version=preconditions["required_version"],
            required_access=tuple(
                (access["resource_id"], AccessOutcome(access["outcome"]))
                for access in availability["required_access"]
            ),
            knowledge_effects=tuple(
                KnowledgeClaim(
                    id=claim["id"],
                    statement=claim["statement"],
                    epistemic_state=EpistemicState(claim["epistemic_state"]),
                    evidence_ids=tuple(claim["evidence_ids"]),
                    provenance_class=ProvenanceClass(claim["provenance_class"]),
                )
                for claim in item["knowledge_effects"]
            ),
            success_status=item["on_success"]["status"],
            failure_status=item["on_failure"]["status"],
            failure_reason=item["on_failure"]["reason"],
        )
