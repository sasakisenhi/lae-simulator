"""Resource accounting derived from canonical task/interval state, without a clock."""

from __future__ import annotations

from lae_simulator.simulation.collaboration_model import WorkInterval, account_time
from lae_simulator.simulation.local_model import (
    LocalEvent,
    LocalEventKind,
    LocalState,
    ScenarioExecution,
)


def resource_intervals(
    execution: ScenarioExecution, state: LocalState
) -> tuple[WorkInterval, ...]:
    """Close open intervals at the observed tick for reporting, never mutate history."""
    result = state.collaboration.intervals
    work = state.collaboration.human_task
    if work is not None and work.status == "active":
        result += (
            WorkInterval(
                state.actor_id,
                work.candidate_id,
                work.generation,
                work.start_tick,
                state.logical_time,
                "resume" if work.resumed else "active",
            ),
        )
    if (
        state.collaboration.waiting_for is not None
        and state.collaboration.waiting_since is not None
    ):
        request_id, generation = state.collaboration.waiting_for
        result += (
            WorkInterval(
                state.actor_id,
                request_id,
                generation,
                state.collaboration.waiting_since,
                state.logical_time,
                "wait",
            ),
        )
    if execution.collaboration is not None:
        rules = {row.id: row for row in execution.collaboration.rules}
        peers = {row.id: row for row in execution.collaboration.collaborators}
        for request in state.collaboration.requests:
            peer = peers[rules[request.rule_id].collaborator_id]
            if peer.kind == "ai" and request.executing:
                result += (
                    WorkInterval(
                        f"{peer.id}:{request.id}:g{request.generation}",
                        request.id,
                        request.generation,
                        request.requested_tick,
                        state.logical_time,
                        "active",
                    ),
                )
    return result


def human_time(execution: ScenarioExecution, state: LocalState) -> tuple[int, int, int]:
    return account_time(resource_intervals(execution, state), state.actor_id)


def activity_transitions(
    events: tuple[LocalEvent, ...],
) -> tuple[tuple[str, str, str | None, str | None], ...]:
    """Keep screen changes distinct from task/context switches; assign no penalty."""
    view: str | None = None
    task: str | None = None
    rows: list[tuple[str, str, str | None, str | None]] = []
    for event in events:
        if (
            event.kind is LocalEventKind.EVENT_SCHEDULED
            and event.candidate_id is not None
            and event.candidate_id != task
        ):
            rows.append((event.id, "task", task, event.candidate_id))
            task = event.candidate_id
        if event.kind in {
            LocalEventKind.DOCUMENT_READ,
            LocalEventKind.NAVIGATE,
            LocalEventKind.SEARCH,
        }:
            target = (
                event.target_id if event.kind is not LocalEventKind.SEARCH else "search"
            )
            if target != view:
                rows.append((event.id, "view", view, target))
                view = target
    return tuple(rows)
