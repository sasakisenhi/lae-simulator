"""Structured execution, integrity, publication, and persistence failures."""

from __future__ import annotations

from dataclasses import dataclass

from lae_simulator.simulation.model import IntegrityIssue


class SimulationError(RuntimeError):
    pass


class HistoryValidationError(SimulationError):
    def __init__(self, issue: IntegrityIssue):
        self.issue = issue
        super().__init__(f"{issue.target} [{issue.code}] {issue.message}")


class PublicationError(SimulationError):
    pass


@dataclass(frozen=True)
class FailureRecord:
    status: str
    stage: str
    target: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {
            "reason": self.reason,
            "stage": self.stage,
            "status": self.status,
            "target": self.target,
        }


class PersistenceError(SimulationError):
    def __init__(self, record: FailureRecord):
        self.record = record
        super().__init__(f"{record.stage} failed for {record.target}: {record.reason}")
