package collections.compliance

import rego.v1

# Compliance rules with citations to FDCPA / Reg F.

# ─── Full suppression ────────────────────────────────────────────────

full_suppression if { "BANKRUPTCY" in input.compliance_flags }
full_suppression if { "DECEASED" in input.compliance_flags }
full_suppression if { "IDENTITY_THEFT" in input.compliance_flags }
default full_suppression := false

# ─── Channel restrictions ────────────────────────────────────────────

written_only if { "CEASE_AND_DESIST" in input.compliance_flags }
written_only if { "ATTORNEY_REPRESENTED" in input.compliance_flags }
default written_only := false

# ─── §1006.6(b) Quiet hours ──────────────────────────────────────────
# 8 am – 9 pm local. Applies to ALL real-time channels.

quiet_channels := {"voice", "sms", "dialer", "digital"}

quiet_hours_blocked(action) if {
    action.channel in quiet_channels
    input.customer_local_hour >= 21
}
quiet_hours_blocked(action) if {
    action.channel in quiet_channels
    input.customer_local_hour < 8
}

# ─── §1006.14(b) Frequency caps ──────────────────────────────────────

# (1) No more than 7 calls within 7 consecutive days about a particular debt.
frequency_blocked("voice") if { input.voice_attempts_7d >= 7 }
frequency_blocked("dialer") if { input.voice_attempts_7d >= 7 }

# Reasonable bounds on non-call channels
frequency_blocked("sms")   if { input.channel_attempts_7d.sms   >= 10 }
frequency_blocked("email") if { input.channel_attempts_7d.email >= 14 }

# §1006.14(a) UDAAP — total contact bound
frequency_blocked(_) if { input.total_attempts_7d >= 21 }

default frequency_blocked(_) := false

# ─── Action gate (REST-callable wrapper) ─────────────────────────────

action_gate := action_allowed(input.action) if input.action

action_allowed(action) := result if {
    not full_suppression
    not channel_blocked(action.channel)
    not quiet_hours_blocked(action)
    not frequency_blocked(action.channel)
    result := { "allowed": true, "reason": "all checks passed" }
}

action_allowed(action) := result if {
    full_suppression
    result := { "allowed": false, "reason": "full suppression active", "flag": suppression_flag }
}

action_allowed(action) := result if {
    quiet_hours_blocked(action)
    result := { "allowed": false, "reason": "quiet hours (8am-9pm local) — §1006.6(b)" }
}

action_allowed(action) := result if {
    frequency_blocked(action.channel)
    result := { "allowed": false, "reason": "frequency cap exceeded — §1006.14(b)" }
}

# ─── Helpers ─────────────────────────────────────────────────────────

channel_blocked("voice")  if { written_only }
channel_blocked("dialer") if { written_only }
channel_blocked("sms")    if { written_only }
default channel_blocked(_) := false

suppression_flag := "BANKRUPTCY" if { "BANKRUPTCY" in input.compliance_flags }
suppression_flag := "DECEASED"   if { "DECEASED" in input.compliance_flags }
suppression_flag := "IDENTITY_THEFT" if { "IDENTITY_THEFT" in input.compliance_flags }
