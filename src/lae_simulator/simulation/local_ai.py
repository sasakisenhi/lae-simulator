"""Pure version/permission checks for integrating a frozen AI overlay."""

from __future__ import annotations

from lae_simulator.simulation.collaboration_model import RequestState
from lae_simulator.simulation.local_model import (
    LocalPatch,
    LocalState,
    ScenarioExecution,
)
from lae_simulator.simulation.local_workspace import (
    WorkspaceConflict,
    WorkspaceMutation,
    apply_patch_workspace,
)


def integration_plan(
    execution: ScenarioExecution, state: LocalState, request: RequestState
) -> tuple[LocalPatch, WorkspaceMutation | None, str]:
    if execution.collaboration is None:
        raise ValueError("no collaboration definitions")
    rule = next(
        row for row in execution.collaboration.rules if row.id == request.rule_id
    )
    if rule.overlay_patch_id is None:
        raise ValueError("response contains no fixed overlay")
    patch = next(row for row in execution.patches if row.id == rule.overlay_patch_id)
    if (
        (not execution.ai_can_edit or rule.required_scope is not None)
        and not request.authorized
        or execution.workspace_resource_id is None
        or (execution.workspace_resource_id, "virtual-edit")
        not in execution.permissions
    ):
        return patch, None, "permission-denied"
    if request.base_version != state.workspace_version:
        return patch, None, "conflict"
    try:
        return (
            patch,
            apply_patch_workspace(state, patch, request.base_version),
            "integrated",
        )
    except WorkspaceConflict:
        return patch, None, "conflict"
