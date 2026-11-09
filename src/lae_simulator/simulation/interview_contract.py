"""Provider independent interview contract; no networking or world truth access."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal, Protocol

PROMPT_VERSION: Literal["employee-interview-v2"] = "employee-interview-v2"
VALID_KINDS = frozenset({"experience", "hearsay", "misunderstanding", "interpretation",
                         "inference", "unknown", "not_remembered"})


@dataclass(frozen=True)
class Statement:
    text: str
    epistemic_kind: str
    private_support_ids: tuple[str, ...] = ()
    topic: str | None = None
    value: str | None = None
    episode: str | None = None


@dataclass(frozen=True)
class GeneratedAnswer:
    statements: tuple[Statement, ...]
    generator: str
    generator_version: str
    model: str
    settings: str = ""
    execution: dict[str, object] = field(default_factory=dict)


class GenerationFailure(Exception):
    """Safe failure code and private attempt metadata, never raw SDK error text."""

    def __init__(self, code: str, execution: dict[str, object] | None = None):
        super().__init__(code)
        self.code = code
        self.execution = execution or {}


class InterviewGenerator(Protocol):
    name: str
    version: str
    model: str
    settings: str

    def generate(self, *, question: str, package: dict[str, object],
                 retrieved: tuple[dict[str, object], ...], prompt_version: str) -> GeneratedAnswer: ...


@dataclass(frozen=True)
class InterviewResult:
    status: str
    answer: str | None
    epistemic_kinds: tuple[str, ...]
    audit: dict[str, object]


def answer_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "text": {"type": "string"},
        "epistemic_kind": {"type": "string", "enum": sorted(VALID_KINDS)},
        "private_support_ids": {"type": "array", "items": {"type": "string"}},
        **{key: {"type": ["string", "null"]} for key in ("topic", "value", "episode")},
    }
    return {"type": "object", "additionalProperties": False,
            "properties": {"statements": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": properties, "required": list(properties)}}},
            "required": ["statements"]}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def parse_statements(text: str) -> tuple[Statement, ...]:
    """Enforce the complete local schema even if a provider claims schema compliance."""
    try:
        data = json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        if not isinstance(data, dict) or set(data) != {"statements"}:
            raise ValueError("root")
        rows = data["statements"]
        if not isinstance(rows, list) or len(rows) > 64:
            raise ValueError("statements")
        result: list[Statement] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"text", "epistemic_kind", "private_support_ids", "topic", "value", "episode"}:
                raise ValueError("fields")
            if (not isinstance(row["text"], str) or not row["text"].strip()
                    or len(row["text"]) > 16000 or row["epistemic_kind"] not in VALID_KINDS):
                raise ValueError("statement")
            ids = row["private_support_ids"]
            if not isinstance(ids, list) or any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != len(ids):
                raise ValueError("support")
            if any(row[key] is not None and (not isinstance(row[key], str) or not row[key].strip())
                   for key in ("topic", "value", "episode")):
                raise ValueError("claim")
            result.append(Statement(row["text"], row["epistemic_kind"], tuple(ids), row["topic"], row["value"], row["episode"]))
        return tuple(result)
    except (ValueError, TypeError, KeyError):
        raise GenerationFailure("invalid-output") from None
