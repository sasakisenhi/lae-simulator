"""Scenario 1.4.0 fixed search-scope and Workspace-reference validation."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lae_simulator.world.errors import ValidationIssue, WorldValidationError


@dataclass(frozen=True)
class WorkspaceReference:
    reference_id: str
    source_id: str
    path: str
    ranges: tuple[tuple[int, int], ...]


def normalize_search_paths(profile: object, workspace_paths: Sequence[str]) -> tuple[str, ...] | None:
    """Return canonical sorted paths for an explicitly supplied profile."""
    issues: list[ValidationIssue] = []
    if not isinstance(profile, dict):
        raise WorldValidationError([ValidationIssue("$.search_profile", "invalid-type", "expected an object")])
    for key in sorted(profile.keys() - {"paths"}):
        issues.append(ValidationIssue(f"$.search_profile.{key}", "unsupported-field", "field is not supported"))
    if "paths" not in profile:
        issues.append(ValidationIssue("$.search_profile.paths", "missing-field", "required field is missing"))
        raise WorldValidationError(issues)
    paths = profile["paths"]
    if not isinstance(paths, list):
        raise WorldValidationError([ValidationIssue("$.search_profile.paths", "invalid-type", "expected an array")])
    if not paths:
        issues.append(ValidationIssue("$.search_profile.paths", "invalid-value", "paths must not be empty"))
    available = set(workspace_paths)
    result: list[str] = []
    for index, path in enumerate(paths):
        issue_path = f"$.search_profile.paths[{index}]"
        if not isinstance(path, str):
            issues.append(ValidationIssue(issue_path, "invalid-type", "expected a string"))
            continue
        if (not path or "\\" in path or path.startswith("/") or "*" in path or "?" in path
                or "[" in path or "]" in path or posixpath.normpath(path) != path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            issues.append(ValidationIssue(issue_path, "invalid-path", "expected a normalized relative POSIX Workspace path"))
            continue
        if path not in available:
            issues.append(ValidationIssue(issue_path, "unknown-workspace-path", "path is absent from the verified Workspace"))
        result.append(path)
    if len(result) != len(set(result)):
        issues.append(ValidationIssue("$.search_profile.paths", "duplicate-path", "paths contains a duplicate"))
    if issues:
        raise WorldValidationError(issues)
    return tuple(sorted(result))


_RANGE = re.compile(r"(?:(?P<path>[^,:]+):)?(?P<start>[1-9][0-9]*)(?:-(?P<end>[1-9][0-9]*))?\Z")


def resolve_workspace_references(
    references: Sequence[Mapping[str, object]],
    workspace: Mapping[str, bytes],
) -> tuple[WorkspaceReference, ...]:
    """Resolve B0 recorded-reference evidence to unique paths and bounded lines."""
    issues: list[ValidationIssue] = []
    resolved: list[WorkspaceReference] = []
    for index, reference in enumerate(references):
        if reference.get("source_id") != "B0" or reference.get("coverage") != "recorded":
            continue
        ref_id = reference.get("id")
        base = f"$.references[{index}].evidence"
        evidence = reference.get("evidence")
        if not isinstance(evidence, str) or not isinstance(ref_id, str):
            continue  # Core reference validation reports malformed values.
        pieces = evidence.split(",")
        current_path: str | None = None
        bound_path: str | None = None
        ranges: list[tuple[int, int]] = []
        for piece in pieces:
            token = piece.strip()
            match = _RANGE.fullmatch(token)
            if match is None:
                issues.append(ValidationIssue(base, "invalid-line-range", "expected file:line or file:first-last ranges"))
                continue
            named_path = match.group("path")
            if named_path is not None:
                if "/" in named_path:
                    candidates = [named_path] if named_path in workspace else []
                else:
                    candidates = [path for path in workspace if path.rsplit("/", 1)[-1] == named_path]
                if len(candidates) != 1:
                    code = "unknown-workspace-reference" if not candidates else "ambiguous-workspace-reference"
                    issues.append(ValidationIssue(base, code, "evidence path must resolve uniquely in its source Workspace"))
                    current_path = None
                else:
                    candidate_path = candidates[0]
                    if bound_path is not None and candidate_path != bound_path:
                        issues.append(ValidationIssue(
                            base, "multiple-workspace-reference-paths",
                            "a recorded Workspace reference must identify exactly one file; "
                            "ranges from different files are not supported",
                        ))
                        continue
                    bound_path = candidate_path
                    current_path = candidate_path
            if current_path is None:
                if named_path is None:
                    issues.append(ValidationIssue(base, "missing-reference-path", "range without a path has no preceding path"))
                continue
            start = int(match.group("start"))
            end = int(match.group("end") or match.group("start"))
            if end < start:
                issues.append(ValidationIssue(base, "invalid-line-range", "range end precedes its start"))
                continue
            try:
                line_count = len(workspace[current_path].splitlines())
            except KeyError:
                line_count = 0
            if end > line_count:
                issues.append(ValidationIssue(base, "line-range-out-of-bounds", "evidence line range exceeds Workspace file"))
                continue
            ranges.append((start, end))
        if current_path is not None and ranges:
            resolved.append(WorkspaceReference(ref_id, "B0", current_path, tuple(ranges)))
    if issues:
        raise WorldValidationError(issues)
    return tuple(sorted(resolved, key=lambda item: item.reference_id))
