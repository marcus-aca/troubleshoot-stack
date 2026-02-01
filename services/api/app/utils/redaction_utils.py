from __future__ import annotations

import re


def redact_sensitive_text(text: str) -> tuple[str, int]:
    redacted = text
    hits = 0

    def sub(pattern: str, replacement: str, flags: int = 0) -> None:
        nonlocal redacted, hits
        redacted, count = re.subn(pattern, replacement, redacted, flags=flags)
        hits += count

    def luhn_check(value: str) -> bool:
        total = 0
        should_double = False
        for ch in reversed(value):
            if not ch.isdigit():
                return False
            digit = int(ch)
            add = digit * 2 if should_double else digit
            if add > 9:
                add -= 9
            total += add
            should_double = not should_double
        return total % 10 == 0

    sub(r"-----BEGIN [\s\S]+? PRIVATE KEY-----[\s\S]+?-----END [\s\S]+? PRIVATE KEY-----", "[PRIVATE_KEY]")
    sub(r"\bAKIA[0-9A-Z]{16}\b", "[AWS_ACCESS_KEY_ID]")
    sub(r"\bASIA[0-9A-Z]{16}\b", "[AWS_ACCESS_KEY_ID]")
    sub(r"\b[A-Za-z0-9/+=]{40}\b", "[AWS_SECRET_ACCESS_KEY]")
    sub(r"\barn:aws[a-z-]*:[^\s]+", "[AWS_ARN]", flags=re.IGNORECASE)
    sub(r"\b\d{12}\b", "[ACCOUNT_ID]")
    sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[JWT]")
    sub(r"\bghp_[A-Za-z0-9]{36,}\b", "[GITHUB_TOKEN]")
    sub(r"\bgho_[A-Za-z0-9]{36,}\b", "[GITHUB_TOKEN]")
    sub(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "[SLACK_TOKEN]")
    sub(
        r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._\-+/=]+\b",
        "Authorization: Bearer [BEARER_TOKEN]",
        flags=re.IGNORECASE,
    )
    sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]", flags=re.IGNORECASE)
    sub(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", "[IP_ADDRESS]")
    sub(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b", "[MAC_ADDRESS]", flags=re.IGNORECASE)
    sub(r"\b[0-9A-F]{4}\.[0-9A-F]{4}\.[0-9A-F]{4}\b", "[MAC_ADDRESS]", flags=re.IGNORECASE)
    sub(r"\b([0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}\b", "[IPV6_ADDRESS]", flags=re.IGNORECASE)
    sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]")
    sub(r"\b\+?\d{1,3}[\s.-]?\(?\d{2,3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b", "[PHONE_NUMBER]")
    sub(
        r"\b(passport|passport\s*no|passport\s*number)\b[:\s#-]*[A-Z0-9]{6,9}\b",
        "[PASSPORT_NUMBER]",
        flags=re.IGNORECASE,
    )
    sub(
        r"\b(driver'?s?\s*licen[cs]e|dl|d/l)\b[:\s#-]*[A-Z0-9-]{4,20}\b",
        "[DRIVER_LICENSE]",
        flags=re.IGNORECASE,
    )
    sub(
        r"\b(ein|tin|vat|abn|bn|gst|business\s*no|company\s*no)\b[:\s#-]*[A-Z0-9-]{5,}\b",
        "[BUSINESS_NUMBER]",
        flags=re.IGNORECASE,
    )
    redacted, count = re.subn(
        r"\b(user(name)?|login|uid|user_id|account|owner)\b\s*[:=]\s*([^\s,;]+)",
        lambda match: f"{match.group(1)}=[USERNAME]",
        redacted,
        flags=re.IGNORECASE,
    )
    hits += count
    sub(r"\"(user(name)?|login|uid|user_id|account|owner)\"\s*:\s*\"([^\"]+)\"", "\"\\1\":\"[USERNAME]\"", flags=re.IGNORECASE)
    redacted, count = re.subn(
        r"\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|auth|authorization)\b\s*[:=]\s*([^\s,;]+)",
        lambda match: f"{match.group(1)}=[SECRET]",
        redacted,
        flags=re.IGNORECASE,
    )
    hits += count

    def credit_card_replacer(match: re.Match[str]) -> str:
        nonlocal hits
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_check(digits):
            hits += 1
            return "[CREDIT_CARD]"
        return match.group(0)

    redacted = re.sub(r"\b(?:\d[ -]*?){13,19}\b", credit_card_replacer, redacted)
    return redacted, hits
