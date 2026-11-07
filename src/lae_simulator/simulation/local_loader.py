"""Validated G1/G2 input conversion into typed G3 runtime data."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from lae_simulator.provenance import verify_provenance_bundle
from lae_simulator.simulation.local_model import (
    LocalCandidate,
    LocalCheck,
    LocalClaim,
    LocalDocument,
    LocalExpression,
    LocalPatch,
    LocalPatchChange,
    LocalReference,
    ScenarioExecution,
    SemanticFactRule,
    SemanticPredicate,
    WorkspaceFile,
    _digest,
    mark_scenario_verified,
)
from lae_simulator.world.collaboration import collaboration_scopes, load_collaboration
from lae_simulator.world.errors import ValidationIssue, WorldValidationError
from lae_simulator.world.scenario import load_scenario_bundle
from lae_simulator.world.timing import load_timing


def _normalized_source_content(root: Path, record: dict[str, Any]) -> bytes:
    path = (root / record["path"]).resolve(strict=True)
    try:
        path.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise WorldValidationError([ValidationIssue(
            "$.source_manifest", "path-escape", "source escaped the verified G1 bundle"
        )]) from error
    raw = path.read_bytes()
    if record["encoding"] == "base64":
        content = base64.b64decode(b"".join(raw.split()), validate=True)
    elif record["encoding"] == "utf-8-drop-one-terminal-newline":
        raw.decode("utf-8")
        content = raw[:-1] if raw.endswith(b"\n") else raw
    else:
        raise WorldValidationError([ValidationIssue(
            "$.source_manifest", "unsupported-source-encoding", str(record["encoding"])
        )])
    if hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise WorldValidationError([ValidationIssue(
            "$.source_manifest", "digest-mismatch", "fixed source differs from verified digest"
        )])
    return content

def load_scenario_execution(path: str | Path) -> ScenarioExecution:
    """Create typed run-time definitions only after G2 and G1 validation."""
    scenario_path = Path(path)
    bundle = load_scenario_bundle(scenario_path)
    try:
        verify_provenance_bundle(scenario_path.parent.parent / "g1" / "manifest.json")
        data = json.loads(scenario_path.read_text(encoding="utf-8"))
        g1_root = scenario_path.parent.parent / "g1"
        manifest = json.loads((g1_root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorldValidationError([ValidationIssue("$", "scenario-read-failed", str(error))]) from error
    source_records = {item["id"]: item for item in manifest["sources"]}
    canonical = json.dumps(data, allow_nan=False, ensure_ascii=False,
                           separators=(",", ":"), sort_keys=True).encode("utf-8")
    if "sha256:" + hashlib.sha256(canonical).hexdigest() != bundle.content_id:
        raise WorldValidationError([ValidationIssue("$", "input-changed-after-validation",
                                                       "scenario changed between validation and loading")])

    def source_content(source_id: str, digest: str) -> bytes:
        record = source_records[source_id]
        item = next((f for f in record["files"] if "sha256:" + f["sha256"] == digest), None)
        if item is None:
            raise ValueError(f"digest {digest} is not part of source {source_id}")
        return _normalized_source_content(g1_root, item)

    docs = tuple(
        LocalDocument(
            id=item["id"], source_id=item["source_id"], digest=item["digest"],
            source_classification=source_records[item["source_id"]]["classification"],
            classification=item["classification"], availability=item["availability"],
            content=(source_content(item["source_id"], item["digest"]).decode("utf-8")
                     if item["availability"] == "available"
                     and item["classification"] != "administrative"
                     and source_records[item["source_id"]]["classification"] != "audit_only_comment"
                     else None),
        ) for item in data["documents"]
    )
    refs = tuple(LocalReference(
        id=item["id"], source_id=item["source_id"],
        source_classification=source_records[item["source_id"]]["classification"],
        relation=item["relation"],
        coverage=item["coverage"],
        target_id=item.get("target_id"), evidence=item["evidence"],
    ) for item in data["references"])
    claims = tuple(LocalClaim(
        id=item["id"], statement=item["statement"],
        classification=item["classification"], source_ids=tuple(item["source_ids"]),
    ) for item in data["world_claims"])
    permissions = tuple(sorted(
        (item["resource_id"], item["action"])
        for item in data["participant_profile"]["permissions"]
    ))
    workspace_resources = tuple(sorted(
        resource_id for resource_id, action in permissions if action == "virtual-edit"
    ))
    workspace_resource_id = workspace_resources[0] if len(workspace_resources) == 1 else None
    candidates = tuple(LocalCandidate(
        id=item["id"], label=data["actor_view"]["candidate_labels"][item["id"]],
        goal=item["goal"], operation=item["operation"],
        target_refs=tuple(item["target_refs"]), evidence_refs=tuple(item["evidence_refs"]),
        permission=next((
            ((workspace_resource_id or "workspace") if expr["field"] == "permission.workspace"
             else expr["field"].split(".", 1)[1],
             "virtual-edit" if expr["field"] == "permission.workspace" and expr["value"] == "edit"
             else str(expr["value"]))
            for expr in item["preconditions"] if expr["field"].startswith("permission.")
        ), None),
        required_claims=(),
        availability=tuple(LocalExpression(expr["field"], expr["operator"], expr["value"])
                           for expr in item["availability"]),
        preconditions=tuple(LocalExpression(expr["field"], expr["operator"], expr["value"])
                            for expr in item["preconditions"]),
        effects=tuple(LocalExpression(expr["field"], expr["operator"], expr["value"])
                      for expr in item["effects"]),
        expected_information=item["expected_information"], failure=item["failure"],
        next_goal_options=tuple(item["next_goal_options"]),
        duration_model_id=item["duration_model"],
        # Schema 1.0/1.1 inputs without this extension previously exposed all
        # patches to patch.apply; preserve that declared legacy interpretation.
        patch_ids=tuple(item.get("patch_ids", [patch["id"] for patch in data["patches"]]
                                  if item["operation"] == "patch.apply" else ())),
    ) for item in data["candidates"])
    g2_root = scenario_path.parent

    def patch_bytes(item: dict[str, Any], before_key: str, after_key: str,
                    file_key: str, base_key: str) -> LocalPatchChange:
        def read_snippet(key: str, digest_key: str) -> bytes:
            path = (g2_root / item[key]).resolve(strict=True)
            try:
                path.relative_to(g2_root.resolve(strict=True))
            except ValueError as error:
                raise WorldValidationError([ValidationIssue(
                    f"$.patches.{item.get('id')}.{key}", "path-escape",
                    "patch snippet escaped the validated G2 bundle",
                )]) from error
            content = cast(bytes, path.read_bytes())
            if "sha256:" + hashlib.sha256(content).hexdigest() != item[digest_key]:
                raise WorldValidationError([ValidationIssue(
                    f"$.patches.{item.get('id')}.{digest_key}", "digest-mismatch",
                    "patch snippet changed after validation",
                )])
            return content
        before = read_snippet(before_key, "before_digest")
        after = read_snippet(after_key, "after_digest")
        return LocalPatchChange(item[file_key], item[base_key], item["before_digest"],
                                item["after_digest"], before, after)

    patches_list: list[LocalPatch] = []
    for item in data["patches"]:
        changes = []
        if item["kind"] == "byte-diff":
            changes.append(patch_bytes(item, "before_path", "after_path", "file", "base_digest"))
            changes.extend(
                patch_bytes(change, "before_path", "after_path", "file", "base_digest")
                for change in item.get("additional_changes", [])
            )
        patches_list.append(LocalPatch(
            id=item["id"], kind=item["kind"], base_digest=item["base_digest"],
            author=item["author"], semantic_delta=item["semantic_delta"],
            affected_refs=tuple(item["affected_refs"]), changes=tuple(changes),
        ))
    checks = tuple(LocalCheck(
        id=item["id"], input_cases=tuple(item["input_cases"]),
        subject_versions=tuple(item["subject_versions"]), coverage=item["coverage"],
        predicates=tuple(item["predicates"]), evidence_refs=tuple(item["evidence_refs"]),
        mode=item["mode"], limitations=item["limitations"],
        assertions=tuple(SemanticPredicate(
            fact_id=assertion["fact_id"], operator=assertion["operator"],
            expected=assertion["expected"],
        ) for assertion in item.get("assertions", [])),
    ) for item in data["checks"])
    semantic_fact_rules = tuple(SemanticFactRule(
        id=item["id"], file=item["file"],
        true_if_all=tuple(value.encode("utf-8") for value in item["true_if_all"]),
        false_if_all=tuple(value.encode("utf-8") for value in item["false_if_all"]),
    ) for item in data.get("semantic_model", {}).get("facts", []))
    audit_reference_ids = {
        item.id for item in refs if item.source_classification == "audit_only_comment"
    }
    if any(reference_id in audit_reference_ids for item in checks for reference_id in item.evidence_refs):
        raise WorldValidationError([ValidationIssue(
            "$.checks.evidence_refs", "visibility-conflict",
            "modeled checks cannot cite audit-only references",
        )])
    workspace: list[WorkspaceFile] = []
    for record in source_records["B0"]["files"]:
        relative = record["path"]
        if not relative.startswith("raw/b0/"):
            continue
        content = _normalized_source_content(g1_root, record)
        target = relative.removeprefix("raw/b0/")
        if target.endswith(".b64"):
            target = target[:-4]
        elif target.endswith("/shared.b64"):
            target = target[:-4] + ".ts"
        workspace.append(WorkspaceFile(target, content, _digest(content)))
    # The patch fixture's base digest identifies the raw frozen artifact. Store
    # it alongside each decoded file to compare the declared base precisely.
    digest_by_target = {}
    for record in source_records["B0"]["files"]:
        target = record["path"].removeprefix("raw/b0/")
        target = target.removesuffix(".b64")
        digest_by_target[target] = "sha256:" + record["sha256"]
    workspace = [replace(item, digest=digest_by_target.get(item.path, item.digest)) for item in workspace]
    execution = ScenarioExecution(
        schema_version=bundle.schema_version, exercise_id=bundle.exercise_id,
        content_id=bundle.content_id, canonical_bytes=canonical,
        source_revisions=tuple((item["id"], item["revision"], item["digest"])
                               for item in data["source_manifest"]),
        source_classifications=tuple(sorted((item["id"], item["classification"])
                                             for item in manifest["sources"])),
        actor_id=data["participant_profile"]["actor_id"],
        ai_allowed=data["participant_profile"]["ai"]["allowed"],
        ai_can_edit=data["participant_profile"]["ai"]["can_edit"],
        initial_claim_ids=tuple(data["participant_profile"]["initial_claim_ids"]),
        operation_capabilities=tuple(data["participant_profile"]["operation_capabilities"]),
        permissions=permissions, workspace_resource_id=workspace_resource_id,
        claims=claims, documents=docs, references=refs,
        candidates=candidates, patches=tuple(patches_list), checks=checks,
        semantic_fact_rules=semantic_fact_rules,
        administrative_claim_ids=tuple(
            item.id for item in claims if item.classification == "administrative"
        ),
        base_files=tuple(sorted(workspace, key=lambda item: item.path)),
        timing=(load_timing(data["timing"], {item.duration_model_id for item in candidates})
                if "timing" in data else None),
        collaboration=(load_collaboration(data["collaboration"], *collaboration_scopes(
            data, {item['id']: item['classification'] for item in manifest['sources']}),
            {item.id for item in patches_list}) if "collaboration" in data else None),
    )
    return mark_scenario_verified(execution)


