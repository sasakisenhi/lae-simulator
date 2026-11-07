"""Deterministic candidate selection from the actor-visible world contract."""

from __future__ import annotations

from lae_simulator.world.model import Candidate, WorldDefinition


def _resource_version(world: WorldDefinition, resource_id: str) -> str | None:
    if world.issue.id == resource_id:
        return world.issue.version
    document = next((item for item in world.documents if item.id == resource_id), None)
    return None if document is None else document.version


def candidate_is_available(
    world: WorldDefinition,
    candidate: Candidate,
    knowledge_ids: tuple[str, ...],
) -> bool:
    actor = next((item for item in world.actors if item.id == candidate.actor_id), None)
    tool = next((item for item in world.tools if item.id == candidate.tool_id), None)
    if actor is None or tool is None:
        return False
    if not set(candidate.required_information).issubset(knowledge_ids):
        return False
    if candidate.tool_id not in actor.tool_ids:
        return False
    if candidate.operation_kind not in tool.operations:
        return False
    permission = next(
        (item for item in actor.permissions if item.resource_id == candidate.target_id),
        None,
    )
    if permission is None or not candidate.required_permissions.issubset(permission.actions):
        return False
    if _resource_version(world, candidate.target_id) != candidate.required_version:
        return False
    return all(
        world.access_outcome(candidate.actor_id, resource_id) is outcome
        for resource_id, outcome in candidate.required_access
    )


def select_candidate(
    world: WorldDefinition,
    knowledge_ids: tuple[str, ...],
    completed_candidate_ids: tuple[str, ...],
) -> Candidate | None:
    actor = world.actors[0]
    policy = next(item for item in world.policies if item.actor_id == actor.id)
    candidates = {item.id: item for item in world.candidates}
    completed = set(completed_candidate_ids)
    for candidate_id in policy.candidate_priority:
        candidate = candidates[candidate_id]
        if candidate_id not in completed and candidate_is_available(
            world, candidate, knowledge_ids
        ):
            return candidate
    return None
