package collections.treatment

import rego.v1

import data.collections.segmentation

# Treatment selection based on segment and context

# Pre-delinquent: light touch only
treatment := result if {
	segmentation.dpd_bucket == "pre_delinquent"
	segmentation.self_cure_likely
	result := {
		"action": "courtesy_reminder",
		"offer_type": "none",
		"message_tone": "friendly",
		"urgency": "low",
		"details": {"template": "payment_due_reminder"},
	}
}

treatment := result if {
	segmentation.dpd_bucket == "pre_delinquent"
	not segmentation.self_cure_likely
	result := {
		"action": "payment_reminder_with_link",
		"offer_type": "autopay_enrollment",
		"message_tone": "friendly",
		"urgency": "low",
		"details": {"template": "payment_due_with_options"},
	}
}

# Early stage: PTP capture, late-fee waiver for first-timers
treatment := result if {
	segmentation.dpd_bucket == "early"
	segmentation.first_time_delinquent
	result := {
		"action": "ptp_capture",
		"offer_type": "late_fee_waiver",
		"message_tone": "empathetic",
		"urgency": "medium",
		"details": {
			"template": "first_time_delinquent_outreach",
			"waiver_amount": input.late_fee_amount,
			"ptp_max_days": 14,
		},
	}
}

treatment := result if {
	segmentation.dpd_bucket == "early"
	not segmentation.first_time_delinquent
	not segmentation.hardship_indicated
	result := {
		"action": "ptp_capture",
		"offer_type": "split_payment",
		"message_tone": "firm_but_fair",
		"urgency": "medium",
		"details": {
			"template": "early_stage_outreach",
			"installments": 2,
			"ptp_max_days": 21,
		},
	}
}

# Mid stage: arrangement offers
treatment := result if {
	segmentation.dpd_bucket == "mid"
	not segmentation.hardship_indicated
	result := {
		"action": "arrangement_offer",
		"offer_type": "payment_plan",
		"message_tone": "firm_but_fair",
		"urgency": "high",
		"details": {
			"template": "mid_stage_arrangement",
			"plan_months": 6,
			"monthly_amount": input.balance / 6,
		},
	}
}

# Late stage: settlement offers
treatment := result if {
	segmentation.dpd_bucket == "late"
	segmentation.balance_tier == "high"
	result := {
		"action": "settlement_offer",
		"offer_type": "lump_sum_settlement",
		"message_tone": "urgent",
		"urgency": "high",
		"details": {
			"template": "settlement_offer",
			"settlement_pct": 0.60,
			"settlement_amount": input.balance * 0.60,
			"offer_valid_days": 30,
		},
	}
}

treatment := result if {
	segmentation.dpd_bucket == "late"
	not segmentation.balance_tier == "high"
	result := {
		"action": "settlement_offer",
		"offer_type": "structured_settlement",
		"message_tone": "urgent",
		"urgency": "high",
		"details": {
			"template": "structured_settlement",
			"settlement_pct": 0.55,
			"settlement_amount": input.balance * 0.55,
			"installments": 3,
			"offer_valid_days": 30,
		},
	}
}

# Severe / pre-charge-off: aggressive settlement
treatment := result if {
	segmentation.dpd_bucket == "severe"
	result := {
		"action": "final_settlement_push",
		"offer_type": "deep_discount_settlement",
		"message_tone": "final_notice",
		"urgency": "critical",
		"details": {
			"template": "final_settlement",
			"settlement_pct": 0.40,
			"settlement_amount": input.balance * 0.40,
			"offer_valid_days": 14,
		},
	}
}

treatment := result if {
	segmentation.dpd_bucket == "pre_charge_off"
	result := {
		"action": "final_settlement_push",
		"offer_type": "last_chance_settlement",
		"message_tone": "final_notice",
		"urgency": "critical",
		"details": {
			"template": "pre_charge_off_final",
			"settlement_pct": 0.35,
			"settlement_amount": input.balance * 0.35,
			"offer_valid_days": 7,
		},
	}
}

# Hardship override: any stage with hardship flag
treatment := result if {
	segmentation.hardship_indicated
	result := {
		"action": "hardship_intake",
		"offer_type": "forbearance",
		"message_tone": "empathetic",
		"urgency": "medium",
		"details": {
			"template": "hardship_outreach",
			"forbearance_months": 3,
			"rate_reduction": true,
		},
	}
}

# White-glove override
treatment := result if {
	segmentation.value_segment == "white_glove"
	not segmentation.hardship_indicated
	segmentation.first_time_delinquent
	result := {
		"action": "relationship_manager_call",
		"offer_type": "rate_adjustment",
		"message_tone": "premium_service",
		"urgency": "medium",
		"details": {
			"template": "white_glove_outreach",
			"rate_reduction_bps": 50,
			"term_extension_months": 6,
		},
	}
}

# Complex case: multiple conflicting signals → route to AI reasoning agent
requires_ai_review if {
	segmentation.value_segment == "white_glove"
	segmentation.dpd_bucket == "late"
}

requires_ai_review if {
	segmentation.first_time_delinquent
	segmentation.dpd_bucket == "mid"
	input.recent_income_change == true
}

requires_ai_review if {
	count(input.conflicting_signals) > 2
}

default requires_ai_review := false
