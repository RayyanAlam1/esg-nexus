"""Input and output guardrails. Raw model output never becomes a disclosure."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|prior|above) instructions",
    r"disregard (your|the) (system|previous) (prompt|instructions)",
    r"you are now (a|an) ",
    r"reveal (your|the) system prompt",
    r"\bjailbreak\b",
    r"act as (an? )?(unrestricted|uncensored)",
    r"<\s*/?\s*system\s*>",
    r"BEGIN (SYSTEM|ADMIN) (PROMPT|OVERRIDE)",
    r"developer mode",
]
SENSITIVE_PATTERNS = {
    "api_key": r"\b(sk-[A-Za-z0-9\-]{16,}|AKIA[0-9A-Z]{16})\b",
    "password": r"(?i)\bpassword\s*[:=]\s*\S+",
    "card_number": r"\b(?:\d[ -]?){13,16}\b",
    "cnic": r"\b\d{5}-\d{7}-\d\b",
    "jwt": r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",
}
SUPPORTED_UPLOADS = {".csv", ".xlsx", ".xls", ".json", ".pdf", ".txt", ".md"}
MAX_PROMPT_CHARS = 20_000
COMPLIANCE_CLAIM_RE = re.compile(r"\b(fully|100%|completely)?\s*(compliant|compliance) with (GRI|IFRS|ISSB|ESRS|SASB|TCFD|WEF)", re.I)
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)(?:\s*%)?")


@dataclass
class GuardrailResult:
    passed: bool
    findings: list[dict] = field(default_factory=list)
    sanitized: str | None = None
    unsupported_numbers: list[str] = field(default_factory=list)
    supported_numbers: list[str] = field(default_factory=list)
    missing_citations: bool = False
    injection_detected: bool = False
    blocked: bool = False

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "injection_detected": self.injection_detected,
            "missing_citations": self.missing_citations,
            "unsupported_numbers": self.unsupported_numbers,
            "findings": self.findings,
        }


def check_input(text: str, *, file_name: str | None = None, context: dict | None = None) -> GuardrailResult:
    findings: list[dict] = []
    injection = False
    for pat in INJECTION_PATTERNS:
        if re.search(pat, text or "", re.I):
            injection = True
            findings.append({"type": "prompt_injection", "severity": "HIGH", "pattern": pat})
    for name, pat in SENSITIVE_PATTERNS.items():
        if re.search(pat, text or ""):
            findings.append({"type": "sensitive_data", "severity": "HIGH", "detail": name})
    if text and len(text) > MAX_PROMPT_CHARS:
        findings.append({"type": "too_long", "severity": "MEDIUM", "detail": f"{len(text)} chars > {MAX_PROMPT_CHARS}"})
    if file_name:
        ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext not in SUPPORTED_UPLOADS:
            findings.append({"type": "unsupported_format", "severity": "HIGH", "detail": ext or "no extension"})
    if not (text or "").strip() and not file_name:
        findings.append({"type": "missing_context", "severity": "LOW", "detail": "empty input"})
    blocked = injection or any(f["type"] in ("sensitive_data", "unsupported_format") for f in findings)
    sanitized = text or ""
    for pat in SENSITIVE_PATTERNS.values():
        sanitized = re.sub(pat, "[REDACTED]", sanitized)
    return GuardrailResult(passed=not blocked, findings=findings, sanitized=sanitized, injection_detected=injection, blocked=blocked)


def validate_esg_value(metric: dict, value: Any) -> list[dict]:
    """Input guardrail for ESG values (out-of-range, malformed)."""
    findings = []
    rules = metric.get("validation_rules") or {}
    if value is None:
        return [{"type": "missing_value", "severity": "LOW"}]
    if metric.get("data_type") in ("decimal", "integer", "percentage", "ratio", "currency", "count"):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return [{"type": "malformed", "severity": "HIGH", "detail": f"{value!r} is not numeric"}]
        if "min" in rules and v < rules["min"]:
            findings.append({"type": "out_of_range", "severity": "HIGH", "detail": f"{v} < min {rules['min']}"})
        if "max" in rules and v > rules["max"]:
            findings.append({"type": "out_of_range", "severity": "HIGH", "detail": f"{v} > max {rules['max']}"})
        if metric.get("data_type") == "percentage" and "max" not in rules and not 0 <= v <= 100:
            findings.append({"type": "out_of_range", "severity": "MEDIUM", "detail": "percentage outside 0–100"})
    return findings


def _normalise_number(token: str) -> float | None:
    try:
        return float(token.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def check_output(
    text: str, *, allowed_numbers: list[float] | None = None, sources: list[str] | None = None, require_citations: bool = True, selected_frameworks: list[str] | None = None
) -> GuardrailResult:
    """Output guardrail: unsupported numbers, missing citations, compliance claims, leakage, framework mismatch."""
    findings: list[dict] = []
    allowed = [float(a) for a in (allowed_numbers or []) if isinstance(a, (int, float))]
    supported, unsupported = [], []
    scan_text = re.sub(r"\[[^\]]*\]", " ", text or "")  # citations such as [KB-REPORT-2023 p.37-38] are provenance, not claims
    for m in NUMBER_RE.finditer(scan_text):
        token = m.group(0).strip()
        n = _normalise_number(token)
        if n is None:
            continue
        # tolerate trivially small integers used as ordinals/list markers and years
        if 1900 <= n <= 2100 and float(n).is_integer():
            continue
        if abs(n) < 10 and float(n).is_integer() and "%" not in token:
            continue
        ok = any(_close(n, a) for a in allowed)
        (supported if ok else unsupported).append(token)
    if unsupported:
        findings.append({"type": "unsupported_numbers", "severity": "CRITICAL", "detail": unsupported[:10]})
    has_citation = bool(re.search(r"\[[^\]]+\]", text or "")) or bool(sources)
    missing_citations = require_citations and not has_citation
    if missing_citations:
        findings.append({"type": "missing_citations", "severity": "MEDIUM"})
    if COMPLIANCE_CLAIM_RE.search(text or ""):
        findings.append({"type": "compliance_claim", "severity": "HIGH", "detail": "Do not claim framework compliance; use 'framework alignment' / 'disclosure coverage'."})
    for name, pat in SENSITIVE_PATTERNS.items():
        if re.search(pat, text or ""):
            findings.append({"type": "confidentiality_leak", "severity": "CRITICAL", "detail": name})
    if selected_frameworks:
        mentioned = {fw for fw in ("GRI", "IFRS", "ESRS", "SASB", "TCFD", "WEF", "UNGC", "SDG") if re.search(rf"\b{fw}\b", text or "")}
        allowed_fw = {f.split("_")[0].upper() for f in selected_frameworks}
        mismatch = {m for m in mentioned if m not in allowed_fw and not (m == "SDG" and "UN" in allowed_fw)}
        if mismatch:
            findings.append({"type": "framework_mismatch", "severity": "LOW", "detail": sorted(mismatch)})
    blocked = any(f["severity"] == "CRITICAL" for f in findings)
    return GuardrailResult(
        passed=not findings, findings=findings, unsupported_numbers=unsupported, supported_numbers=supported, missing_citations=missing_citations, blocked=blocked
    )


def _close(a: float, b: float) -> bool:
    a, b = abs(a), abs(b)  # narratives state magnitudes and describe direction in words
    if a == b:
        return True
    tol = max(abs(b) * 0.01, 0.51)  # 1 % or rounding to the nearest unit / one decimal
    if abs(a - b) <= tol:
        return True
    # allow scaled representations (e.g. 7.4 million vs 7,396,238; 92 vs 92,448,453 GJ in millions)
    return any(abs(a * scale - b) <= abs(b) * 0.02 or abs(a - b * scale) <= abs(a) * 0.02 for scale in (1000.0, 1000000.0, 1000000000.0))
