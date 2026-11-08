"""Validation for the frozen G2 scenario catalog; no execution occurs here."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never

from lae_simulator.world.errors import ValidationIssue, WorldValidationError

JsonObject = dict[str, Any]
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
OPERATIONS = frozenset({
    "ai.delegate", "ai.integrate", "check.model", "code.search",
    "document.read", "file.open", "issue.read", "patch.apply",
    "patch.revert", "pr.create", "question.send", "run.defer",
    "symbol.navigate", "wait", "work.compare",
})
EXPRESSION_OPERATORS = frozenset({"add", "equals", "remove", "set", "subset"})
EXPRESSION_FIELD_PREFIXES = (
    "access.", "admin.", "ai.", "business.", "check.", "contact.",
    "deadline.", "goal.", "knowledge.", "outcome.", "permission.",
    "question.", "run.", "submission.", "tasks.", "tool.", "workspace.",
)
PREDICATES = frozenset({
    "all", "equals", "nonempty-url", "not", "one-of", "present",
    "recorded", "same-version", "type-allowed",
})
SUPPORTED_SCENARIO_VERSIONS = frozenset({"1.0.0", "1.1.0", "1.2.0", "1.3.0"})


class _DuplicateKeyError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _constant(value: str) -> Never:
    raise ValueError(f"non-finite JSON number is not supported: {value}")


@dataclass(frozen=True)
class ScenarioBundle:
    schema_version: str
    exercise_id: str
    candidate_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    patch_ids: tuple[str, ...]
    check_ids: tuple[str, ...]
    actor_view: tuple[tuple[str, str], ...]
    content_id: str


def load_scenario_bundle(path: str | Path) -> ScenarioBundle:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WorldValidationError([ValidationIssue("$", "input-read-failed", str(error))]) from error
    try:
        data = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except _DuplicateKeyError as error:
        raise WorldValidationError([ValidationIssue("$", "duplicate-key", str(error))]) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise WorldValidationError([ValidationIssue("$", "invalid-json", str(error))]) from error
    return load_scenario_bundle_data(data, source.parent)


def load_scenario_bundle_data(data: Any, bundle_dir: str | Path) -> ScenarioBundle:
    """Validate already-parsed scenario data against files in ``bundle_dir``."""
    validator = _Validator(data, Path(bundle_dir))
    validator.validate()
    if validator.issues:
        raise WorldValidationError(validator.issues)
    return validator.build()


class _Validator:
    def __init__(self, data: Any, bundle_dir: Path) -> None:
        self.data = data
        self.bundle_dir = bundle_dir
        self.root: JsonObject = {}
        self.issues: list[ValidationIssue] = []
        self.ids: dict[str, str] = {}
        self.sources: set[str] = set()
        self.source_digests: dict[str, set[str]] = {}
        self.source_classes: dict[str, str] = {}
        self.references: set[str] = set()
        self.claims: set[str] = set()
        self.candidates: set[str] = set()
        self.patches: set[str] = set()
        self.semantic_fact_ids: set[str] = set()

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

    def text(self, value: Any, path: str) -> str | None:
        if not isinstance(value, str):
            self.issue(path, "invalid-type", "expected a string")
            return None
        if not value:
            self.issue(path, "invalid-value", "string must not be empty")
            return None
        return value

    def keys(self, value: JsonObject, path: str, required: set[str], optional: set[str] | None = None) -> None:
        optional = optional or set()
        for key in sorted(required - value.keys()):
            self.issue(f"{path}.{key}", "missing-field", "required field is missing")
        for key in sorted(value.keys() - required - optional):
            self.issue(f"{path}.{key}", "unsupported-field", "field is not supported")

    def strings(self, value: Any, path: str) -> list[str]:
        result: list[str] = []
        for index, raw in enumerate(self.array(value, path)):
            parsed = self.text(raw, f"{path}[{index}]")
            if parsed is not None:
                result.append(parsed)
        if len(result) != len(set(result)):
            self.issue(path, "duplicate-reference", "array contains a duplicate")
        return result

    def register(self, value: Any, path: str, group: set[str]) -> str | None:
        identifier = self.text(value, path)
        if identifier is None:
            return None
        if identifier in self.ids:
            self.issue(path, "duplicate-id", f"already defined at {self.ids[identifier]}")
        else:
            self.ids[identifier] = path
            group.add(identifier)
        return identifier

    def validate(self) -> None:
        self.root = self.obj(self.data, "$")
        required = {
            "actor_view", "candidates", "checks", "context", "documents",
            "exercise_id", "extraction_history", "participant_profile", "patches", "references", "rules",
            "schema_version", "source_manifest", "world_claims",
        }
        optional = {"semantic_model", "timing", "collaboration"}
        if self.root.get('schema_version') == '1.3.0':
            optional.add('tool_availability')
        self.keys(self.root, "$", required, optional)
        if 'tool_availability' in self.root:
            tools = self.obj(self.root['tool_availability'], '$.tool_availability')
            self.keys(tools, '$.tool_availability', {'code.search'})
            if type(tools.get('code.search')) is not bool:
                self.issue('$.tool_availability', 'invalid-value', 'search availability must be boolean')
        schema_version = self.text(self.root.get("schema_version"), "$.schema_version")
        if schema_version not in SUPPORTED_SCENARIO_VERSIONS:
            self.issue("$.schema_version", "unsupported-version", "expected a supported Scenario version (1.0.0 through 1.3.0)")
        if schema_version in {"1.1.0", "1.2.0", "1.3.0"} and "semantic_model" not in self.root:
            self.issue("$.semantic_model", "missing-field", "scenario requires a bounded semantic model")
        if schema_version == "1.0.0" and "semantic_model" in self.root:
            self.issue("$.semantic_model", "version-conflict", "semantic models require scenario 1.1.0")
        self.text(self.root.get("exercise_id"), "$.exercise_id")
        self._validate_sources()
        self._validate_documents()
        self._validate_references()
        self._validate_claims()
        self._validate_context()
        self._validate_participant_profile()
        if schema_version == '1.3.0':
            profile = self.root.get('participant_profile')
            if isinstance(profile, dict):
                self._knowledge_refs(profile.get('initial_claim_ids'), '$.participant_profile.initial_claim_ids')
        self._validate_candidates()
        if "timing" in self.root:
            from lae_simulator.world.timing import load_timing
            candidate_rows = self.root.get("candidates")
            candidate_rows = candidate_rows if isinstance(candidate_rows, list) else []
            try:
                timing = load_timing(self.root["timing"], {
                    item["duration_model"] for item in candidate_rows
                    if isinstance(item, dict) and isinstance(item.get("duration_model"), str)
                })
                models = {item.id: item for item in timing.models}
                candidate_ids = {item.get("id") for item in candidate_rows if isinstance(item, dict)
                                 and isinstance(item.get("id"), str)}
                if any(control.target_candidate_id not in candidate_ids for control in timing.controls):
                    self.issue("$.timing.controls", "unknown-control-target", "control candidate is not defined")
                for item in candidate_rows:
                    if (isinstance(item, dict) and isinstance(item.get("duration_model"), str)
                            and item["duration_model"] in models
                            and item.get("operation") not in models[item["duration_model"]].scope):
                        self.issue("$.timing", "invalid-timing-scope", "duration model does not cover candidate operation")
            except (TypeError, ValueError) as error:
                self.issue("$.timing", "invalid-timing", str(error))
        self._validate_rules()
        self._validate_patches()
        candidate_data = self.root.get("candidates")
        for index, item in enumerate(candidate_data if isinstance(candidate_data, list) else []):
            if isinstance(item, dict):
                patch_ids = item.get("patch_ids", [])
                for patch_id in patch_ids if isinstance(patch_ids, list) else []:
                    if isinstance(patch_id, str) and patch_id not in self.patches:
                        self.issue(f"$.candidates[{index}].patch_ids", "unknown-patch", str(patch_id))
        self._validate_semantic_model()
        self._validate_checks()
        if "collaboration" in self.root:
            from lae_simulator.world.collaboration import (
                collaboration_scopes,
                load_collaboration,
            )
            try:
                if "timing" not in self.root:
                    raise ValueError("collaboration requires explicit scheduler timing")
                claims, evidence = collaboration_scopes(self.root, self.source_classes)
                collaboration = load_collaboration(self.root["collaboration"], claims, evidence, self.patches)
                profile = self.root['participant_profile']
                contacts = {row['id']: row for row in profile['contacts']}
                for peer in collaboration.collaborators:
                    if peer.kind == 'peer' and (peer.id not in contacts or
                            peer.approval_scopes and not contacts[peer.id]['can_approve']):
                        raise ValueError('collaborator exceeds the participant contact/approval profile')
                for rule in collaboration.rules:
                    if (rule.operation == 'ai.delegate' and rule.overlay_patch_id is not None
                            and not profile['ai']['can_edit'] and rule.required_scope is None):
                        raise ValueError('AI overlay without initial edit permission requires an explicit scope')
                    if rule.operation == 'ai.delegate' and rule.required_scope is not None and not any(
                        approval.operation == 'approval.request' and approval.collaborator_id == rule.approver_id
                        and approval.required_scope == rule.required_scope for approval in collaboration.rules):
                        raise ValueError('required AI scope has no fixed approver rule')
            except (TypeError, ValueError) as error:
                self.issue("$.collaboration", "invalid-collaboration", str(error))
        self._validate_actor_view()
        self._validate_history()

    def _validate_sources(self) -> None:
        required = {"digest", "id", "manifest_path", "revision"}
        for index, raw in enumerate(self.array(self.root.get("source_manifest"), "$.source_manifest")):
            path = f"$.source_manifest[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required)
            self.register(item.get("id"), f"{path}.id", self.sources)
            self.text(item.get("revision"), f"{path}.revision")
            self._digest(item.get("digest"), f"{path}.digest")
            relative = self.text(item.get("manifest_path"), f"{path}.manifest_path")
            if relative is not None:
                self._check_g1_source(path, item, relative)

    def _check_g1_source(self, path: str, item: JsonObject, relative: str) -> None:
        source = (self.bundle_dir / relative).resolve()
        try:
            source.relative_to(self.bundle_dir.parent.resolve())
            manifest = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            self.issue(f"{path}.manifest_path", "source-manifest-invalid", str(error))
            return
        record = next((entry for entry in manifest.get("sources", []) if entry.get("id") == item.get("id")), None)
        if record is None:
            self.issue(f"{path}.id", "unknown-reference", "source is absent from G1 manifest")
            return
        if record.get("revision") != item.get("revision"):
            self.issue(f"{path}.revision", "version-mismatch", "revision differs from G1 manifest")
        digests = {f"sha256:{entry.get('sha256')}" for entry in record.get("files", [])}
        if isinstance(item.get("id"), str):
            self.source_digests[item["id"]] = digests
            self.source_classes[item["id"]] = str(record.get("classification", ""))
        if item.get("digest") not in digests:
            self.issue(f"{path}.digest", "digest-mismatch", "digest is absent from the G1 source")

    def _digest(self, value: Any, path: str) -> None:
        digest = self.text(value, path)
        if digest is not None and SHA256.fullmatch(digest) is None:
            self.issue(path, "invalid-digest", "expected sha256:<64 lowercase hex>")

    def _validate_documents(self) -> None:
        required = {"availability", "classification", "digest", "id", "source_id"}
        document_ids: set[str] = set()
        for index, raw in enumerate(self.array(self.root.get("documents"), "$.documents")):
            path = f"$.documents[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required)
            self.register(item.get("id"), f"{path}.id", document_ids)
            if item.get("source_id") not in self.sources:
                self.issue(f"{path}.source_id", "unknown-reference", "source is not defined")
            self._digest(item.get("digest"), f"{path}.digest")
            source_id = item.get("source_id")
            if isinstance(source_id, str) and item.get("digest") not in self.source_digests.get(source_id, set()):
                self.issue(f"{path}.digest", "digest-mismatch", "digest is absent from the G1 source")
            if item.get("classification") not in {"actor-private", "administrative", "public-evidence"}:
                self.issue(f"{path}.classification", "invalid-value", "unknown classification")
            if item.get("availability") not in {"available", "unavailable", "audit-only"}:
                self.issue(f"{path}.availability", "invalid-value", "unknown availability")

    def _validate_references(self) -> None:
        required = {"coverage", "evidence", "id", "relation", "source_id"}
        for index, raw in enumerate(self.array(self.root.get("references"), "$.references")):
            path = f"$.references[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required, {"target_id"})
            self.register(item.get("id"), f"{path}.id", self.references)
            if item.get("source_id") not in self.sources:
                self.issue(f"{path}.source_id", "unknown-reference", "source is not defined")
            coverage = item.get("coverage")
            if coverage not in {"recorded", "unrecorded", "unresolved"}:
                self.issue(f"{path}.coverage", "invalid-value", "unknown coverage")
            if coverage == "recorded" and "target_id" not in item:
                self.issue(f"{path}.target_id", "missing-field", "recorded reference requires target")
            if coverage != "recorded" and "target_id" in item:
                self.issue(f"{path}.target_id", "coverage-conflict", "uncertain reference must not assert target")
            self.text(item.get("relation"), f"{path}.relation")
            self.text(item.get("evidence"), f"{path}.evidence")

    def _validate_claims(self) -> None:
        required = {"classification", "id", "origin", "source_ids", "statement", "status"}
        for index, raw in enumerate(self.array(self.root.get("world_claims"), "$.world_claims")):
            path = f"$.world_claims[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required)
            self.register(item.get("id"), f"{path}.id", self.claims)
            self.text(item.get("statement"), f"{path}.statement")
            if item.get("origin") not in {"fictional-setting", "real-oss", "synthetic-assumption"}:
                self.issue(f"{path}.origin", "invalid-value", "unknown origin")
            if item.get("status") not in {"additional-assumption", "draft-setting", "provisional", "undetermined"}:
                self.issue(f"{path}.status", "invalid-value", "unknown status")
            if item.get("classification") not in {"actor-private", "administrative", "public-evidence"}:
                self.issue(f"{path}.classification", "invalid-value", "unknown classification")
            for source_index, source_id in enumerate(self.strings(item.get("source_ids"), f"{path}.source_ids")):
                if source_id not in self.sources:
                    self.issue(f"{path}.source_ids[{source_index}]", "unknown-reference", "source is not defined")

    def _validate_context(self) -> None:
        context = self.obj(self.root.get("context"), "$.context")
        self.keys(context, "$.context", {"company_context", "exercise_scenario", "team_profile"})
        for name in ("company_context", "team_profile", "exercise_scenario"):
            item = self.obj(context.get(name), f"$.context.{name}")
            self.keys(item, f"$.context.{name}", {"claim_ids"})
            for index, claim_id in enumerate(self.strings(item.get("claim_ids"), f"$.context.{name}.claim_ids")):
                if claim_id not in self.claims:
                    self.issue(f"$.context.{name}.claim_ids[{index}]", "unknown-reference", "claim is not defined")

    def _validate_participant_profile(self) -> None:
        path = "$.participant_profile"
        profile = self.obj(self.root.get("participant_profile"), path)
        self.keys(profile, path, {"actor_id", "ai", "contacts", "initial_claim_ids", "operation_capabilities", "permissions"})
        self.text(profile.get("actor_id"), f"{path}.actor_id")
        for index, claim_id in enumerate(self.strings(profile.get("initial_claim_ids"), f"{path}.initial_claim_ids")):
            if claim_id not in self.claims:
                self.issue(f"{path}.initial_claim_ids[{index}]", "unknown-reference", "claim is not defined")
        for index, operation in enumerate(self.strings(profile.get("operation_capabilities"), f"{path}.operation_capabilities")):
            if operation not in OPERATIONS:
                self.issue(f"{path}.operation_capabilities[{index}]", "unsupported-operation", "operation is not supported")
        seen_permissions: set[tuple[str, str]] = set()
        for index, raw in enumerate(self.array(profile.get("permissions"), f"{path}.permissions")):
            item_path = f"{path}.permissions[{index}]"
            permission = self.obj(raw, item_path)
            self.keys(permission, item_path, {"action", "resource_id"})
            resource_id = self.text(permission.get("resource_id"), f"{item_path}.resource_id")
            action = self.text(permission.get("action"), f"{item_path}.action")
            if resource_id is not None and action is not None:
                pair = (resource_id, action)
                if pair in seen_permissions:
                    self.issue(item_path, "duplicate-permission", "permission is duplicated")
                seen_permissions.add(pair)
        seen_contacts: set[str] = set()
        for index, raw in enumerate(self.array(profile.get("contacts"), f"{path}.contacts")):
            item_path = f"{path}.contacts[{index}]"
            contact = self.obj(raw, item_path)
            self.keys(contact, item_path, {"can_approve", "id", "knowledge_scope"})
            contact_id = self.text(contact.get("id"), f"{item_path}.id")
            self.text(contact.get("knowledge_scope"), f"{item_path}.knowledge_scope")
            if type(contact.get("can_approve")) is not bool:
                self.issue(f"{item_path}.can_approve", "invalid-type", "expected a boolean")
            if contact_id in seen_contacts:
                self.issue(f"{item_path}.id", "duplicate-id", "contact is duplicated")
            elif contact_id is not None:
                seen_contacts.add(contact_id)
        ai = self.obj(profile.get("ai"), f"{path}.ai")
        self.keys(ai, f"{path}.ai", {"allowed", "can_edit", "input_classifications"})
        for field in ("allowed", "can_edit"):
            if type(ai.get(field)) is not bool:
                self.issue(f"{path}.ai.{field}", "invalid-type", "expected a boolean")
        for index, classification in enumerate(self.strings(ai.get("input_classifications"), f"{path}.ai.input_classifications")):
            if classification not in {"actor-private", "public-evidence"}:
                self.issue(f"{path}.ai.input_classifications[{index}]", "visibility-conflict", "AI input exceeds actor-visible classifications")

    def _knowledge_refs(self, value: Any, path: str) -> None:
        rows = self.root.get('world_claims')
        rows = rows if isinstance(rows, list) else []
        claims = {row['id']: row for row in rows
                  if isinstance(row, dict) and isinstance(row.get('id'), str)}
        for identifier in self.strings(value, path):
            claim = claims.get(identifier)
            if claim is None:
                self.issue(path, 'unknown-reference', 'knowledge claim is undefined')
            elif (not isinstance(claim.get('source_ids'), list)
                  or not claim.get('source_ids')
                  or claim.get('classification') == 'administrative'
                  or any(self.source_classes.get(source) == 'audit_only_comment'
                         for source in claim.get('source_ids', []) if isinstance(source, str))):
                self.issue(path, 'visibility-conflict', 'knowledge requires actor-eligible sources')

    def _validate_candidates(self) -> None:
        required = {
            "actor_visible_label", "availability", "duration_model", "effects", "evidence_refs",
            "expected_information", "failure", "goal", "id", "next_goal_options",
            "operation", "preconditions", "target_refs",
        }
        for index, raw in enumerate(self.array(self.root.get("candidates"), "$.candidates")):
            path = f"$.candidates[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required, {'patch_ids', 'required_claims'}
                      if self.root.get('schema_version') == '1.3.0' else {'patch_ids'})
            if 'required_claims' in item:
                self._knowledge_refs(item['required_claims'], path + '.required_claims')
            if (self.root.get("schema_version") in {"1.2.0", "1.3.0"}
                    and item.get("operation") == "patch.apply" and not item.get("patch_ids")):
                self.issue(f"{path}.patch_ids", "missing-patch-targets", "patch.apply requires explicit targets")
            if "patch_ids" in item:
                self.strings(item["patch_ids"], f"{path}.patch_ids")
                if item.get("operation") != "patch.apply":
                    self.issue(f"{path}.patch_ids", "invalid-operation", "patch targets require patch.apply")
            self.register(item.get("id"), f"{path}.id", self.candidates)
            for field in ("actor_visible_label", "duration_model", "expected_information", "failure", "goal"):
                self.text(item.get(field), f"{path}.{field}")
            if item.get("operation") not in OPERATIONS:
                self.issue(f"{path}.operation", "unsupported-operation", "operation is not supported")
            profile = self.root.get("participant_profile")
            capabilities = profile.get("operation_capabilities", []) if isinstance(profile, dict) else []
            if item.get("operation") not in capabilities:
                self.issue(f"{path}.operation", "unavailable-operation", "operation is absent from participant capabilities")
            for field in ("availability", "preconditions", "effects"):
                self._expressions(item.get(field), f"{path}.{field}")
            for field in ("target_refs", "evidence_refs"):
                for ref_index, ref_id in enumerate(self.strings(item.get(field), f"{path}.{field}")):
                    if ref_id not in self.references:
                        self.issue(f"{path}.{field}[{ref_index}]", "unknown-reference", "reference is not defined")
            self.strings(item.get("next_goal_options"), f"{path}.next_goal_options")

    def _expressions(self, value: Any, path: str) -> None:
        for index, raw in enumerate(self.array(value, path)):
            item_path = f"{path}[{index}]"
            expression = self.obj(raw, item_path)
            self.keys(expression, item_path, {"field", "operator", "value"})
            field = self.text(expression.get("field"), f"{item_path}.field")
            if field is not None and not field.startswith(EXPRESSION_FIELD_PREFIXES):
                self.issue(f"{item_path}.field", "unsupported-field-reference", "expression field is not supported")
            if expression.get("operator") not in EXPRESSION_OPERATORS:
                self.issue(f"{item_path}.operator", "unsupported-operator", "operator is not supported")
            if not isinstance(expression.get("value"), (str, bool, int)):
                self.issue(f"{item_path}.value", "invalid-type", "expected a string, boolean, or integer")

    def _validate_rules(self) -> None:
        group: set[str] = set()
        for index, raw in enumerate(self.array(self.root.get("rules"), "$.rules")):
            path = f"$.rules[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"condition", "id", "outcome", "rationale"})
            self.register(item.get("id"), f"{path}.id", group)
            for field in ("condition", "outcome", "rationale"):
                self.text(item.get(field), f"{path}.{field}")

    def _validate_patches(self) -> None:
        required = {
            "affected_refs", "after_digest", "after_path", "author", "base_digest",
            "before_digest", "before_path", "file", "id", "kind", "limitations",
            "semantic_delta", "symbol_or_span",
        }
        for index, raw in enumerate(self.array(self.root.get("patches"), "$.patches")):
            path = f"$.patches[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required, {"additional_changes"})
            self.register(item.get("id"), f"{path}.id", self.patches)
            if item.get("kind") not in {"byte-diff", "no-change"}:
                self.issue(f"{path}.kind", "invalid-value", "unknown patch kind")
            for field in ("base_digest", "before_digest", "after_digest"):
                self._digest(item.get(field), f"{path}.{field}")
            for field in ("author", "file", "limitations", "semantic_delta", "symbol_or_span"):
                self.text(item.get(field), f"{path}.{field}")
            for ref_index, ref_id in enumerate(self.strings(item.get("affected_refs"), f"{path}.affected_refs")):
                if ref_id not in self.references:
                    self.issue(f"{path}.affected_refs[{ref_index}]", "unknown-reference", "reference is not defined")
            before = self._snippet(path, item, "before_path", "before_digest")
            after = self._snippet(path, item, "after_path", "after_digest")
            if item.get("kind") == "no-change" and before != after:
                self.issue(path, "patch-contradiction", "no-change patch has different bytes")
            if item.get("kind") == "byte-diff" and before == after:
                self.issue(path, "patch-contradiction", "byte-diff patch has identical bytes")
            if item.get("kind") == "byte-diff":
                self._validate_base_bytes(path, item, before)
            for change_index, raw_change in enumerate(self.array(item.get("additional_changes", []), f"{path}.additional_changes")):
                change_path = f"{path}.additional_changes[{change_index}]"
                change = self.obj(raw_change, change_path)
                self.keys(change, change_path, {"after_digest", "after_path", "base_digest", "before_digest", "before_path", "file"})
                for field in ("base_digest", "before_digest", "after_digest"):
                    self._digest(change.get(field), f"{change_path}.{field}")
                change_before = self._snippet(change_path, change, "before_path", "before_digest")
                change_after = self._snippet(change_path, change, "after_path", "after_digest")
                if change_before == change_after:
                    self.issue(change_path, "patch-contradiction", "additional byte-diff has identical bytes")
                self._validate_base_bytes(change_path, change, change_before)

    def _validate_base_bytes(self, path: str, item: JsonObject, before: bytes) -> None:
        file_name = self.text(item.get("file"), f"{path}.file")
        if file_name is None:
            return
        source = (self.bundle_dir / "../g1/sources/oss/b0" / file_name).resolve()
        try:
            source.relative_to(self.bundle_dir.parent.resolve())
            content = source.read_bytes()
        except (OSError, ValueError) as error:
            self.issue(f"{path}.file", "input-read-failed", str(error))
            return
        if item.get("base_digest") not in self.source_digests.get("B0", set()):
            self.issue(f"{path}.base_digest", "digest-mismatch", "base digest is absent from G1 B0")
        if before not in content:
            self.issue(f"{path}.before_path", "base-bytes-mismatch", "before bytes do not occur in fixed base source")

    def _snippet(self, path: str, item: JsonObject, path_key: str, digest_key: str) -> bytes:
        relative = self.text(item.get(path_key), f"{path}.{path_key}")
        if relative is None:
            return b""
        source = (self.bundle_dir / relative).resolve()
        try:
            source.relative_to(self.bundle_dir.resolve())
            content = source.read_bytes()
        except (OSError, ValueError) as error:
            self.issue(f"{path}.{path_key}", "input-read-failed", str(error))
            return b""
        actual = "sha256:" + hashlib.sha256(content).hexdigest()
        if item.get(digest_key) != actual:
            self.issue(f"{path}.{digest_key}", "digest-mismatch", f"expected {actual}")
        return content

    def _validate_checks(self) -> None:
        group: set[str] = set()
        required = {
            "coverage", "evidence_refs", "expected_property", "id", "input_cases",
            "limitations", "mode", "predicates", "subject_versions",
        }
        for index, raw in enumerate(self.array(self.root.get("checks"), "$.checks")):
            path = f"$.checks[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required, {"assertions"})
            self.register(item.get("id"), f"{path}.id", group)
            if item.get("mode") != "modeled":
                self.issue(f"{path}.mode", "unsupported-evidence-mode", "G2 has no executed checks")
            for field in ("coverage", "expected_property", "limitations"):
                self.text(item.get(field), f"{path}.{field}")
            self.strings(item.get("input_cases"), f"{path}.input_cases")
            for version_index, version in enumerate(self.strings(item.get("subject_versions"), f"{path}.subject_versions")):
                if version != "B0" and version not in self.patches:
                    self.issue(f"{path}.subject_versions[{version_index}]", "unknown-reference", "subject version is not defined")
            for predicate_index, predicate in enumerate(self.strings(item.get("predicates"), f"{path}.predicates")):
                if predicate not in PREDICATES:
                    self.issue(f"{path}.predicates[{predicate_index}]", "unsupported-predicate", "predicate is not supported")
            assertion_ids: set[str] = set()
            for assertion_index, raw_assertion in enumerate(self.array(item.get("assertions", []), f"{path}.assertions")):
                assertion_path = f"{path}.assertions[{assertion_index}]"
                assertion = self.obj(raw_assertion, assertion_path)
                self.keys(assertion, assertion_path, {"expected", "fact_id", "operator"})
                fact_id = self.text(assertion.get("fact_id"), f"{assertion_path}.fact_id")
                if fact_id is not None:
                    if fact_id not in self.semantic_fact_ids:
                        self.issue(f"{assertion_path}.fact_id", "unknown-reference", "semantic fact is not defined")
                    if fact_id in assertion_ids:
                        self.issue(f"{assertion_path}.fact_id", "duplicate-reference", "fact is asserted more than once")
                    assertion_ids.add(fact_id)
                if assertion.get("operator") != "equals":
                    self.issue(f"{assertion_path}.operator", "unsupported-operator", "only typed equality is supported")
                if type(assertion.get("expected")) is not bool:
                    self.issue(f"{assertion_path}.expected", "invalid-type", "expected a boolean")
            for ref_index, ref_id in enumerate(self.strings(item.get("evidence_refs"), f"{path}.evidence_refs")):
                if ref_id not in self.references:
                    self.issue(f"{path}.evidence_refs[{ref_index}]", "unknown-reference", "reference is not defined")

    def _validate_semantic_model(self) -> None:
        if "semantic_model" not in self.root:
            return
        model = self.obj(self.root["semantic_model"], "$.semantic_model")
        self.keys(model, "$.semantic_model", {"facts", "version"})
        if self.text(model.get("version"), "$.semantic_model.version") != "source-facts-1":
            self.issue("$.semantic_model.version", "unsupported-version", "expected 'source-facts-1'")
        known_b0_paths = self._known_b0_paths()
        self.semantic_fact_ids = set()
        for index, raw in enumerate(self.array(model.get("facts"), "$.semantic_model.facts")):
            path = f"$.semantic_model.facts[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, {"file", "false_if_all", "id", "true_if_all"})
            fact_id = self.register(item.get("id"), f"{path}.id", self.semantic_fact_ids)
            file_name = self.text(item.get("file"), f"{path}.file")
            if file_name is not None and file_name not in known_b0_paths:
                self.issue(f"{path}.file", "unknown-reference", "fact file is not a fixed B0 workspace file")
            true_markers = self.strings(item.get("true_if_all"), f"{path}.true_if_all")
            false_markers = self.strings(item.get("false_if_all"), f"{path}.false_if_all")
            if not true_markers and not false_markers:
                self.issue(path, "missing-semantic-evidence", "at least one source marker is required")
            if set(true_markers) & set(false_markers):
                self.issue(path, "contradictory-semantic-evidence", "true and false markers overlap")
            if fact_id is not None and not fact_id.startswith("SEM-"):
                self.issue(f"{path}.id", "invalid-id", "semantic fact IDs must start with SEM-")

    def _known_b0_paths(self) -> set[str]:
        for raw in self.array(self.root.get("source_manifest"), "$.source_manifest"):
            if not isinstance(raw, dict) or raw.get("id") != "B0":
                continue
            source_path = self.text(raw.get("manifest_path"), "$.source_manifest.B0.manifest_path")
            if source_path is None:
                return set()
            manifest_path = (self.bundle_dir / source_path).resolve()
            try:
                manifest_path.relative_to(self.bundle_dir.parent.resolve())
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                return set()
            source = next((entry for entry in manifest.get("sources", [])
                           if entry.get("id") == "B0"), None)
            if not isinstance(source, dict):
                return set()
            result: set[str] = set()
            for file in source.get("files", []):
                if not isinstance(file, dict) or not isinstance(file.get("path"), str):
                    continue
                file_path = file["path"]
                if file_path.startswith("raw/b0/"):
                    result.add(file_path.removeprefix("raw/b0/").removesuffix(".b64"))
            return result
        return set()

    def _validate_actor_view(self) -> None:
        view = self.obj(self.root.get("actor_view"), "$.actor_view")
        self.keys(view, "$.actor_view", {"candidate_labels", "initial_claim_ids"})
        labels = self.obj(view.get("candidate_labels"), "$.actor_view.candidate_labels")
        if set(labels) != self.candidates:
            self.issue("$.actor_view.candidate_labels", "reference-set-mismatch", "must label every candidate exactly once")
        for candidate_id, label in labels.items():
            self.text(label, f"$.actor_view.candidate_labels.{candidate_id}")
        claims_by_id = {item.get("id"): item for item in self.root.get("world_claims", []) if isinstance(item, dict)}
        actor_claims = self.strings(view.get("initial_claim_ids"), "$.actor_view.initial_claim_ids")
        profile = self.root.get("participant_profile")
        profile_claims = profile.get("initial_claim_ids") if isinstance(profile, dict) else None
        if actor_claims != profile_claims:
            self.issue("$.actor_view.initial_claim_ids", "view-profile-mismatch", "actor view must match the participant profile")
        for index, claim_id in enumerate(actor_claims):
            claim = claims_by_id.get(claim_id)
            if claim is None:
                self.issue(f"$.actor_view.initial_claim_ids[{index}]", "unknown-reference", "claim is not defined")
            elif claim.get("classification") == "administrative":
                self.issue(f"$.actor_view.initial_claim_ids[{index}]", "visibility-conflict", "administrative claim leaks into actor view")

    def _validate_history(self) -> None:
        history = self.obj(self.root.get("extraction_history"), "$.extraction_history")
        required = {"input_revision", "method", "output_digest", "output_path", "review_result", "reviewer"}
        self.keys(history, "$.extraction_history", required)
        for field in required - {"output_digest", "output_path"}:
            self.text(history.get(field), f"$.extraction_history.{field}")
        self._digest(history.get("output_digest"), "$.extraction_history.output_digest")
        content = self._snippet("$.extraction_history", history, "output_path", "output_digest")
        if not content:
            self.issue("$.extraction_history.output_path", "invalid-value", "review record must not be empty")

    def build(self) -> ScenarioBundle:
        canonical = json.dumps(self.root, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        labels = self.root["actor_view"]["candidate_labels"]
        return ScenarioBundle(
            schema_version=self.root["schema_version"], exercise_id=self.root["exercise_id"],
            candidate_ids=tuple(item["id"] for item in self.root["candidates"]),
            rule_ids=tuple(item["id"] for item in self.root["rules"]),
            patch_ids=tuple(item["id"] for item in self.root["patches"]),
            check_ids=tuple(item["id"] for item in self.root["checks"]),
            actor_view=tuple((key, labels[key]) for key in sorted(labels)),
            content_id="sha256:" + hashlib.sha256(canonical).hexdigest(),
        )
