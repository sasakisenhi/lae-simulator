"""Allowlisted SDK diagnostics. Never retain messages, arbitrary bodies or headers."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

CODES = frozenset({
    "rate_limit_exceeded", "rate_limit_error", "slow_down", "RESOURCE_EXHAUSTED",
    "insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached",
    "organization_spend_limit_exceeded", "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded", "quota_exceeded", "UNAVAILABLE",
})
NON_RETRYABLE = CODES - {"rate_limit_exceeded", "rate_limit_error", "slow_down", "UNAVAILABLE", "RESOURCE_EXHAUSTED"}
FINISH_REASONS = frozenset({"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER",
                           "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "MALFORMED_FUNCTION_CALL",
                           "max_output_tokens", "content_filter", "completed", "incomplete", "failed"})


def count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def allowed(value: object, choices: frozenset[str], secret: str = "") -> str | None:
    return value if isinstance(value, str) and value in choices and not (secret and secret in value) else None


def request_id(value: object, secret: str) -> str | None:
    # Request IDs remain private diagnostic metadata, never interview publication.
    if not isinstance(value, str) or (secret and secret in value):
        return None
    if re.fullmatch(r"(?:req[_-][A-Za-z0-9_-]{8,100}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})", value):
        return value
    return None


def model_identifier(value: object, secret: str) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,120}", value) and not (secret and secret in value):
        return value
    return None


def safe_details(value: object, *, provider: str, model: str, secret: str) -> dict[str, object]:
    """Recheck even an injected transport's diagnostics at the audit boundary."""
    data = value if isinstance(value, dict) else {}
    category = allowed(data.get("category"), frozenset({"timeout", "quota-or-billing", "authentication-failed",
                       "rate-limit", "rate-limit-unknown", "provider-unavailable", "provider-error"}), secret)
    status = count(data.get("http_status"))
    delay = data.get("retry_after_seconds")
    delay = delay if isinstance(delay, (int, float)) and not isinstance(delay, bool) and math.isfinite(delay) and 0 <= delay <= 86400 else None
    code = allowed(data.get("error_code"), CODES, secret)
    error_type = allowed(data.get("error_type"), CODES, secret)
    return {"provider": provider, "model": model, "category": category,
            "http_status": status if status is not None and 100 <= status <= 599 else None,
            "error_code": code, "error_type": error_type, "retry_after_seconds": delay,
            "request_id": request_id(data.get("request_id"), secret),
            "retryable": data.get("retryable") is True and category in {"timeout", "rate-limit", "provider-unavailable"}
                         and code not in NON_RETRYABLE and error_type not in NON_RETRYABLE}


def error_details(error: Exception, *, provider: str, model: str, secret: str) -> dict[str, object]:
    raw_status = getattr(error, "status_code", getattr(error, "code", None))
    status = raw_status if type(raw_status) is int and 100 <= raw_status <= 599 else None
    body = getattr(error, "body", None)
    if not isinstance(body, Mapping):
        body = getattr(error, "details", {})  # google-genai APIError stores its JSON here.
    if isinstance(body, Mapping) and isinstance(body.get("error"), Mapping):
        body = body["error"]
    body = body if isinstance(body, Mapping) else {}
    code = allowed(body.get("code"), CODES, secret) or allowed(getattr(error, "code", None), CODES, secret)
    error_type = allowed(body.get("type"), CODES, secret) or allowed(body.get("status"), CODES, secret)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {})
    headers = headers if isinstance(headers, Mapping) else {}
    raw_delay = headers.get("retry-after")
    delay: float | None = None
    if isinstance(raw_delay, str) and re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,3})?", raw_delay) and not (secret and secret in raw_delay):
        parsed = float(raw_delay)
        if math.isfinite(parsed) and 0 <= parsed <= 86400:
            delay = parsed
    rid = (request_id(getattr(error, "request_id", None), secret)
           or request_id(headers.get("x-request-id"), secret)
           or request_id(headers.get("x-goog-request-id"), secret))
    if isinstance(error, TimeoutError) or "timeout" in type(error).__name__.casefold():
        category, retryable = "timeout", True
    elif code in NON_RETRYABLE or error_type in NON_RETRYABLE:
        category, retryable = "quota-or-billing", False
    elif status in (401, 403):
        category, retryable = "authentication-failed", False
    elif status == 429:
        retryable = code in {"rate_limit_exceeded", "slow_down"}
        category = "rate-limit" if retryable else "rate-limit-unknown"
    elif status is not None and status >= 500:
        category, retryable = "provider-unavailable", True
    else:
        category, retryable = "provider-error", False
    return {"provider": provider, "model": model, "http_status": status,
            "error_code": code, "error_type": error_type, "retry_after_seconds": delay,
            "request_id": rid, "category": category,
            "retryable": retryable and (raw_delay is None or delay is not None)}
