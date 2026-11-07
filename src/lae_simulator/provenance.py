"""Offline verification for fixed teaching-material provenance bundles."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

JsonObject = dict[str, Any]
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HEX_GIT = re.compile(r"[0-9a-f]{40}\Z")
_SEMVER = re.compile(r"(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*)){2}\Z")
_RFC3339 = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_BASE64_WHITESPACE = b" \t\r\n"
_TOP_LEVEL_KEYS = frozenset(
    {
        "fixture_id",
        "retrieved_at",
        "schema_version",
        "sources",
        "synthetic_assumptions",
        "transformations",
    }
)
_SOURCE_KEYS = frozenset(
    {
        "classification",
        "excluded",
        "files",
        "id",
        "license",
        "package_version",
        "published_at",
        "revision",
        "source",
    }
)
_FILE_KEYS = frozenset(
    {
        "drive_file_id",
        "encoding",
        "git_blob",
        "link_target",
        "mode",
        "path",
        "reference_id",
        "sha256",
    }
)
_REFERENCE_KEYS = frozenset({"id", "kind", "source_id", "target"})
_CLASSIFICATIONS = frozenset(
    {"audit_only_comment", "fictional_company_draft", "real_oss", "real_oss_issue"}
)


@dataclass(frozen=True)
class ProvenanceIssue:
    code: str
    location: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "location": self.location, "message": self.message}


class ProvenanceValidationError(ValueError):
    def __init__(self, issues: tuple[ProvenanceIssue, ...]) -> None:
        self.issues = issues
        super().__init__("fixed-material provenance validation failed")


class _DuplicateKeyError(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _load_json(path: Path, location: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
        raise ProvenanceValidationError(
            (ProvenanceIssue("invalid-json", location, str(error)),)
        ) from error


def _git_blob_id(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def _text(value: object, issues: list[ProvenanceIssue], location: str) -> str | None:
    if not isinstance(value, str) or not value:
        issues.append(ProvenanceIssue("invalid-type", location, "non-empty string required"))
        return None
    return value


def _keys(
    value: JsonObject,
    issues: list[ProvenanceIssue],
    location: str,
    *,
    required: frozenset[str],
    allowed: frozenset[str],
) -> None:
    for key in sorted(required - value.keys()):
        issues.append(ProvenanceIssue("missing-field", f"{location}.{key}", "required"))
    for key in sorted(value.keys() - allowed):
        issues.append(ProvenanceIssue("unknown-field", f"{location}.{key}", "not allowed"))


def _rfc3339(value: object, issues: list[ProvenanceIssue], location: str) -> None:
    text = _text(value, issues, location)
    if text is None:
        return
    if _RFC3339.fullmatch(text) is None:
        issues.append(ProvenanceIssue("invalid-datetime", location, "RFC 3339 timestamp with offset required"))
        return
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        issues.append(ProvenanceIssue("invalid-datetime", location, "RFC 3339 timestamp with offset required"))


def _calendar_date(value: object, issues: list[ProvenanceIssue], location: str) -> None:
    text = _text(value, issues, location)
    if text is None:
        return
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None or len(text) != 10:
        issues.append(ProvenanceIssue("invalid-date", location, "YYYY-MM-DD required"))


def _bundle_file(
    root: Path,
    value: object,
    issues: list[ProvenanceIssue],
    location: str,
) -> tuple[Path | None, str | None]:
    relative = _text(value, issues, location)
    if relative is None:
        return None, None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        issues.append(ProvenanceIssue("invalid-path", location, "path must stay within the bundle"))
        return None, relative
    candidate = root
    resolved = root
    for part in pure.parts:
        candidate /= part
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except FileNotFoundError as error:
            issues.append(ProvenanceIssue("missing-file", location, str(error)))
            return None, relative
        except (OSError, RuntimeError) as error:
            issues.append(ProvenanceIssue("invalid-path", location, str(error)))
            return None, relative
        except ValueError:
            issues.append(ProvenanceIssue("path-outside-bundle", location, relative))
            return None, relative
    if not resolved.is_file():
        issues.append(ProvenanceIssue("invalid-path", location, "path must resolve to a regular file"))
        return None, relative
    return resolved, relative


def _decode_content(
    stored: bytes,
    encoding: object,
    issues: list[ProvenanceIssue],
    location: str,
) -> bytes | None:
    if encoding == "base64":
        normalized = stored.translate(None, _BASE64_WHITESPACE)
        try:
            return base64.b64decode(normalized, validate=True)
        except binascii.Error as error:
            issues.append(ProvenanceIssue("invalid-base64", location, str(error)))
            return None
    if encoding == "utf-8-drop-one-terminal-newline":
        try:
            stored.decode("utf-8")
        except UnicodeError as error:
            issues.append(ProvenanceIssue("invalid-content", location, str(error)))
            return None
        return stored[:-1] if stored.endswith(b"\n") else stored
    issues.append(ProvenanceIssue("invalid-encoding", f"{location}.encoding", str(encoding)))
    return None


def _validate_license(
    value: object,
    files: set[str],
    issues: list[ProvenanceIssue],
    location: str,
) -> None:
    if not isinstance(value, dict):
        issues.append(ProvenanceIssue("invalid-type", location, "object required"))
        return
    _keys(
        value,
        issues,
        location,
        required=frozenset({"spdx"}),
        allowed=frozenset({"file", "spdx", "terms"}),
    )
    spdx = _text(value.get("spdx"), issues, f"{location}.spdx")
    file_value = value.get("file")
    terms_value = value.get("terms")
    if file_value is None and terms_value is None:
        issues.append(ProvenanceIssue("missing-field", location, "file or terms required"))
    if file_value is not None:
        file_text = _text(file_value, issues, f"{location}.file")
        if file_text is not None and file_text not in files:
            issues.append(ProvenanceIssue("unknown-license-file", f"{location}.file", file_text))
    if terms_value is not None:
        _text(terms_value, issues, f"{location}.terms")
    if spdx == "NOASSERTION" and terms_value is None:
        issues.append(ProvenanceIssue("missing-field", f"{location}.terms", "required for NOASSERTION"))


def _validate_named_text_list(
    value: object,
    issues: list[ProvenanceIssue],
    location: str,
    allowed: frozenset[str],
) -> None:
    if not isinstance(value, list) or not value:
        issues.append(ProvenanceIssue("invalid-type", location, "non-empty list required"))
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_location = f"{location}[{index}]"
        if not isinstance(item, dict):
            issues.append(ProvenanceIssue("invalid-type", item_location, "object required"))
            continue
        _keys(item, issues, item_location, required=allowed, allowed=allowed)
        item_id = _text(item.get("id"), issues, f"{item_location}.id")
        if item_id is not None:
            if item_id in seen:
                issues.append(ProvenanceIssue("duplicate-id", f"{item_location}.id", item_id))
            seen.add(item_id)
        for key in allowed - {"id"}:
            _text(item.get(key), issues, f"{item_location}.{key}")


def _validate_file(
    root: Path,
    source_class: str | None,
    entry: object,
    entry_loc: str,
    seen_paths: set[str],
    seen_reference_ids: set[str],
    seen_drive_ids: set[str],
    issues: list[ProvenanceIssue],
) -> tuple[str | None, bool]:
    if not isinstance(entry, dict):
        issues.append(ProvenanceIssue("invalid-type", entry_loc, "object required"))
        return None, False
    _keys(
        entry,
        issues,
        entry_loc,
        required=frozenset({"encoding", "path", "sha256"}),
        allowed=_FILE_KEYS,
    )
    file_path, relative = _bundle_file(root, entry.get("path"), issues, f"{entry_loc}.path")
    if relative is not None:
        if relative in seen_paths:
            issues.append(ProvenanceIssue("duplicate-path", f"{entry_loc}.path", relative))
        seen_paths.add(relative)
    digest = _text(entry.get("sha256"), issues, f"{entry_loc}.sha256")
    if digest is not None and _HEX_SHA256.fullmatch(digest) is None:
        issues.append(ProvenanceIssue("invalid-digest", f"{entry_loc}.sha256", "64 lowercase hex characters required"))
    git_blob = entry.get("git_blob")
    if git_blob is not None and (
        not isinstance(git_blob, str) or _HEX_GIT.fullmatch(git_blob) is None
    ):
        issues.append(ProvenanceIssue("invalid-git-blob", f"{entry_loc}.git_blob", "40 lowercase hex characters required"))
    if source_class == "fictional_company_draft":
        for key, seen in (("reference_id", seen_reference_ids), ("drive_file_id", seen_drive_ids)):
            value = _text(entry.get(key), issues, f"{entry_loc}.{key}")
            if value is not None:
                if value in seen:
                    issues.append(ProvenanceIssue(f"duplicate-{key.replace('_', '-')}", f"{entry_loc}.{key}", value))
                seen.add(value)
    elif "reference_id" in entry or "drive_file_id" in entry:
        issues.append(ProvenanceIssue("invalid-field", entry_loc, "Drive reference fields require fictional_company_draft"))
    if (
        source_class == "real_oss"
        and entry.get("encoding") != "base64"
        or source_class in {
            "audit_only_comment",
            "fictional_company_draft",
            "real_oss_issue",
        }
        and entry.get("encoding") != "utf-8-drop-one-terminal-newline"
    ):
        issues.append(
            ProvenanceIssue(
                "invalid-encoding",
                f"{entry_loc}.encoding",
                f"encoding does not match classification {source_class}",
            )
        )
    link_target = entry.get("link_target")
    if link_target is not None:
        _text(link_target, issues, f"{entry_loc}.link_target")
        if entry.get("mode") != "120000":
            issues.append(ProvenanceIssue("invalid-mode", f"{entry_loc}.mode", "link payload requires mode 120000"))
    elif "mode" in entry:
        issues.append(ProvenanceIssue("invalid-field", f"{entry_loc}.mode", "mode is only supported for link payloads"))
    if file_path is None:
        return relative, False
    try:
        stored = file_path.read_bytes()
    except OSError as error:
        issues.append(ProvenanceIssue("file-read-failed", f"{entry_loc}.path", str(error)))
        return relative, False
    content = _decode_content(stored, entry.get("encoding"), issues, entry_loc)
    if content is None:
        return relative, False
    if digest is not None and _HEX_SHA256.fullmatch(digest) is not None:
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != digest:
            issues.append(ProvenanceIssue("digest-mismatch", f"{entry_loc}.sha256", f"expected {digest}, got {actual_digest}"))
    if isinstance(git_blob, str) and _HEX_GIT.fullmatch(git_blob) is not None:
        actual_blob = _git_blob_id(content)
        if actual_blob != git_blob:
            issues.append(ProvenanceIssue("git-blob-mismatch", f"{entry_loc}.git_blob", f"expected {git_blob}, got {actual_blob}"))
    if isinstance(link_target, str):
        try:
            decoded_target = content.decode("utf-8")
        except UnicodeError as error:
            issues.append(ProvenanceIssue("invalid-link-target-content", entry_loc, str(error)))
        else:
            if decoded_target != link_target:
                issues.append(ProvenanceIssue("link-target-mismatch", f"{entry_loc}.link_target", link_target))
    return relative, True


def _validate_source(
    root: Path,
    source: object,
    source_loc: str,
    seen_ids: set[str],
    seen_paths: set[str],
    seen_reference_ids: set[str],
    seen_drive_ids: set[str],
    issues: list[ProvenanceIssue],
) -> tuple[str | None, int]:
    if not isinstance(source, dict):
        issues.append(ProvenanceIssue("invalid-type", source_loc, "object required"))
        return None, 0
    _keys(
        source,
        issues,
        source_loc,
        required=frozenset({"classification", "files", "id", "license", "revision", "source"}),
        allowed=_SOURCE_KEYS,
    )
    source_id = _text(source.get("id"), issues, f"{source_loc}.id")
    if source_id is not None:
        if source_id in seen_ids:
            issues.append(ProvenanceIssue("duplicate-id", f"{source_loc}.id", source_id))
        seen_ids.add(source_id)
    classification = _text(source.get("classification"), issues, f"{source_loc}.classification")
    if classification is not None and classification not in _CLASSIFICATIONS:
        issues.append(ProvenanceIssue("invalid-classification", f"{source_loc}.classification", classification))
    source_url = _text(source.get("source"), issues, f"{source_loc}.source")
    if source_url is not None and not source_url.startswith("https://"):
        issues.append(ProvenanceIssue("invalid-source", f"{source_loc}.source", "HTTPS URL required"))
    revision = _text(source.get("revision"), issues, f"{source_loc}.revision")
    if classification == "real_oss" and revision is not None and _HEX_GIT.fullmatch(revision) is None:
        issues.append(ProvenanceIssue("invalid-revision", f"{source_loc}.revision", "40-character commit SHA required"))
    if classification == "real_oss_issue" and revision is not None and re.fullmatch(r"issue:[1-9]\d*", revision) is None:
        issues.append(ProvenanceIssue("invalid-revision", f"{source_loc}.revision", "issue:<positive integer> required"))
    if classification == "audit_only_comment" and revision is not None and re.fullmatch(r"issue-comment:[1-9]\d*", revision) is None:
        issues.append(ProvenanceIssue("invalid-revision", f"{source_loc}.revision", "issue-comment:<positive integer> required"))
    if classification == "fictional_company_draft" and revision is not None and _SEMVER.fullmatch(revision) is None:
        issues.append(ProvenanceIssue("invalid-revision", f"{source_loc}.revision", "semantic version required"))
    if classification in {"real_oss_issue", "audit_only_comment"}:
        if "published_at" not in source:
            issues.append(ProvenanceIssue("missing-field", f"{source_loc}.published_at", "required"))
        else:
            _rfc3339(source.get("published_at"), issues, f"{source_loc}.published_at")
    elif classification == "fictional_company_draft":
        if "published_at" not in source:
            issues.append(ProvenanceIssue("missing-field", f"{source_loc}.published_at", "required"))
        else:
            _calendar_date(source.get("published_at"), issues, f"{source_loc}.published_at")
    elif "published_at" in source:
        _rfc3339(source.get("published_at"), issues, f"{source_loc}.published_at")
    if "package_version" in source:
        if classification != "real_oss":
            issues.append(
                ProvenanceIssue(
                    "invalid-field",
                    f"{source_loc}.package_version",
                    "only valid for real_oss",
                )
            )
        version = _text(source.get("package_version"), issues, f"{source_loc}.package_version")
        if version is not None and _SEMVER.fullmatch(version) is None:
            issues.append(ProvenanceIssue("invalid-version", f"{source_loc}.package_version", "semantic version required"))
    if "excluded" in source:
        excluded = source.get("excluded")
        if classification != "fictional_company_draft":
            issues.append(ProvenanceIssue("invalid-field", f"{source_loc}.excluded", "only valid for fictional_company_draft"))
        if (
            not isinstance(excluded, list)
            or not excluded
            or any(not isinstance(item, str) or not item for item in excluded)
        ):
            issues.append(ProvenanceIssue("invalid-type", f"{source_loc}.excluded", "non-empty string list required"))
        elif len(excluded) != len(set(excluded)):
            issues.append(ProvenanceIssue("duplicate-value", f"{source_loc}.excluded", "values must be unique"))
    files = source.get("files")
    if not isinstance(files, list) or not files:
        issues.append(ProvenanceIssue("invalid-type", f"{source_loc}.files", "non-empty list required"))
        files = []
    source_files: set[str] = set()
    verified = 0
    for file_index, entry in enumerate(files):
        relative, file_verified = _validate_file(
            root,
            classification,
            entry,
            f"{source_loc}.files[{file_index}]",
            seen_paths,
            seen_reference_ids,
            seen_drive_ids,
            issues,
        )
        if relative is not None:
            source_files.add(relative)
        verified += int(file_verified)
    _validate_license(source.get("license"), source_files, issues, f"{source_loc}.license")
    return source_id, verified


def _validate_reference_seed(
    root: Path,
    source_classes: dict[str, str],
    issues: list[ProvenanceIssue],
) -> int:
    seed_path = root / "reference-seed.json"
    try:
        seed_path = seed_path.resolve(strict=True)
        seed_path.relative_to(root)
    except FileNotFoundError as error:
        issues.append(ProvenanceIssue("missing-file", "reference-seed.json", str(error)))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        issues.append(ProvenanceIssue("invalid-path", "reference-seed.json", str(error)))
        return 0
    try:
        document = _load_json(seed_path, "reference-seed.json")
    except ProvenanceValidationError as error:
        issues.extend(error.issues)
        return 0
    if not isinstance(document, dict):
        issues.append(ProvenanceIssue("invalid-type", "$references", "object required"))
        return 0
    _keys(
        document,
        issues,
        "$references",
        required=frozenset({"references", "schema_version"}),
        allowed=frozenset({"references", "schema_version"}),
    )
    if document.get("schema_version") != "1.0.0":
        issues.append(ProvenanceIssue("unsupported-version", "$references.schema_version", "expected 1.0.0"))
    references = document.get("references")
    if not isinstance(references, list) or not references:
        issues.append(ProvenanceIssue("invalid-type", "$references.references", "non-empty list required"))
        return 0
    seen_ids: set[str] = set()
    for index, reference in enumerate(references):
        location = f"$references.references[{index}]"
        if not isinstance(reference, dict):
            issues.append(ProvenanceIssue("invalid-type", location, "object required"))
            continue
        _keys(reference, issues, location, required=_REFERENCE_KEYS, allowed=_REFERENCE_KEYS)
        reference_id = _text(reference.get("id"), issues, f"{location}.id")
        if reference_id is not None:
            if reference_id in seen_ids:
                issues.append(ProvenanceIssue("duplicate-reference", f"{location}.id", reference_id))
            seen_ids.add(reference_id)
        source_id = _text(reference.get("source_id"), issues, f"{location}.source_id")
        if source_id is not None and source_id not in source_classes:
            issues.append(ProvenanceIssue("unknown-source-reference", f"{location}.source_id", source_id))
        kind = _text(reference.get("kind"), issues, f"{location}.kind")
        if (
            source_id is not None
            and kind is not None
            and source_id in source_classes
            and kind != source_classes[source_id]
        ):
            issues.append(
                ProvenanceIssue(
                    "reference-classification-mismatch",
                    f"{location}.kind",
                    f"expected {source_classes[source_id]}, got {kind}",
                )
            )
        _text(reference.get("target"), issues, f"{location}.target")
    return len(references)


def verify_provenance_bundle(manifest_path: Path) -> dict[str, object]:
    """Verify a bundle without network access and return a stable summary."""
    try:
        root = manifest_path.parent.resolve(strict=True)
        resolved_manifest = manifest_path.resolve(strict=True)
        resolved_manifest.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise ProvenanceValidationError(
            (ProvenanceIssue("invalid-manifest-path", "$", str(error)),)
        ) from error
    document = _load_json(resolved_manifest, "$")
    if not isinstance(document, dict):
        raise ProvenanceValidationError(
            (ProvenanceIssue("invalid-type", "$", "manifest must be an object"),)
        )
    issues: list[ProvenanceIssue] = []
    _keys(
        document,
        issues,
        "$",
        required=_TOP_LEVEL_KEYS,
        allowed=_TOP_LEVEL_KEYS,
    )
    if document.get("schema_version") != "1.0.0":
        issues.append(ProvenanceIssue("unsupported-version", "$.schema_version", "expected 1.0.0"))
    fixture_id = _text(document.get("fixture_id"), issues, "$.fixture_id")
    _rfc3339(document.get("retrieved_at"), issues, "$.retrieved_at")
    _validate_named_text_list(
        document.get("synthetic_assumptions"),
        issues,
        "$.synthetic_assumptions",
        frozenset({"id", "text"}),
    )
    _validate_named_text_list(
        document.get("transformations"),
        issues,
        "$.transformations",
        frozenset({"id", "input", "method", "output"}),
    )
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        issues.append(ProvenanceIssue("invalid-type", "$.sources", "non-empty list required"))
        sources = []
    seen_ids: set[str] = set()
    source_classes: dict[str, str] = {}
    seen_paths: set[str] = set()
    seen_reference_ids: set[str] = set()
    seen_drive_ids: set[str] = set()
    verified = 0
    for source_index, source in enumerate(sources):
        source_id, source_verified = _validate_source(
            root,
            source,
            f"$.sources[{source_index}]",
            seen_ids,
            seen_paths,
            seen_reference_ids,
            seen_drive_ids,
            issues,
        )
        if (
            source_id is not None
            and isinstance(source, dict)
            and isinstance(source.get("classification"), str)
        ):
            source_classes[source_id] = source["classification"]
        verified += source_verified
    references_verified = _validate_reference_seed(root, source_classes, issues)
    if issues:
        raise ProvenanceValidationError(tuple(issues))
    return {
        "fixture_id": fixture_id,
        "files_verified": verified,
        "references_verified": references_verified,
        "sources_verified": len(sources),
        "status": "valid",
    }
