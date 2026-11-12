"""Redaction and sensitive-value detection. Used on every title we keep and every line we log."""
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?)\d{3,4}[ -]\d{4}(?!\d)")
RESIDENT_ID = re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")          # KR 주민등록번호 shape
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
LONG_NUMBER = re.compile(r"(?<![A-Za-z])\d{5,}")
SECRETISH = re.compile(
    # key = literal value. Code expressions (os.environ.get(...), func()) are not values and don't match.
    r"(?i)(password|passwd|pwd|비밀번호|api[_-]?key|secret|token|bearer)\s*[:=]\s*"
    r"[\"']?[^\s\"'(),.\[\]{}]{4,}[\"']?(?=\s|$|[,;)}\]])"
)


def luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def looks_sensitive(value: str) -> str | None:
    """Return a reason string if value looks like a password/card/ID we must never type or store."""
    if not value:
        return None
    if SECRETISH.search(value):
        return "secret-like key=value"
    if RESIDENT_ID.search(value):
        return "resident registration number"
    for m in CARD.finditer(value):
        if luhn_ok(m.group(0)):
            return "payment card number"
    return None


def redact(text: str, numbers: bool = True) -> str:
    """numbers=False keeps plain long numbers (run ids, counts) — used for logs."""
    if not text:
        return text
    text = SECRETISH.sub(lambda m: m.group(1) + "=[REDACTED]", text)
    text = EMAIL.sub("[email]", text)
    text = RESIDENT_ID.sub("[id]", text)
    text = CARD.sub(lambda m: "[card]" if luhn_ok(m.group(0)) else m.group(0), text)
    text = PHONE.sub("[phone]", text)
    if numbers:
        text = LONG_NUMBER.sub("[num]", text)
    return text


_DATEISH = re.compile(r"\b\d{1,4}[-./]\d{1,2}(?:[-./]\d{1,4})?\b")
_NUM = re.compile(r"\d+")
_BRACKETS = re.compile(r"\[(?:email|id|card|phone|num)\]")
_SPACES = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Turn 'Invoice_2026-03-04 (3).pdf - Preview' into 'invoice_# (#).pdf - preview' so repeats group together."""
    t = redact(title or "").lower()
    t = _BRACKETS.sub("#", t)
    t = _DATEISH.sub("#", t)
    t = _NUM.sub("#", t)
    t = _SPACES.sub(" ", t).strip()
    return t[:80]
