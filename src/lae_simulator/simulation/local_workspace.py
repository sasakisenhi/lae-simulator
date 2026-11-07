"""Pure Workspace byte transitions shared by command preparation and reduction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from lae_simulator.simulation.local_model import (
    LocalPatch,
    LocalState,
    WorkspaceFile,
    _digest,
    workspace_digest,
)


@dataclass(frozen=True)
class WorkspaceMutation:
    version: str
    files: tuple[WorkspaceFile, ...]


class WorkspaceConflict(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _match_line_endings(content: bytes, before: bytes, after: bytes) -> tuple[bytes, bytes]:
    if b"\r\n" in content and b"\r\n" not in before:
        return before.replace(b"\n", b"\r\n"), after.replace(b"\n", b"\r\n")
    return before, after


def apply_patch_workspace(state: LocalState, patch: LocalPatch,
                          input_version: str | None) -> WorkspaceMutation:
    if state.workspace_version not in state.workspace_versions:
        raise WorkspaceConflict("unknown-workspace-version", "workspace version is not known")
    if input_version != state.workspace_version:
        raise WorkspaceConflict("version-mismatch", "patch input version is stale")
    if patch.kind == "no-change":
        if state.workspace_version != "B0" or not any(
            item.digest == patch.base_digest for item in state.workspace_files
        ):
            raise WorkspaceConflict("base-digest-mismatch", "no-change patch does not match frozen workspace")
        return WorkspaceMutation(state.workspace_version, state.workspace_files)
    current = {item.path: item for item in state.workspace_files}
    updated = dict(current)
    for change in patch.changes:
        existing = current.get(change.file)
        if existing is None:
            raise WorkspaceConflict("missing-target", "patch target is not present in workspace")
        if existing.digest != change.base_digest and state.workspace_version == "B0":
            raise WorkspaceConflict("base-digest-mismatch", "target base digest differs")
        before, after = _match_line_endings(existing.content, change.before, change.after)
        if before not in existing.content:
            raise WorkspaceConflict("before-bytes-mismatch", "patch before bytes do not match")
        output = existing.content.replace(before, after, 1)
        updated[change.file] = WorkspaceFile(change.file, output, _digest(output))
    files = tuple(updated[path] for path in sorted(updated))
    material = (
        state.workspace_version + "\n" + patch.id + "\n" + workspace_digest(files)
    ).encode("utf-8")
    version = patch.id + ":" + hashlib.sha256(material).hexdigest()
    return WorkspaceMutation(version, files)


def revert_patch_workspace(state: LocalState, patch: LocalPatch,
                           patch_id: str, input_version: str | None) -> WorkspaceMutation:
    if not state.applied_patch_ids or state.applied_patch_ids[-1] != patch_id:
        raise WorkspaceConflict("revert-order", "only the most recent patch can be reverted")
    if input_version != state.workspace_version:
        raise WorkspaceConflict("stale-revert", "revert base version is stale")
    files = {item.path: item for item in state.workspace_files}
    for change in reversed(patch.changes):
        current = files.get(change.file)
        if current is None:
            raise WorkspaceConflict("missing-target", "revert target is not present")
        before, after = _match_line_endings(current.content, change.before, change.after)
        if after not in current.content:
            raise WorkspaceConflict("revert-content-mismatch", "applied bytes no longer match patch")
        content = current.content.replace(after, before, 1)
        files[change.file] = WorkspaceFile(change.file, content, _digest(content))
    ordered = tuple(files[path] for path in sorted(files))
    material = (
        state.workspace_version + "\nrevert\n" + patch_id + "\n" + workspace_digest(ordered)
    ).encode("utf-8")
    version = "revert-" + hashlib.sha256(material).hexdigest()[:16]
    return WorkspaceMutation(version, ordered)
