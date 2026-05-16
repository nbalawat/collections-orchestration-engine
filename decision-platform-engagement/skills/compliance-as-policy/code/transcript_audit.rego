package collections.compliance

import rego.v1

# Transcript audit — pattern-based checks against an interaction transcript.
# Used by the Quality & Compliance AI agent to scan voice / digital transcripts
# for FDCPA, Reg F, and disclosure-rule violations.

transcript := lower(input.transcript)

# ─── FDCPA §807 prohibited language ──────────────────────────────────

prohibited_phrase contains phrase if {
    phrases := [
        "i'll have you arrested",
        "we will sue you",
        "you'll go to jail",
        "this is your final warning",
        "you are committing fraud",
    ]
    some phrase in phrases
    contains(transcript, phrase)
}

# ─── Mini-Miranda (required for first-party collections calls) ───────

mini_miranda_present if {
    contains(transcript, "this is an attempt to collect a debt")
}
mini_miranda_present if {
    contains(transcript, "for the purpose of collecting a debt")
}

# ─── Recording disclosure ────────────────────────────────────────────

recording_disclosure_present if {
    contains(transcript, "this call may be recorded")
}
recording_disclosure_present if {
    contains(transcript, "call is being recorded")
}

# ─── Cease-and-desist violation ──────────────────────────────────────

cease_violation if {
    "CEASE_AND_DESIST" in input.active_flags
    input.transcript_length > 0
    input.channel != "email"
}

# ─── Findings ─────────────────────────────────────────────────────────

findings contains finding if {
    count(prohibited_phrase) > 0
    finding := {
        "rule": "fdcpa_807_prohibited_language",
        "severity": "critical",
        "phrases_detected": prohibited_phrase,
    }
}

findings contains finding if {
    input.channel == "voice"
    input.transcript_length > 50
    not mini_miranda_present
    finding := {
        "rule": "mini_miranda_disclosure_missing",
        "severity": "high",
        "note": "First-party voice contact missing required mini-Miranda disclosure",
    }
}

findings contains finding if {
    input.channel == "voice"
    input.transcript_length > 50
    not recording_disclosure_present
    finding := {
        "rule": "recording_disclosure_missing",
        "severity": "medium",
        "note": "Voice transcript missing recording disclosure",
    }
}

findings contains finding if {
    cease_violation
    finding := {
        "rule": "cease_and_desist_violation",
        "severity": "critical",
        "note": "Outbound contact attempted on customer with active CEASE_AND_DESIST flag",
    }
}

default transcript_audit := {
    "passed": true,
    "findings": [],
    "critical_count": 0,
}

transcript_audit := result if {
    count(findings) > 0
    critical := [f | f := findings[_]; f.severity == "critical"]
    result := {
        "passed": count(critical) == 0,
        "findings": findings,
        "critical_count": count(critical),
        "high_count": count([f | f := findings[_]; f.severity == "high"]),
        "medium_count": count([f | f := findings[_]; f.severity == "medium"]),
    }
}
