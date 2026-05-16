package collections.channel_routing

import rego.v1

import data.collections.segmentation

# Channel cascade order based on segment
default next_channels := ["sms", "email"]

next_channels := ["voice"] if {
	segmentation.value_segment == "white_glove"
}

next_channels := ["sms", "email", "voice"] if {
	segmentation.dpd_bucket == "early"
	segmentation.value_segment != "white_glove"
}

next_channels := ["sms", "voice", "email"] if {
	segmentation.dpd_bucket == "mid"
}

next_channels := ["voice", "dialer", "sms"] if {
	segmentation.dpd_bucket == "late"
}

next_channels := ["dialer", "voice"] if {
	segmentation.dpd_bucket == "severe"
}

next_channels := ["dialer", "voice"] if {
	segmentation.dpd_bucket == "pre_charge_off"
}

# Channel escalation: skip channels that already failed
effective_channels := [ch |
	some ch in next_channels
	not channel_failed(ch)
]

channel_failed(ch) if {
	some failed in input.failed_channels
	failed == ch
}

# Frequency caps (per rolling 7-day window)
frequency_cap := {"sms": 3, "email": 2, "voice": 1, "dialer": 2}

channel_allowed(ch) if {
	cap := frequency_cap[ch]
	count := input.channel_attempts_7d[ch]
	count < cap
}

channel_allowed(ch) if {
	not input.channel_attempts_7d[ch]
}

# Quiet hours check (simplified: 9pm-8am customer local time)
quiet_hours_active if {
	input.customer_local_hour >= 21
}

quiet_hours_active if {
	input.customer_local_hour < 8
}

default quiet_hours_active := false

# Reg F: max 7 call attempts per 7-day rolling window
reg_f_call_limit_reached if {
	input.voice_attempts_7d >= 7
}

default reg_f_call_limit_reached := false

# Helper: can_contact is the inverse of quiet_hours_active
default can_contact := true

can_contact := false if {
	quiet_hours_active
}

# Final routing decision
routing := result if {
	result := {
		"recommended_channels": effective_channels,
		"quiet_hours_active": quiet_hours_active,
		"reg_f_limited": reg_f_call_limit_reached,
		"can_contact": can_contact,
	}
}
