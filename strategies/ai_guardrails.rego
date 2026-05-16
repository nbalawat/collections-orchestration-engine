package collections.ai_guardrails

import rego.v1

# AI agent autonomy guardrails — what agents can do without human approval

# Digital Channel Agent autonomy
digital_agent_can_respond if {
	not compliance_block
	input.agent_type == "digital_channel"
}

digital_agent_can_capture_ptp if {
	digital_agent_can_respond
	input.ptp_amount <= input.total_past_due
	input.ptp_days <= 30
}

digital_agent_can_offer_payment_link if {
	digital_agent_can_respond
}

digital_agent_can_initiate_hardship if {
	digital_agent_can_respond
}

digital_agent_can_offer_arrangement if {
	digital_agent_can_respond
	input.arrangement_months <= 6
	input.arrangement_monthly <= input.balance * 0.20
}

# Actions that always require human approval
digital_agent_must_escalate if {
	input.intent == "THREAT_LEGAL"
}

digital_agent_must_escalate if {
	input.intent == "DISTRESS"
}

digital_agent_must_escalate if {
	input.intent == "COMPLAINT"
}

digital_agent_must_escalate if {
	input.settlement_amount > input.balance * 0.50
}

digital_agent_must_escalate if {
	input.confidence < 0.70
}

default digital_agent_must_escalate := false

# Copilot Agent: can always suggest, never act directly
copilot_can_suggest := true

copilot_can_auto_fill_forms if {
	input.agent_type == "copilot"
	input.form_type in ["ptp", "case_note", "call_summary"]
}

# Case Reasoning Agent: auto-execute within guardrails
case_agent_can_auto_execute if {
	input.agent_type == "case_reasoning"
	input.confidence >= 0.85
	not high_value_action
}

high_value_action if {
	input.action_type == "settlement_offer"
	input.settlement_amount > 10000
}

high_value_action if {
	input.action_type == "account_modification"
}

high_value_action if {
	input.action_type == "charge_off_recommendation"
}

default high_value_action := false

# Compliance block for all AI agents
compliance_block if {
	"BANKRUPTCY" in input.compliance_flags
}

compliance_block if {
	"CEASE_AND_DESIST" in input.compliance_flags
}

compliance_block if {
	"FRAUD" in input.compliance_flags
}

default compliance_block := false

# Master guardrail check
guardrail_check := result if {
	input.agent_type == "digital_channel"
	result := {
		"can_respond": digital_agent_can_respond,
		"can_capture_ptp": digital_agent_can_capture_ptp,
		"can_offer_payment_link": digital_agent_can_offer_payment_link,
		"can_initiate_hardship": digital_agent_can_initiate_hardship,
		"can_offer_arrangement": digital_agent_can_offer_arrangement,
		"must_escalate": digital_agent_must_escalate,
		"compliance_block": compliance_block,
	}
}

guardrail_check := result if {
	input.agent_type == "case_reasoning"
	result := {
		"can_auto_execute": case_agent_can_auto_execute,
		"high_value_action": high_value_action,
		"compliance_block": compliance_block,
	}
}

guardrail_check := result if {
	input.agent_type == "copilot"
	result := {
		"can_suggest": copilot_can_suggest,
		"can_auto_fill": copilot_can_auto_fill_forms,
		"compliance_block": compliance_block,
	}
}

default digital_agent_can_respond := false

default digital_agent_can_capture_ptp := false

default digital_agent_can_offer_payment_link := false

default digital_agent_can_initiate_hardship := false

default digital_agent_can_offer_arrangement := false

default copilot_can_auto_fill_forms := false

default case_agent_can_auto_execute := false
