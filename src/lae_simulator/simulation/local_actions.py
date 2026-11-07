"""Pure command-target checks shared by command preparation and replay."""

from __future__ import annotations

from lae_simulator.simulation.local_model import LocalCandidate, ScenarioExecution


def document_target_matches(execution: ScenarioExecution, candidate: LocalCandidate,
                            document_id: str) -> bool:
    if candidate.operation == "issue.read":
        return any(
            item.id == document_id and item.source_classification == "real_oss_issue"
            for item in execution.documents
        )
    declared_targets = {
        reference.target_id for reference in execution.references
        if reference.id in candidate.target_refs
        and reference.coverage == "recorded"
        and reference.source_classification != "audit_only_comment"
    }
    return document_id in declared_targets
