"""Policy selection based only on typed actor observations."""

from __future__ import annotations

import json

from lae_simulator.simulation.local_model import (
    ActorCandidate,
    ActorObservation,
    ClaimStatus,
    LocalCandidate,
    LocalExpression,
    LocalState,
    PolicyInput,
    ScenarioExecution,
)

_G3_OPERATIONS = frozenset({
    "issue.read", "document.read", "code.search", "symbol.navigate",
    "patch.apply", "patch.revert", "check.model", "pr.create", "run.defer",
})


def supported_operations(execution: ScenarioExecution) -> frozenset[str]:
    return (_G3_OPERATIONS if execution.collaboration is None else
            _G3_OPERATIONS | {'question.send', 'ai.delegate', 'ai.integrate', 'wait'})

def actor_observation(execution: ScenarioExecution, state: LocalState) -> ActorObservation:
    known_claims = {item.id: item for item in execution.claims
                    if item.classification != "administrative"}
    references = {item.id: item for item in execution.references
                  if item.source_classification != "audit_only_comment"}
    observations = {item.claim_id: item for item in state.observations
                    if item.kind in {"search", "check"}}
    claim_rows = []
    for item in state.claims:
        claim = known_claims.get(item.claim_id)
        if claim is not None:
            statement = claim.statement
        elif item.claim_id.startswith("reference:"):
            reference = references.get(item.claim_id.removeprefix("reference:"))
            statement = (f"Reference {reference.id}: {reference.relation}; coverage={reference.coverage}; "
                         f"target={reference.target_id or 'unresolved'}" if reference else "")
        elif item.claim_id.startswith("check:") or item.claim_id.startswith("search:"):
            observation = observations.get(item.claim_id)
            statement = observation.statement if observation else ""
        else:
            statement = f"Participant information: {item.claim_id}."
        claim_rows.append((item.claim_id, item.status.value, statement))
    claims = tuple(sorted(claim_rows))
    predictions = tuple((item.id, item.statement, item.status, item.evidence_ids)
                        for item in state.predictions)
    allowed_docs = tuple(sorted(
        item.id for item in execution.documents
        if item.availability == "available"
        and item.classification != "administrative"
        and item.source_classification != "audit_only_comment"
        and (item.id, "read") in execution.permissions
    ))
    acquired_content = tuple(sorted(
        (item.id, item.digest, item.content)
        for item in execution.documents
        if item.id in state.acquired_documents and item.content is not None
        and item.source_classification != "audit_only_comment"
    ))
    known_reference_ids = {
        item.claim_id.removeprefix("reference:") for item in state.claims
        if item.claim_id.startswith("reference:") and item.status is not ClaimStatus.WITHDRAWN
    }
    refs = tuple(sorted(
        (item.id, item.coverage, item.target_id)
        for item in execution.references
        if item.id in known_reference_ids and item.id not in state.invalidated_reference_ids
        and item.source_classification != "audit_only_comment"
    ))
    actor_visible_ref_ids = frozenset(references)
    operations = tuple(operation for operation in execution.operation_capabilities
                       if operation in supported_operations(execution))
    candidate_views = tuple(
        ActorCandidate(
            item.id, item.label, item.operation,
            tuple(ref for ref in item.target_refs if ref in actor_visible_ref_ids),
            tuple(ref for ref in item.evidence_refs if ref in actor_visible_ref_ids),
        )
        for item in execution.candidates
        if item.operation in operations
        and _actor_candidate_available(item, execution, state)
    )
    return ActorObservation(
        logical_time=state.logical_time, actor_id=state.actor_id, claims=claims,
        predictions=predictions,
        visible_documents=allowed_docs,
        acquired_document_content=acquired_content,
        searchable_files=tuple(sorted(item.path for item in state.workspace_files)),
        visible_references=refs,
        invalidated_references=state.invalidated_reference_ids,
        workspace_version=state.workspace_version,
        applied_patch_ids=state.applied_patch_ids,
        checks=tuple((item.check_id, item.subject_version, item.status, item.mode,
                      item.coverage, item.evidence_refs, item.limitations)
                     for item in state.check_results),
        allowed_operations=operations,
        available_candidates=candidate_views, active_view_id=state.active_view_id,
        search_query=state.search_query, search_result_refs=state.search_result_refs,
        observed_messages=state.observed_messages,
        observations=state.observations,
        notifications=tuple((row.id, row.generation, 'read' if row.observed_tick is not None else 'acknowledged' if row.acknowledged_tick is not None else 'delivered')
                            for row in state.collaboration.requests if row.delivered_tick is not None),
        task_states=tuple((row.id, row.generation,
                           (row.status if row.observed_tick is not None else 'pending'))
                          for row in state.collaboration.requests),
    )


def _actor_candidate_available(candidate: LocalCandidate, execution: ScenarioExecution,
                               state: LocalState) -> bool:
    if candidate.operation not in supported_operations(execution) or candidate.operation not in execution.operation_capabilities:
        return False
    if candidate.operation.startswith("ai.") and not execution.ai_allowed:
        return False
    claim_ids = {item.claim_id for item in state.claims if item.status is not ClaimStatus.WITHDRAWN}
    if not set(candidate.required_claims).issubset(claim_ids):
        return False
    if candidate.permission is not None and candidate.permission not in execution.permissions:
        return False
    return (
        all(_expression_matches(expr, execution, state) for expr in candidate.availability)
        and candidate_preconditions_met(candidate, execution, state)
    )


def candidate_preconditions_met(candidate: LocalCandidate, execution: ScenarioExecution,
                                state: LocalState) -> bool:
    return all(_expression_matches(expr, execution, state) for expr in candidate.preconditions)


def candidate_request_valid(candidate: LocalCandidate, execution: ScenarioExecution,
                            state: LocalState) -> bool:
    """Validate non-access conditions; access denial is an observable outcome."""
    known = {item.claim_id for item in state.claims if item.status is not ClaimStatus.WITHDRAWN}
    return (candidate.operation in execution.operation_capabilities
            and set(candidate.required_claims).issubset(known)
            and all(_expression_matches(expr, execution, state)
                    for expr in candidate.availability + candidate.preconditions
                    if not expr.field.startswith(("permission.", "access."))))


def candidate_access_met(candidate: LocalCandidate, execution: ScenarioExecution,
                         state: LocalState) -> bool:
    return ((candidate.permission is None or candidate.permission in execution.permissions)
            and all(_expression_matches(expr, execution, state)
                    for expr in candidate.availability + candidate.preconditions
                    if expr.field.startswith(("permission.", "access."))))


def _field_value(field: str, execution: ScenarioExecution,
                 state: LocalState) -> str | bool | int | None:
    if execution.collaboration is not None:
        if field.startswith('contact.'):
            contacts = json.loads(execution.canonical_bytes)['participant_profile']['contacts']
            return 'known' if any(row['id'] == field.partition('.')[2] for row in contacts) else None
        if field == 'question.content':
            return 'bounded'
        if field == 'ai.input-scope':
            return 'actor-visible'
        if field == 'tasks.ai':
            return 'completed' if any(row.observed_tick is not None and row.status == 'responded'
                and row.disposition == 'answer' and any(rule.id == row.rule_id and rule.operation == 'ai.delegate'
                for rule in execution.collaboration.rules) for row in state.collaboration.requests) else 'pending'
        if field == 'workspace.base':
            return 'task-base' if any(row.observed_tick is not None and row.status == 'responded'
                                     for row in state.collaboration.requests) else None
        if field == 'tasks.pending':
            return any(row.observed_tick is None for row in state.collaboration.requests)
        if field == 'deadline.reached':
            return execution.timing is not None and state.logical_time >= execution.timing.deadline_tick
    if field == 'submission.ready':
        return bool(state.applied_patch_ids)
    if field == 'submission.target':
        return 'simulated'
    if field == 'run.active':
        return state.outcome is None
    if field == 'outcome.valid':
        return True
    if field.startswith("access."):
        document_id = field.partition(".")[2]
        document = next((item for item in execution.documents if item.id == document_id), None)
        if document is None or document.classification == "administrative":
            return None
        available = document.availability == "available" and (document_id, "read") in execution.permissions
        return "available" if available else "unavailable"
    if field == "tool.search":
        return "code.search" in execution.operation_capabilities
    if field == "workspace.version":
        if state.workspace_version == "B0" or state.workspace_files == execution.base_files:
            return "B0"
        return state.applied_patch_ids[-1] if state.applied_patch_ids else "unknown"
    if field == "workspace.has-overlay":
        return bool(state.applied_patch_ids)
    if field == "knowledge.locations":
        return "search-result" if state.search_result_refs else None
    if field == "knowledge.count":
        return "nonzero" if state.claims else "zero"
    if field == "check.supported":
        version = ("B0" if state.workspace_version == "B0" or state.workspace_files == execution.base_files else
                   state.applied_patch_ids[-1] if state.applied_patch_ids else "unknown")
        return any(version in item.subject_versions for item in execution.checks)
    if field == "ai.allowed":
        return execution.ai_allowed
    if field.startswith("permission."):
        resource = field.partition(".")[2]
        if (resource == "workspace" and execution.workspace_resource_id is not None
                and (execution.workspace_resource_id, "virtual-edit") in execution.permissions):
            return "edit"
        if (resource, "read") in execution.permissions:
            return "read"
        return None
    # In particular, administrative claims are not an actor-observable field.
    return None


def _expression_matches(expression: LocalExpression, execution: ScenarioExecution,
                        state: LocalState) -> bool:
    actual = _field_value(expression.field, execution, state)
    if actual is None:
        return False
    if expression.field == "workspace.version" and expression.value == "known":
        return actual != "unknown"
    if expression.operator == "equals":
        return actual == expression.value
    if expression.operator == "subset":
        return actual == expression.value
    return expression.operator == "present"


def select_local_candidate(policy_input: PolicyInput) -> ActorCandidate | None:
    """A deterministic policy using only its typed actor observation."""
    observation = policy_input.observation
    candidates = observation.available_candidates
    if not candidates:
        return None
    operation_preference: tuple[str, ...]
    check_failed = any(item[2] == "FAIL" for item in observation.checks)
    acquired_document_ids = {
        document_id for document_id, _digest, _content in observation.acquired_document_content
    }
    if check_failed:
        operation_preference = ("document.read", "code.search", "symbol.navigate")
    elif observation.search_result_refs:
        operation_preference = ("symbol.navigate",)
    elif not acquired_document_ids:
        operation_preference = ("issue.read", "document.read")
    elif observation.workspace_version == "B0":
        operation_preference = ("code.search", "document.read")
    else:
        operation_preference = ("check.model", "document.read", "code.search")
    for operation in operation_preference:
        choices = [item for item in candidates if item.operation == operation]
        if choices:
            return min(choices, key=lambda item: item.id)
    # This fallback deliberately permits defer, no-op, and non-correct choices.
    return min(candidates, key=lambda item: item.id)


