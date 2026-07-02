"""Deterministic security screen for the Ambient Expense Agent.

Runs BEFORE any LLM invocation. Two jobs:
  1. Redact PII (card numbers, SSNs, emails, phone numbers) from the raw
     expense payload so it never reaches the model context.
  2. Detect prompt-injection patterns in free-text fields (e.g. memo/notes)
     and short-circuit the workflow before the LLM ever sees them.

Kept as plain Python (no model calls) so it is fast, deterministic, and
fully unit-testable without an API key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- PII patterns -----------------------------------------------------------

_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,2}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}\b")

_PII_PATTERNS = {
    "card_number": _CARD_RE,
    "ssn": _SSN_RE,
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
}

# --- Prompt-injection patterns ----------------------------------------------
# Deliberately conservative substring/regex list. Extend via evalset failures
# rather than guessing — see tests/eval/evalsets/basic.evalset.json.

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|any|previous|prior) instructions", re.I),
    re.compile(r"disregard (the|your) (system|above) prompt", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"act as (an?|the) (unrestricted|jailbroken|dan)", re.I),
    re.compile(r"reveal (your|the) (system prompt|instructions)", re.I),
    re.compile(r"auto[- ]?approve (this|any|all)", re.I),  # tries to talk the LLM into self-approving
    re.compile(r"\bsudo\b|\boverride approval\b", re.I),
]


@dataclass
class ScreenResult:
    clean_payload: dict
    redactions: list[str] = field(default_factory=list)
    injection_detected: bool = False
    injection_reason: str | None = None

    @property
    def route(self) -> str:
        return "blocked" if self.injection_detected else "clear"


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Replace PII substrings with typed placeholders. Returns (clean_text, labels_found)."""
    found: list[str] = []

    def _sub(pattern: re.Pattern, label: str, s: str) -> str:
        def repl(m: re.Match) -> str:
            found.append(label)
            return f"[REDACTED_{label.upper()}]"

        return pattern.sub(repl, s)

    clean = text
    for label, pattern in _PII_PATTERNS.items():
        clean = _sub(pattern, label, clean)
    return clean, found


def detect_injection(text: str) -> str | None:
    """Return a matched pattern description if the text looks like a prompt-injection attempt."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def screen_expense_payload(payload: dict) -> ScreenResult:
    """Run PII redaction + injection detection over every string field in the payload."""
    redactions: list[str] = []
    injection_reason: str | None = None
    clean_payload = dict(payload)

    for key, value in payload.items():
        if not isinstance(value, str):
            continue
        clean_value, found = redact_pii(value)
        redactions.extend(f"{key}:{label}" for label in found)
        clean_payload[key] = clean_value

        if injection_reason is None:
            hit = detect_injection(value)
            if hit:
                injection_reason = f"{key} matched pattern: {hit}"

    return ScreenResult(
        clean_payload=clean_payload,
        redactions=redactions,
        injection_detected=injection_reason is not None,
        injection_reason=injection_reason,
    )
