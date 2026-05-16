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

# Quiet hours: 9pm-8am customer local time
quiet_hours_blocked(action) if {
	action.channel != "email"
	input.customer_local_hour >= 21
}

quiet_hours_blocked(action) if {
	action.channel != "email"
	input.customer_local_hour < 8
}

# Frequency: Reg F 7-in-7 for voice
frequency_blocked("voice") if {
	input.voice_attempts_7d >= 7
}

frequency_blocked("dialer") if {
	input.voice_attempts_7d >= 7
}

default channel_blocked(_) := false

default quiet_hours_blocked(_) := false

default frequency_blocked(_) := false

# Helper: can_contact is the inverse of full_suppression
default can_contact := true

can_contact := false if {
	full_suppression
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
