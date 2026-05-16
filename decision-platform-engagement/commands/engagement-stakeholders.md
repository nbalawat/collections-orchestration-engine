---
name: engagement-stakeholders
description: Map platform capabilities onto the specific stakeholders in this engagement. Produces a capability × stakeholder matrix that drives demo flow and brief content.
---

# /engagement-stakeholders

You are mapping platform capabilities onto the specific stakeholders in this engagement. The output is a **proof matrix**: capability × stakeholder × verifiable proof point.

## Pre-requisites

Read `docs/engagement-profile.md`. Key inputs:
- Demo buyer (C1)
- Room composition (C2)
- AI maturity (C3)

If those are missing, ask the user OR run `/engagement-init` first.

Read `docs/stakeholder-archetypes.md` in this plugin for the eight standard personas and their first ten questions.

## The mapping method

### 1. Identify the personas

From the engagement profile, build the list of personas you must satisfy. Typically 5-8 personas; include at minimum:

- The demo buyer (always)
- 2-3 other room-composition stakeholders
- Audit / SOX / SOC 2 (if regulatory scope warrants)

### 2. List the platform capabilities

Enumerate what the platform actually does. Use the canonical 8 capability domains:

1. Real-time orchestration
2. Policy engine
3. AI agent platform
4. Compliance & audit
5. Data lakehouse
6. Risk & ML
7. Observability
8. Stakeholder UI

For each capability that exists in your engagement, write a one-line description.

### 3. Map each capability to the personas who care

For each (capability, persona) pair, ask: "Does this capability answer one of this persona's first ten questions?"

If yes, capture:
- The specific concern the capability answers (one phrase)
- The verifiable proof point (a number, a screen, a SQL query — something the persona can verify in 30 seconds)

### 4. Write the matrix

Output to `docs/capability-matrix.md`:

```markdown
# Capability × stakeholder proof matrix

## Personas in scope

- Persona 1: <name> · <role> · <their main concern>
- Persona 2: …

## Matrix

| Capability | Concern it answers | Stakeholder | Proof point |
|---|---|---|---|
| <capability> | <concern> | <persona> | <verifiable number / screen / query> |
…

## Coverage check

For each persona, list which capabilities they map to. Flag any persona with < 2 capability mappings — they may not have a clear story.

## Recommended demo emphasis

Top 5 capabilities by stakeholder weight (capability appears in matrix rows weighted by stakeholder importance).
```

### 5. Coverage check

After the matrix, do this:

- **Does every persona have at least 2 proof points?** If not, the demo will fall flat for them. Recommend additional capabilities to build or different framing.
- **Are there capabilities that map to nobody?** Those are demo bloat — consider cutting from the flow.
- **Is there a stakeholder whose concerns aren't captured?** The matrix may be incomplete — go back to the persona profile.

## Output guarantees

- `docs/capability-matrix.md` exists and is well-formed
- Every persona has at least 2 capabilities mapped
- The "Recommended demo emphasis" section names the top 5 capabilities

## What to do next

After the matrix, the natural next command is `/engagement-demo-flow` to turn the capability emphasis into an N-minute demo path.
