package collections.compliance

import rego.v1

# Compliance rules — these are non-negotiable guardrails

# Full suppression: no contact of any kind
full_suppression if {
	"BANKRUPTCY" in input.compliance_flags
}

full_suppression if {
	"DECEASED" in input.compliance_flags
}

full_suppression if {
	"IDENTITY_THEFT" in input.compliance_flags
}

default full_suppression := false

# Channel restriction: written-only
written_only if {
	"CEASE_AND_DESIST" in input.compliance_flags
}

written_only if {
	"ATTORNEY_REPRESENTED" in input.compliance_flags
}

default written_only := false

# SCRA protections
scra_protected if {
	"SCRA_MILITARY" in input.compliance_flags
}

default scra_protected := false

# Dispute freeze
dispute_active if {
	"DISPUTE" in input.compliance_flags
}

default dispute_active := false

# Disaster forbearance
disaster_forbearance if {
	"DISASTER" in input.compliance_flags
}

default disaster_forbearance := false

# Fraud investigation
fraud_investigation if {
	"FRAUD" in input.compliance_flags
}

default fraud_investigation := false

# Can we take this specific action?
action_allowed(action) := result if {
	not full_suppression
	not dispute_active
	not fraud_investigation
	not disaster_forbearance

	channel := action.channel
	not channel_blocked(channel)
	not quiet_hours_blocked(action)
	not frequency_blocked(channel)

	result := {
		"allowed": true,
		"reason": "all checks passed",
	}
}

action_allowed(action) := result if {
	full_suppression
	result := {
		"allowed": false,
		"reason": "full suppression active",
		"flag": suppression_flag,
	}
}

action_allowed(action) := result if {
	dispute_active
	result := {
		"allowed": false,
		"reason": "dispute investigation in progress",
		"flag": "DISPUTE",
	}
}

action_allowed(action) := result if {
	fraud_investigation
	result := {
		"allowed": false,
		"reason": "fraud investigation in progress",
		"flag": "FRAUD",
	}
}

action_allowed(action) := result if {
	disaster_forbearance
	result := {
		"allowed": false,
		"reason": "disaster forbearance active",
		"flag": "DISASTER",
	}
}

# Helper: identify which flag caused suppression
suppression_flag := "BANKRUPTCY" if {
	"BANKRUPTCY" in input.compliance_flags
}

suppression_flag := "DECEASED" if {
	"DECEASED" in input.compliance_flags
}

suppression_flag := "IDENTITY_THEFT" if {
	"IDENTITY_THEFT" in input.compliance_flags
}

# Channel-level blocks
channel_blocked("voice") if {
	written_only
}

channel_blocked("dialer") if {
	written_only
}

channel_blocked("sms") if {
	written_only
}

# Quiet hours per Reg F §1006.6(b)(1): no communication "at any unusual time or
# place", presumed unusual before 8am or after 9pm in the consumer's local time.
# Applies to ALL real-time channels — voice, SMS, dialer. Email is exempt because
# it's not synchronous/disruptive.
quiet_channels := {"voice", "sms", "dialer", "digital"}

quiet_hours_blocked(action) if {
	action.channel in quiet_channels
	input.customer_local_hour >= 21
}

quiet_hours_blocked(action) if {
	action.channel in quiet_channels
	input.customer_local_hour < 8
}

# Frequency: Reg F §1006.14(b) — call frequency caps.
#   (1) No more than 7 calls within 7 consecutive days about a particular debt.
#   (2) No call within 7 days of a telephone conversation in connection with the debt.
# We model the 7-in-7 cap for voice and dialer (both initiate a phone connection).
frequency_blocked("voice") if {
	input.voice_attempts_7d >= 7
}

frequency_blocked("dialer") if {
	input.voice_attempts_7d >= 7
}

# Reg F also expects reasonable limits on non-call channels. We enforce a generous
# cap to prevent runaway SMS/email bombardment and to support state overlays.
frequency_blocked("sms") if {
	input.channel_attempts_7d.sms >= 10
}

frequency_blocked("email") if {
	input.channel_attempts_7d.email >= 14
}

# Total contact attempts across all channels — sanity bound to avoid harassment
# claims under UDAAP / §1006.14(a) "unconscionable means" prohibition.
frequency_blocked(_) if {
	input.total_attempts_7d >= 21
}

default channel_blocked(_) := false

default quiet_hours_blocked(_) := false

default frequency_blocked(_) := false

# Helper: can_contact is the inverse of full_suppression
default can_contact := true

can_contact := false if {
	full_suppression
}

# REST-callable wrapper: reads input.action and calls the action_allowed function.
# The function form `action_allowed(action)` cannot be queried directly via the
# data API; this rule provides a fixed entry point that the orchestrator can POST to.
action_gate := action_allowed(input.action) if {
	input.action
}

# Comprehensive compliance check result
check := result if {
	result := {
		"full_suppression": full_suppression,
		"written_only": written_only,
		"scra_protected": scra_protected,
		"dispute_active": dispute_active,
		"disaster_forbearance": disaster_forbearance,
		"fraud_investigation": fraud_investigation,
		"can_contact": can_contact,
		"active_flags": input.compliance_flags,
	}
}
