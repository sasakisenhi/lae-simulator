"""Structured failures for world-definition validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class ValidationIssue:
    path: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}


class WorldValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...]):
        self.issues = tuple(sorted(issues))
        summary = "; ".join(
            f"{issue.path} [{issue.code}] {issue.message}" for issue in self.issues
        )
        super().__init__(summary)

