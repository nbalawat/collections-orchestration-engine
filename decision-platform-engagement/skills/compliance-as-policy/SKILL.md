---
name: compliance-as-policy
description: Externalize every regulatory rule into a policy engine (OPA, Drools, Cedar) with citations to the specific regulation section. Emit compliance events on both PASS and FAIL. Trigger when the user mentions Reg F, FDCPA, GDPR, HIPAA, SOX, SR 11-7, compliance enforcement, regulatory exam, audit trail, or "how do we know we comply".
metadata:
  type: pattern
  tags: [compliance, governance, regulatory]
---

# Compliance as policy — externalize every rule with citations

## What this solves

Compliance enforcement buried in application code is invisible to auditors and impossible to audit. Externalizing rules into a policy engine produces a single file per rule, version-controlled, with regulation citations — which is exactly what a CFPB / OCC / FDIC / SOX / SOC 2 examiner wants to see.

## The pattern

For every regulation that applies:

1. **Write the rule in a policy engine** (OPA Rego is the reference; Drools, AWS Cedar, custom rules engines work the same way).
2. **Cite the specific regulation section** in a comment at the top of each rule.
3. **Evaluate the policy at every decision point** in the orchestration workflow.
4. **Emit a compliance event on both PASS and FAIL** — not just denials.
5. **Persist the full evaluation context** (input, output, rule cited, action blocked) to a WORM audit table.

## Why "compliance events on PASS too"

A common failure mode: emit a `ComplianceEvent` only when the policy denies an action. The block rate becomes 100% by construction (you never log the allowed ones), the metric is meaningless, and an auditor asking "show me every action your system took on this customer" gets a denial log, not a full evaluation log.

Fix: emit on both. Full evaluation history is the regulator's audit asset.

## Example: Reg F enforcement structure

A typical OPA module for collections, with citations:

```rego
package collections.compliance

# §1006.6(b)(1) — quiet hours
# Presumed unusual: before 8am or after 9pm in the consumer's local time.
quiet_channels := {"voice", "sms", "dialer", "digital"}  # not email (async)

quiet_hours_blocked(action) if {
    action.channel in quiet_channels
    input.customer_local_hour >= 21
}
quiet_hours_blocked(action) if {
    action.channel in quiet_channels
    input.customer_local_hour < 8
}

# §1006.14(b) — call frequency caps
# (1) No more than 7 calls within 7 consecutive days about a particular debt.
# (2) No call within 7 days of a telephone conversation in connection with the debt.
frequency_blocked("voice") if {
    input.voice_attempts_7d >= 7
}

# §1006.14(a) — total contact bound (UDAAP "unconscionable means")
frequency_blocked(_) if {
    input.total_attempts_7d >= 21
}

# Action gate — REST-callable wrapper that combines all rules
action_gate := action_allowed(input.action) if input.action
```

## What to compute and pass as policy input

The policy is only as good as its input. Don't hardcode placeholder values (see `mock-audit` skill). Compute real values from real event history:

| Input | How to compute |
|---|---|
| `voice_attempts_7d` | `COUNT(*) FROM customer_events WHERE channel='voice' AND direction='outbound' AND occurred_at > NOW() - 7d` |
| `customer_local_hour` | Derive from customer's stored timezone + workflow.now() |
| `total_attempts_7d` | Sum of all outbound attempts across channels |
| `failed_channels` | Channels with recent delivery failures |
| `conflicting_signals` | Recent inbound intents that disagree (e.g. PTP + DISPUTE) |
| `active_compliance_flags` | `SELECT flag_type FROM compliance_flags WHERE status='ACTIVE'` |

## Emit compliance event on both verdicts

```python
# After every action_gate evaluation:
comp_result = await call_opa("collections/compliance/action_gate", input)

# Emit on PASS too — full evaluation log, not denial log
await publish_compliance_event(
    customer_id=…,
    workflow_id=…,
    check_type="action_gate",
    passed=bool(comp_result.get("allowed", False)),
    rule_name=comp_result.get("reason", ""),
    details=comp_result,
    action_blocked=None if comp_result.get("allowed") else action.action_type,
    trace_id=current_trace_id,
)

if not comp_result.get("allowed"):
    return  # don't dispatch
```

## State-specific overlays

US bank engagements always need state-specific overlays beyond federal (NY DFS, CA Rosenthal, MA, TX, FL). Pattern: a base policy + per-state override modules with the same interface. Resolve per-customer based on `customer_profiles.address_state`.

## Cross-regulation overlays

| Regulation | Lives in |
|---|---|
| FDCPA / Reg F | `collections.compliance` |
| GDPR | `data.gdpr` |
| HIPAA | `healthcare.phi_access` |
| PCI-DSS | `payments.card_handling` |
| SR 11-7 (model risk) | `ml.model_governance` |

Each module gets its own file, its own citations, its own audit table.

## Common failure modes to avoid

- **Compliance computed in app code.** "if BANKRUPTCY in flags: return" is the smell. Move to OPA.
- **Hardcoded policy inputs.** `voice_attempts_7d=0` everywhere → frequency caps never fire → policy doesn't actually do anything.
- **Compliance events on FAIL only.** Block rate becomes 100%, evaluation history incomplete.
- **No citations.** A regulator reading the policy can't tell what rule it implements.
- **State-specific rules in if/else.** Add them as overlay modules with the same interface.

## Worked example from the reference engagement

Six Rego modules in `strategies/`:

- `compliance.rego` — federal Reg F §1006.6(b), §1006.14(b), full suppression, written-only, SCRA protections
- `transcript_audit.rego` — FDCPA §807 prohibited language, Mini-Miranda, recording disclosure
- `segmentation.rego` — DPD bucket × risk tier × value segment
- `treatment.rego` — action / message tone / AI review required
- `channel_routing.rego` — recommended channels with fallbacks
- `ai_guardrails.rego` — per-agent autonomy & escalation rules

`/strategy` UI surface in the platform shows the policy in action: which rules fire, in what proportion, with what reasons. Every evaluation persists to `strategy_audit_log` with full input + output → end-to-end audit trail.
