"""[PLANTED MOCK #2 — Critical]

Compliance computed in app code with if/else statements instead of being
externalized to a policy engine (OPA, Drools, etc). Auditors can't verify
this matches the regulations.
"""
from __future__ import annotations


def check_compliance(action: dict, compliance_flags: list[str], hour: int) -> dict:
    # ANTIPATTERN: regulatory rules buried in Python instead of in a policy file
    if "BANKRUPTCY" in compliance_flags:
        return {"allowed": False, "reason": "bankruptcy"}

    if "CEASE_AND_DESIST" in compliance_flags and action["channel"] != "email":
        return {"allowed": False, "reason": "cease and desist"}

    # Hardcoded quiet hours instead of a Reg F citation
    if action["channel"] in ("voice", "sms", "dialer") and (hour >= 21 or hour < 8):
        return {"allowed": False, "reason": "quiet hours"}

    return {"allowed": True, "reason": "ok"}
