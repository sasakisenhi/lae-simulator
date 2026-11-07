"""Pure G5 request/notification validation within the existing local reducer."""

from __future__ import annotations

from dataclasses import replace
from typing import NoReturn

from lae_simulator.simulation.collaboration_model import (
    ArrivalPayload,
    RequestAction,
    RequestPayload,
    RequestState,
    ResponseArtifact,
    WorkInterval,
    bind_response,
    response_disposition,
    validate_response,
)
from lae_simulator.simulation.errors import HistoryValidationError
from lae_simulator.simulation.local_ai import integration_plan
from lae_simulator.simulation.local_model import (
    ClaimKnowledge,
    ClaimStatus,
    LocalEvent,
    LocalEventKind,
    LocalObservationRecord,
    LocalState,
    ScenarioExecution,
)
from lae_simulator.simulation.model import IntegrityIssue, ScheduledEvent
from lae_simulator.simulation.scheduler import reserve

COLLABORATION_KINDS = frozenset(
    {
        LocalEventKind.REQUESTED,
        LocalEventKind.RESPONSE_ARRIVED,
        LocalEventKind.NOTICE_DELIVERED,
        LocalEventKind.RESPONSE_OBSERVED,
        LocalEventKind.REQUEST_EXPIRED,
        LocalEventKind.WAIT_STARTED,
        LocalEventKind.WAIT_ENDED,
        LocalEventKind.NOTICE_ACKNOWLEDGED,
        LocalEventKind.APPROVAL_REQUESTED,
        LocalEventKind.AI_INTEGRATED,
        LocalEventKind.AI_DISCARDED,
        LocalEventKind.REQUEST_CANCELLED,
    }
)


def fail(event: LocalEvent, code: str, message: str) -> NoReturn:
    raise HistoryValidationError(IntegrityIssue(event.id, code, message))


def slot_payload(action: str, request: RequestState) -> str:
    return f"collab:{action}:{request.id}:{request.generation}"


def find_request(state: LocalState, payload: str) -> tuple[str, RequestState]:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "collab":
        raise ValueError("invalid collaboration reservation payload")
    generation = int(parts[3])
    request = next(
        (
            row
            for row in state.collaboration.requests
            if row.id == parts[2] and row.generation == generation
        ),
        None,
    )
    if request is None:
        raise ValueError("reservation refers to an unknown request generation")
    return parts[1], request


def obligations(
    state: LocalState,
    event: LocalEvent,
    request: RequestState,
    definitions: tuple[tuple[str, int, int], ...],
) -> tuple[ScheduledEvent, ...]:
    sequence = max(state.scheduler.used_sequences, default=0)
    return tuple(
        ScheduledEvent(
            tick
            + (
                1
                if tick == state.logical_time
                and state.scheduler.cursor is not None
                and priority < state.scheduler.cursor[1]
                else 0
            ),
            priority,
            sequence + index,
            f"AS-{request.id}-g{request.generation}-{action}",
            f"LEV-{event.order + index:06d}",
            slot_payload(action, request),
        )
        for index, (action, tick, priority) in enumerate(definitions, 1)
    )


def schedule_collaboration(
    execution: ScenarioExecution, state: LocalState, event: LocalEvent
) -> LocalState:
    cfg = execution.collaboration
    item = event.reservation
    expected = state.collaboration.reservation_obligations
    if (
        cfg is None
        or item is None
        or not expected
        or item != expected[0]
        or item.created_by_event_id != event.id
        or event.candidate_id is not None
        or event.caused_by != (state.collaboration.obligation_cause,)
        or event.duration_draw is not None
    ):
        fail(
            event,
            "async-reservation-mismatch",
            "reservation lacks the matching canonical obligation",
        )
    try:
        scheduler = reserve(state.scheduler, item, state.logical_time)
    except ValueError as error:
        fail(event, "invalid-async-reservation", str(error))
    remaining = expected[1:]
    return replace(
        state,
        scheduler=scheduler,
        collaboration=replace(
            state.collaboration,
            reservation_obligations=remaining,
            obligation_cause=state.collaboration.obligation_cause
            if remaining
            else None,
        ),
    )


def replace_request(state: LocalState, request: RequestState) -> LocalState:
    rows = tuple(
        request if (row.id, row.generation) == (request.id, request.generation) else row
        for row in state.collaboration.requests
    )
    return replace(state, collaboration=replace(state.collaboration, requests=rows))


def reduce_collaboration_event(
    execution: ScenarioExecution, state: LocalState, event: LocalEvent
) -> LocalState:
    cfg = execution.collaboration
    if cfg is None or execution.timing is None:
        fail(
            event,
            "missing-collaboration-definition",
            "G5 requires fixed collaboration and timing definitions",
        )
    payload = event.collaboration
    if isinstance(payload, (RequestPayload, RequestAction)) and (
        type(payload.generation) is not int
        or payload.generation < 1
        or not isinstance(payload.request_id, str)
        or not payload.request_id
    ):
        fail(
            event,
            "invalid-request-reference",
            "request reference requires a nonempty ID and positive integer generation",
        )
    if isinstance(payload, ArrivalPayload):
        if not isinstance(payload.artifact, ResponseArtifact):
            fail(
                event, "invalid-response-artifact", "arrival requires a typed artifact"
            )
        if (
            type(payload.artifact.generation) is not int
            or payload.artifact.generation < 1
        ):
            fail(
                event,
                "invalid-response-generation",
                "response generation must be a positive integer",
            )
    if event.kind in {LocalEventKind.REQUESTED, LocalEventKind.APPROVAL_REQUESTED}:
        if not isinstance(payload, RequestPayload):
            fail(event, "invalid-request-payload", "request requires a typed payload")
        rule = next((row for row in cfg.rules if row.id == payload.rule_id), None)
        if rule is None:
            fail(
                event,
                "unknown-response-rule",
                "request references an unknown fixed rule",
            )
        peer = next(row for row in cfg.collaborators if row.id == rule.collaborator_id)
        candidate = next(
            (row for row in execution.candidates if row.id == event.candidate_id), None
        )
        prior = next(
            (
                row
                for row in reversed(state.collaboration.requests)
                if row.id == payload.request_id
            ),
            None,
        )
        authorized = False
        dependency_parent = next(
            (
                row
                for row in reversed(state.collaboration.requests)
                if row.id == payload.parent_request_id
            ),
            None,
        )
        parent = dependency_parent
        if event.kind is LocalEventKind.APPROVAL_REQUESTED:
            if (
                parent is None
                or parent.observed_tick is None
                or parent.disposition != "approval-required"
                or parent.status != "responded"
                or payload.generation != parent.generation
                or payload.request_id != "REQ-" + event.id
                or candidate is not None
                or rule.operation != "approval.request"
                or event.caused_by != (parent.observed_event_id,)
                or payload.base_version != parent.base_version
            ):
                fail(
                    event,
                    "invalid-approval-request",
                    "approval requires an observed blocked task and its generation",
                )
            parent_rule = next(row for row in cfg.rules if row.id == parent.rule_id)
            if (
                rule.collaborator_id != parent_rule.approver_id
                or rule.required_scope != parent_rule.required_scope
                or any(
                    row.parent_request_id == parent.id
                    and row.generation == parent.generation
                    for row in state.collaboration.requests
                )
            ):
                fail(
                    event,
                    "approval-scope-mismatch",
                    "approval must match declared approver, scope and one dependency",
                )
        else:
            if (
                candidate is None
                or candidate.operation != rule.operation
                or payload.base_version != state.workspace_version
                or event.input_version != state.workspace_version
            ):
                fail(
                    event,
                    "request-binding",
                    "request does not match selected operation or workspace base",
                )
            if prior is None:
                if (
                    payload.request_id
                    != "REQ-"
                    + dict(state.selected_candidate_event_ids).get(
                        event.candidate_id or "", ""
                    )
                    or payload.generation != 1
                    or payload.parent_request_id is not None
                ):
                    fail(
                        event,
                        "request-identity",
                        "new request requires selection identity and first generation",
                    )
            else:
                if (
                    payload.parent_request_id != prior.id
                    or payload.generation != prior.generation + 1
                    or prior.rule_id != rule.id
                    or prior.observed_tick is None
                    or prior.status
                    not in {
                        "responded",
                        "conflict",
                        "discarded",
                        "timedout",
                        "cancelled",
                        "permission-denied",
                    }
                ):
                    fail(
                        event,
                        "invalid-redelegation",
                        "new generation requires observed predecessor and identical rule",
                    )
                authorized = any(
                    scope == rule.required_scope
                    and owner == prior.id
                    and gen == prior.generation
                    and any(
                        row.id == approval
                        and row.observed_tick is not None
                        and row.disposition == "approve"
                        for row in state.collaboration.requests
                    )
                    for scope, owner, gen, approval in state.collaboration.grants
                )
                state = replace_request(state, replace(prior, status="superseded"))
        if (
            type(payload.generation) is not int
            or payload.generation < 1
            or not isinstance(payload.input_ids, tuple)
        ):
            fail(
                event,
                "request-types",
                "generation and input scope require canonical types",
            )
        if peer.kind == "peer":
            import json

            contacts = json.loads(execution.canonical_bytes)["participant_profile"][
                "contacts"
            ]
            if not any(row["id"] == peer.id for row in contacts):
                fail(
                    event, "unknown-contact", "actor cannot contact an undeclared peer"
                )
        if peer.kind == "ai":
            import json

            ai_scope = json.loads(execution.canonical_bytes)["participant_profile"][
                "ai"
            ]["input_classifications"]
            classifications = {row.id: row.classification for row in execution.claims}
            classifications.update(
                (row.id, row.classification) for row in execution.documents
            )
            classifications.update(
                (row.id, "public-evidence")
                for row in execution.references
                if row.source_classification != "audit_only_comment"
            )
            if any(
                classifications.get(item) not in ai_scope for item in payload.input_ids
            ):
                fail(
                    event,
                    "ai-input-classification",
                    "request exceeds the fixed AI disclosure classifications",
                )
        if peer.kind == "ai" and not execution.ai_allowed:
            fail(event, "ai-disabled", "the fixed participant profile disallows AI")
        available = set(state.acquired_documents) | {
            row.claim_id
            for row in state.claims
            if row.status is not ClaimStatus.WITHDRAWN
        }
        available.update(
            row.claim_id.removeprefix("reference:")
            for row in state.claims
            if row.claim_id.startswith("reference:")
            and row.status is not ClaimStatus.WITHDRAWN
        )
        if len(set(payload.input_ids)) != len(payload.input_ids) or not set(
            payload.input_ids
        ).issubset(available & set(peer.input_ids)):
            fail(
                event,
                "request-input-boundary",
                "request may contain only observed and explicitly shareable input",
            )
        busy = sum(
            (row.executing if peer.kind == "ai" else row.status == "pending")
            and next(r for r in cfg.rules if r.id == row.rule_id).collaborator_id
            == peer.id
            for row in state.collaboration.requests
        )
        available_now = dict(state.collaboration.availability).get(
            peer.id, peer.available
        )
        status = "pending" if busy < peer.capacity and available_now else "unavailable"
        request = RequestState(
            payload.request_id,
            payload.generation,
            rule.id,
            payload.base_version,
            payload.input_ids,
            event.id,
            event.logical_time,
            status,
            parent_request_id=payload.parent_request_id,
            authorized=authorized,
            executing=(
                peer.kind == "ai"
                and status == "pending"
                and set(rule.required_input_ids).issubset(payload.input_ids)
                and (rule.required_scope is None or authorized)
            ),
        )
        definitions = []
        if rule.disposition != "no-response":
            definitions.append(("reply", state.logical_time + rule.delay_ticks, 20))
        definitions.append(("expiry", state.logical_time + rule.expiry_ticks, 90))
        pending = obligations(state, event, request, tuple(definitions))
        return replace(
            state,
            collaboration=replace(
                state.collaboration,
                requests=state.collaboration.requests + (request,),
                reservation_obligations=pending,
                obligation_cause=event.id,
            ),
        )

    if not isinstance(payload, (ArrivalPayload, RequestAction)):
        fail(
            event,
            "invalid-collaboration-payload",
            "event requires an arrival or request action",
        )
    request_id = (
        payload.artifact.request_id
        if isinstance(payload, ArrivalPayload)
        else payload.request_id
    )
    generation = (
        payload.artifact.generation
        if isinstance(payload, ArrivalPayload)
        else payload.generation
    )
    found_request = next(
        (
            row
            for row in state.collaboration.requests
            if row.id == request_id and row.generation == generation
        ),
        None,
    )
    if found_request is None:
        fail(
            event,
            "unknown-request-generation",
            "event references no request in this generation",
        )
    request = found_request
    rule = next(row for row in cfg.rules if row.id == request.rule_id)
    peer = next(row for row in cfg.collaborators if row.id == rule.collaborator_id)

    if event.kind in {
        LocalEventKind.RESPONSE_ARRIVED,
        LocalEventKind.NOTICE_DELIVERED,
        LocalEventKind.REQUEST_EXPIRED,
    }:
        slot = state.collaboration.consumed_slot
        if slot is None or event.caused_by != (state.collaboration.consumed_event_id,):
            fail(
                event, "async-causality", "event must cite its consumed scheduler slot"
            )
        action = {
            LocalEventKind.RESPONSE_ARRIVED: "reply",
            LocalEventKind.NOTICE_DELIVERED: "notice",
            LocalEventKind.REQUEST_EXPIRED: "expiry",
        }[event.kind]
        if slot.payload_kind != slot_payload(action, request):
            fail(
                event,
                "async-slot-mismatch",
                "consumption belongs to another request or effect",
            )
        state = replace(
            state,
            ready_event_id=None,
            collaboration=replace(
                state.collaboration, consumed_slot=None, consumed_event_id=None
            ),
        )
        if action == "reply":
            if not isinstance(payload, ArrivalPayload) or request.response is not None:
                fail(
                    event,
                    "duplicate-response",
                    "reply requires a unique typed response artifact",
                )
            disposition = response_disposition(
                request,
                rule,
                dict(state.collaboration.availability).get(peer.id, peer.available),
            )
            expected = bind_response(request, rule, disposition)
            try:
                validate_response(
                    payload.artifact,
                    request.id,
                    request.generation,
                    request.base_version,
                    set(peer.evidence_ids),
                )
            except ValueError as error:
                fail(event, "response-evidence-mismatch", str(error))
            if payload.artifact != expected or payload.disposition != disposition:
                fail(
                    event,
                    "response-content-mismatch",
                    "reply differs from its frozen response record",
                )
            status = (
                "responded"
                if request.status in {"pending", "unavailable"}
                else request.status
            )
            changed = replace(
                request,
                response=payload.artifact,
                response_event_id=event.id,
                response_tick=state.logical_time,
                status=status,
                executing=False,
                disposition=disposition
                if request.status in {"pending", "unavailable"}
                else request.disposition,
            )
            state = replace_request(state, changed)
            if request.executing:
                interval = WorkInterval(
                    f"{peer.id}:{request.id}:g{request.generation}",
                    request.id,
                    request.generation,
                    request.requested_tick,
                    state.logical_time,
                    "active",
                )
                state = replace(
                    state,
                    collaboration=replace(
                        state.collaboration,
                        intervals=state.collaboration.intervals + (interval,),
                    ),
                )
            if (
                disposition == "approve"
                and request.status == "pending"
                and request.parent_request_id is not None
            ):
                grant_parent = next(
                    (
                        row
                        for row in state.collaboration.requests
                        if row.id == request.parent_request_id
                        and row.generation == request.generation
                    ),
                    None,
                )
                if (
                    grant_parent is not None
                    and grant_parent.status == "responded"
                    and grant_parent.disposition == "approval-required"
                ):
                    state = replace(
                        state,
                        collaboration=replace(
                            state.collaboration,
                            grants=state.collaboration.grants
                            + (
                                (
                                    rule.required_scope or "",
                                    grant_parent.id,
                                    grant_parent.generation,
                                    request.id,
                                ),
                            ),
                        ),
                    )
        elif action == "expiry":
            if request.status in {"pending", "unavailable"}:
                state = replace_request(
                    state,
                    replace(
                        request,
                        status="timedout",
                        disposition="timeout",
                        executing=False,
                    ),
                )
                if request.executing:
                    interval = WorkInterval(
                        f"{peer.id}:{request.id}:g{request.generation}",
                        request.id,
                        request.generation,
                        request.requested_tick,
                        state.logical_time,
                        "active",
                    )
                    state = replace(
                        state,
                        collaboration=replace(
                            state.collaboration,
                            intervals=state.collaboration.intervals + (interval,),
                        ),
                    )
            else:
                return state
        else:
            if (
                request.delivered_tick is not None
                or request.response_event_id is None
                and request.status != "timedout"
            ):
                fail(
                    event,
                    "invalid-notification-delivery",
                    "notification was not produced or was already delivered",
                )
            return replace_request(
                state,
                replace(
                    request,
                    delivered_tick=state.logical_time,
                    delivered_event_id=event.id,
                ),
            )
        if action == "reply" and request.status not in {"pending", "unavailable"}:
            return state
        # A notification is a distinct priority30 delivery, never actor knowledge.
        due = state.logical_time + rule.delivery_ticks
        if (
            state.scheduler.cursor is not None
            and due == state.logical_time
            and state.scheduler.cursor[1] > 30
        ):
            due += 1
        pending = obligations(state, event, request, (("notice", due, 30),))
        return replace(
            state,
            collaboration=replace(
                state.collaboration,
                reservation_obligations=pending,
                obligation_cause=event.id,
            ),
        )

    if not isinstance(payload, RequestAction):
        fail(
            event,
            "invalid-action-payload",
            "actor actions require only the typed request reference",
        )
    if event.kind in {
        LocalEventKind.AI_INTEGRATED,
        LocalEventKind.AI_DISCARDED,
        LocalEventKind.REQUEST_CANCELLED,
    }:
        current = next(
            row
            for row in reversed(state.collaboration.requests)
            if row.id == request.id
        )
        if (
            current.generation != request.generation
            or request.result_event_id is not None
        ):
            fail(
                event,
                "stale-task-result",
                "only current unresolved generation can change task outcome",
            )
        if event.kind is LocalEventKind.REQUEST_CANCELLED:
            if request.status not in {
                "pending",
                "responded",
                "unavailable",
            } or event.caused_by != (request.request_event_id,):
                fail(event, "invalid-task-cancel", "cancel must cite a live request")
            if request.executing:
                interval = WorkInterval(
                    f"{peer.id}:{request.id}:g{request.generation}",
                    request.id,
                    request.generation,
                    request.requested_tick,
                    state.logical_time,
                    "active",
                )
                state = replace(
                    state,
                    collaboration=replace(
                        state.collaboration,
                        intervals=state.collaboration.intervals + (interval,),
                    ),
                )
            return replace_request(
                state,
                replace(
                    request,
                    status="cancelled",
                    result_event_id=event.id,
                    executing=False,
                ),
            )
        if (
            peer.kind != "ai"
            or request.observed_tick is None
            or request.status != "responded"
            or request.disposition != "answer"
            or request.response is None
            or request.observed_event_id not in event.caused_by
        ):
            fail(
                event,
                "unobserved-ai-result",
                "AI result requires observed successful current response",
            )
        if event.kind is LocalEventKind.AI_DISCARDED:
            return replace_request(
                state, replace(request, status="discarded", result_event_id=event.id)
            )
        try:
            patch, mutation, expected_result = integration_plan(
                execution, state, request
            )
        except ValueError as error:
            fail(event, "ai-integration-permission", str(error))
        expected_output = (
            state.workspace_version if mutation is None else mutation.version
        )
        if (
            event.input_version != state.workspace_version
            or event.output_version != expected_output
            or event.patch_id != patch.id
            or event.observed_result != expected_result
        ):
            fail(
                event,
                "integration-version-mismatch",
                "integration event differs from its input, overlay or computed result",
            )
        if mutation is None:
            return replace_request(
                state,
                replace(request, status=expected_result, result_event_id=event.id),
            )
        changed_state = replace(
            state,
            workspace_version=mutation.version,
            workspace_versions=state.workspace_versions + (mutation.version,),
            workspace_files=mutation.files,
            applied_patch_ids=state.applied_patch_ids + (patch.id,),
            applied_patch_event_ids=state.applied_patch_event_ids + (event.id,),
            invalidated_reference_ids=tuple(
                sorted(set(state.invalidated_reference_ids + patch.affected_refs))
            ),
        )
        return replace_request(
            changed_state,
            replace(request, status="integrated", result_event_id=event.id),
        )

    if event.kind is LocalEventKind.NOTICE_ACKNOWLEDGED:
        if (
            request.delivered_tick is None
            or request.acknowledged_tick is not None
            or event.caused_by != (request.delivered_event_id,)
        ):
            fail(
                event,
                "invalid-notice-acknowledgment",
                "acknowledgment requires unique delivered notification",
            )
        return replace_request(
            state,
            replace(
                request,
                acknowledged_tick=state.logical_time,
                acknowledged_event_id=event.id,
            ),
        )

    if event.kind is LocalEventKind.RESPONSE_OBSERVED:
        if (
            request.delivered_tick is None
            or request.observed_tick is not None
            or request.acknowledged_tick is None
            or event.caused_by != (request.acknowledged_event_id,)
            or any(row.candidate_id is not None for row in state.scheduler.pending)
        ):
            fail(
                event,
                "response-not-observable",
                "reply is undelivered, already observed, or human resource is busy",
            )
        changed = replace(
            request, observed_tick=state.logical_time, observed_event_id=event.id
        )
        state = replace_request(state, changed)
        evidence = () if request.response is None else (request.response.id,)
        claims = (
            ()
            if request.disposition != "answer" or request.status != "responded"
            else tuple(
                ClaimKnowledge(
                    claim_id, ClaimStatus.ACQUIRED, evidence, state.logical_time
                )
                for claim_id in rule.response_claim_ids
            )
        )
        statement = (
            "Request timed out."
            if request.disposition == "timeout"
            else request.response.text
            if request.response is not None
            else "Request unresolved."
        )
        observation = LocalObservationRecord(
            event.id,
            state.logical_time,
            request.base_version,
            f"response:{request.id}:g{request.generation}",
            "response",
            request.id,
            (request.disposition or request.status,),
            statement,
        )
        existing = {row.claim_id for row in state.claims}
        return replace(
            state,
            claims=state.claims
            + tuple(row for row in claims if row.claim_id not in existing),
            observations=state.observations + (observation,),
        )

    if event.kind is LocalEventKind.WAIT_STARTED:
        if (
            request.status not in {"pending", "unavailable", "responded", "timedout"}
            or state.collaboration.waiting_for is not None
            or request.observed_tick is not None
            or any(row.candidate_id is not None for row in state.scheduler.pending)
            or event.caused_by != (request.request_event_id,)
        ):
            fail(
                event,
                "invalid-wait",
                "waiting requires an outstanding own request and a free human resource",
            )
        return replace(
            state,
            collaboration=replace(
                state.collaboration,
                waiting_for=(request.id, request.generation),
                waiting_since=state.logical_time,
                waiting_event_id=event.id,
            ),
        )
    if event.kind is LocalEventKind.WAIT_ENDED:
        if (
            state.collaboration.waiting_for != (request.id, request.generation)
            or state.collaboration.waiting_since is None
            or event.caused_by
            not in {
                (state.collaboration.waiting_event_id,),
                (state.collaboration.waiting_event_id, request.observed_event_id),
                (state.collaboration.waiting_event_id, request.result_event_id),
            }
        ):
            fail(event, "invalid-wait-end", "wait end lacks its matching wait start")
        interval = WorkInterval(
            state.actor_id,
            request.id,
            request.generation,
            state.collaboration.waiting_since,
            state.logical_time,
            "wait",
        )
        return replace(
            state,
            collaboration=replace(
                state.collaboration,
                intervals=state.collaboration.intervals + (interval,),
                waiting_for=None,
                waiting_since=None,
                waiting_event_id=None,
            ),
        )
    fail(event, "unsupported-collaboration-event", "unsupported G5 transition")
