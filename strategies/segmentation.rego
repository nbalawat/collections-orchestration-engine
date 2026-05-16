package collections.segmentation

import rego.v1

# Determine DPD bucket
dpd_bucket := "pre_delinquent" if {
	input.dpd >= 1
	input.dpd <= 29
}

dpd_bucket := "early" if {
	input.dpd >= 30
	input.dpd <= 59
}

dpd_bucket := "mid" if {
	input.dpd >= 60
	input.dpd <= 89
}

dpd_bucket := "late" if {
	input.dpd >= 90
	input.dpd <= 119
}

dpd_bucket := "severe" if {
	input.dpd >= 120
	input.dpd <= 179
}

dpd_bucket := "pre_charge_off" if {
	input.dpd >= 180
}

dpd_bucket := "current" if {
	input.dpd < 1
}

# Risk tier based on behavioral/risk score
risk_tier := "high_risk" if {
	input.risk_score < 500
}

risk_tier := "medium_risk" if {
	input.risk_score >= 500
	input.risk_score < 650
}

risk_tier := "low_risk" if {
	input.risk_score >= 650
}

# Balance tier
balance_tier := "low" if {
	input.balance < 5000
}

balance_tier := "mid" if {
	input.balance >= 5000
	input.balance < 25000
}

balance_tier := "high" if {
	input.balance >= 25000
}

# Customer value segment
value_segment := "white_glove" if {
	input.relationship_value == "platinum"
}

value_segment := "white_glove" if {
	input.relationship_value == "high"
	input.relationship_tenure_years >= 10
}

value_segment := "high_value" if {
	input.relationship_value == "high"
}

value_segment := "standard" if {
	not input.relationship_value == "platinum"
	not input.relationship_value == "high"
}

# Self-cure probability tier
self_cure_likely if {
	dpd_bucket == "pre_delinquent"
	risk_tier == "low_risk"
}

self_cure_likely if {
	dpd_bucket == "early"
	input.prior_cures >= 2
	risk_tier != "high_risk"
}

# First-time delinquent flag
first_time_delinquent if {
	input.prior_delinquencies == 0
}

# Hardship indicator
hardship_indicated if {
	input.hardship_flag == true
}

# Final segment assignment
segment := result if {
	result := {
		"dpd_bucket": dpd_bucket,
		"risk_tier": risk_tier,
		"balance_tier": balance_tier,
		"value_segment": value_segment,
		"self_cure_likely": self_cure_likely,
		"first_time_delinquent": first_time_delinquent,
		"hardship_indicated": hardship_indicated,
	}
}

default self_cure_likely := false

default first_time_delinquent := false

default hardship_indicated := false
