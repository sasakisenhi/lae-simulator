"""Separate structural, support, disclosure, and limited claim checks.

An ID/value match is never proof of arbitrary prose. Nonliteral statements need
independent semantic review and are withheld as INCONCLUSIVE in this version.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lae_simulator.simulation.interview_contract import VALID_KINDS, Statement

CHECKER_VERSION = "interview-checks-v3"
UNKNOWN_TEXT = frozenset({"I do not know.", "わかりません。", "不明です。"})
MEMORY_TEXT = frozenset({"I do not remember.", "I do not remember why.", "覚えていません。"})
KIND_MAP = {"direct-experience": "experience", "mistaken-belief": "misunderstanding",
            "misunderstanding": "misunderstanding", "hearsay": "hearsay",
            "interpretation": "interpretation"}


@dataclass(frozen=True)
class Support:
    identifier: str
    texts: tuple[str, ...]
    kind: str
    episode: str | None


def package_support(package: dict[str, object]) -> dict[str, Support]:
    """Use only explicit personal rows; never traverse arbitrary administrative fields."""
    supports: dict[str, Support] = {}
    background = package.get("background", [])
    if isinstance(background, list):
        for row in background:
            if isinstance(row, list) and len(row) == 3 and all(isinstance(v, str) for v in row):
                supports[row[0]] = Support(row[0], (row[2],), "interpretation", "initial")
    for field in ("perceptions", "belief_history"):
        rows = package.get(field, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = row.get("event_id")
            if not isinstance(sid, str):
                continue
            texts = [row[key] for key in ("statement",) if isinstance(row.get(key), str)]
            perception = row.get("perception")
            if isinstance(perception, dict):
                texts.extend(perception[key] for key in ("action", "belief") if isinstance(perception.get(key), str))
            kind = str(row.get("epistemic_kind", row.get("experience_kind", "interpretation")))
            supports[sid] = Support(sid, tuple(texts), KIND_MAP.get(kind, kind), sid)
    return supports


def support_catalog(package: dict[str, object]) -> tuple[dict[str, object], ...]:
    return tuple({"id": row.identifier, "texts": list(row.texts),
                  "epistemic_kind": row.kind, "episode": row.episode}
                 for row in package_support(package).values())


def private_identifiers(package: dict[str, object]) -> set[str]:
    identifiers = set(package_support(package))
    pending: list[object] = [package]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            identifiers.update(value for key, value in item.items()
                               if key in {"event_id", "claim_id", "id"} and isinstance(value, str))
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and item.startswith(("observed-claim-", "prediction-", "request-")):
            identifiers.add(item)
    return identifiers


def validate_statements(statements: tuple[Statement, ...], supports: dict[str, Support],
                        prior: tuple[Statement, ...], private_ids: set[str] | None = None) -> tuple[str, list[dict[str, object]]]:
    checks: list[dict[str, object]] = []
    for statement in statements:
        ids = statement.private_support_ids
        references = len(set(ids)) == len(ids) and all(sid in supports for sid in ids)
        absence = statement.epistemic_kind in {"unknown", "not_remembered"}
        grounded = references and (bool(ids) or absence)
        # IDs are private even when the underlying statement is disclosable.
        disclosure = not (any(sid in statement.text for sid in (private_ids or set(supports)))
                          or re.search(r"\b(?:PER-|LEV-|LSCH-|private_support_ids|audit-only|administrative:)", statement.text))
        kind_valid = statement.epistemic_kind in VALID_KINDS
        if absence:
            grounded = grounded and statement.value is None
        # This is a restricted quotation check, not semantic verification of paraphrases.
        literal = (statement.text in (UNKNOWN_TEXT if statement.epistemic_kind == "unknown" else
                                    MEMORY_TEXT if statement.epistemic_kind == "not_remembered" else ())
                   and not ids and statement.value is None)
        if references and ids:
            literal = literal or any(
                statement.text in supports[sid].texts and supports[sid].kind == statement.epistemic_kind
                and (statement.value is None or statement.value in statement.text)
                and (statement.episode is None or statement.episode == supports[sid].episode)
                for sid in ids)
        # Value labels and translations are not a shared semantic ontology.
        # Only compare concrete file paths, or conflicting literal fixed records.
        concrete = bool(statement.value and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", statement.value))
        contradiction = any(
            (concrete or literal) and statement.value and old.value
            and bool(statement.topic and old.topic) and statement.topic == old.topic
            and (bool(set(ids) & set(old.private_support_ids))
                 or bool(statement.topic and statement.episode
                         and (statement.topic, statement.episode) == (old.topic, old.episode)))
            and statement.value.casefold() != old.value.casefold()
            and not any(statement.value.casefold() in text.casefold()
                        for sid in old.private_support_ids if sid in supports for text in supports[sid].texts)
            and statement.epistemic_kind not in {"inference", "unknown", "not_remembered", "misunderstanding"}
            and old.epistemic_kind == statement.epistemic_kind for old in prior)
        # Different fields may share one observation. Without a fixed claim-item
        # ontology, changed values across topics are uncertain, not a contradiction.
        item_uncertain = any(set(ids) & set(old.private_support_ids)
                             and (not statement.topic or not old.topic or statement.topic != old.topic) and statement.value and old.value
                             and statement.value != old.value for old in prior)
        cross = "FAIL" if contradiction else "PASS" if literal and not item_uncertain else "UNKNOWN"
        kind_promotion = references and bool(ids) and statement.epistemic_kind == "experience" and all(
            supports[sid].kind == "misunderstanding" for sid in ids)
        semantics = "FAIL" if kind_promotion else "PASS" if literal else "NEEDS_REVIEW"
        checks.append({"schema": "PASS" if kind_valid else "FAIL",
                       "support": "PASS" if grounded else "FAIL",
                       "reference_access": "PASS" if references else "FAIL",
                       "disclosure": "PASS" if disclosure else "FAIL",
                       "semantics": semantics,
                       "epistemic_kind": statement.epistemic_kind,
                       "episode_binding": "PASS" if not statement.episode or (references and any(
                           supports[sid].episode == statement.episode for sid in ids)) else "NEEDS_REVIEW",
                       "cross_question": cross, "contradiction": bool(contradiction),
                       "support_ids": list(ids),
                       "reason": "missing-or-invalid-support" if not grounded else
                                 "private-identifier-disclosure" if not disclosure else
                                 "misunderstanding-promoted-to-fact" if kind_promotion else
                                 "conflicting-concrete-claim" if contradiction else
                                 "restricted-quotation-or-abstention" if literal else "independent-semantic-review-required"})
    if not statements:
        return "unanswerable", checks
    if any(row[key] == "FAIL" for row in checks for key in ("schema", "support", "disclosure", "cross_question", "semantics")):
        return "rejected", checks
    if any(row["semantics"] == "NEEDS_REVIEW" or row["cross_question"] == "UNKNOWN" or row["episode_binding"] == "NEEDS_REVIEW" for row in checks):
        return "inconclusive", checks
    return "accepted", checks
