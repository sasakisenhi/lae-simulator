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
        self.references: set[str] = set()
        self.claims: set[str] = set()
        self.candidates: set[str] = set()
        self.patches: set[str] = set()

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
        self.keys(self.root, "$", required)
        if self.text(self.root.get("schema_version"), "$.schema_version") != "1.0.0":
            self.issue("$.schema_version", "unsupported-version", "expected '1.0.0'")
        self.text(self.root.get("exercise_id"), "$.exercise_id")
        self._validate_sources()
        self._validate_documents()
        self._validate_references()
        self._validate_claims()
        self._validate_context()
        self._validate_participant_profile()
        self._validate_candidates()
        self._validate_rules()
        self._validate_patches()
        self._validate_checks()
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

    def _validate_candidates(self) -> None:
        required = {
            "actor_visible_label", "availability", "duration_model", "effects", "evidence_refs",
            "expected_information", "failure", "goal", "id", "next_goal_options",
            "operation", "preconditions", "target_refs",
        }
        for index, raw in enumerate(self.array(self.root.get("candidates"), "$.candidates")):
            path = f"$.candidates[{index}]"
            item = self.obj(raw, path)
            self.keys(item, path, required)
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
            self.keys(item, path, required)
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
            for ref_index, ref_id in enumerate(self.strings(item.get("evidence_refs"), f"{path}.evidence_refs")):
                if ref_id not in self.references:
                    self.issue(f"{path}.evidence_refs[{ref_index}]", "unknown-reference", "reference is not defined")

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
