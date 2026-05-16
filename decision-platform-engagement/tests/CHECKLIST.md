# Manual behavioral test checklist

The automated structural tests verify the plugin is well-formed. This checklist is for the behavioral tests that require running Claude against real scenarios. Walk through each item before tagging a release.

## Setup (one-time)

```bash
# Install Claude Code CLI
npm i -g @anthropic-ai/claude-code

# Set API key (or OAuth token)
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Install the plugin
cp -R decision-platform-engagement ~/.claude/plugins/

# Restart Claude Code so it discovers the plugin
```

---

## Skill trigger tests (10 skills × 4 scenarios each)

For each skill, run the should-trigger and should-not-trigger prompts from `tests/scenarios/skill-triggers.json`. Verify Claude references the skill (or doesn't) in its response.

### mock-audit

- [ ] **Triggers:** "I need to audit this codebase before adding new features. Find every mock and stub inside the orchestration boundary."
- [ ] **Triggers:** "Is this code real or is it a demo? I want to know what's faked."
- [ ] **Triggers:** "We're claiming this is production-ready but I'm suspicious. Can you check?"
- [ ] **Triggers:** "Help me find hidden mocks before this goes to a stakeholder review."
- [ ] **Does NOT trigger:** "Refactor this function to be more readable."
- [ ] **Does NOT trigger:** "Add error handling to the API endpoints."
- [ ] **Does NOT trigger:** "Generate unit tests for the customer service module."

### structured-ai-decisions
- [ ] Triggers: "I'm building a Claude agent for customer support. How do I make its decisions auditable?"
- [ ] Triggers: "We're getting AI responses with hardcoded confidence=0.85. That's a smell, right?"
- [ ] Does NOT trigger: "What's the difference between asyncio and threading in Python?"

### medallion-lakehouse
- [ ] Triggers: "We need to set up a data lake. Bronze/silver/gold pattern on S3."
- [ ] Triggers: "How do I write Kafka events to Parquet files for analytics queries?"
- [ ] Does NOT trigger: "How do I configure Kafka producers?"

### compliance-as-policy
- [ ] Triggers: "We need to enforce Reg F §1006.6 quiet hours. Where does the rule live?"
- [ ] Does NOT trigger: "Generate a TypeScript type from this JSON schema."

### worm-audit-trail
- [ ] Triggers: "We need SOC 2 evidence — the audit trail can't be tampered with."
- [ ] Does NOT trigger: "Add an index to the user_sessions table."

### champion-challenger
- [ ] Triggers: "We want to A/B test two strategy versions safely. What's the framework?"
- [ ] Does NOT trigger: "What's the best way to mock an LLM call in tests?"

### data-lineage-ui
- [ ] Triggers: "Build a feature that traces one event across Kafka, Postgres, and S3 tiers."
- [ ] Does NOT trigger: "Add a dropdown to the customer filter."

### stakeholder-driven-ui
- [ ] Triggers: "We're building dashboards for the CRO, CCO, and CTO. Should it be one page or many?"
- [ ] Does NOT trigger: "Convert this Tailwind class to CSS Modules."

### narrative-summarization
- [ ] Triggers: "I want the AI to summarize a customer's full journey, not just dump events."
- [ ] Does NOT trigger: "Set up streaming responses from the API."

### cost-observability
- [ ] Triggers: "What does Claude cost us per day? Build me a dashboard."
- [ ] Does NOT trigger: "How do I deploy this to ECS?"

---

## Command artifact tests (6 commands)

### /engagement-init

```bash
mkdir -p /tmp/test-engagement && cd /tmp/test-engagement
claude
# In Claude: /engagement-init
# Answer the questionnaire with the synthetic data from
# tests/scenarios/command-specs.json → commands.engagement-init.simulated_answers
```

Verify:
- [ ] `docs/engagement-profile.md` was created
- [ ] Contains all 9 expected sections (Stakeholders, Regulatory frame, Tech stack, etc.)
- [ ] References the answers we gave (CRO, Temporal, PostgreSQL, Kafka, Reg F)
- [ ] Recommends a preset
- [ ] Lists top 5 skills
- [ ] Names `/engagement-audit` as the next command

### /engagement-audit

```bash
cp -R decision-platform-engagement/tests/fixtures/synthetic-codebase /tmp/test-audit
cd /tmp/test-audit
echo '> Orchestration boundary: only services/channel_simulator.py may be simulated. Everything else must be real.' > docs/engagement-profile.md
claude
# In Claude: /engagement-audit
```

Verify:
- [ ] `docs/audit-findings.md` was created
- [ ] Has Critical / High / Medium / Low sections
- [ ] Found all 5 planted mocks (`fake_agent.py`, `compliance_check.py`, `stub_dispatcher.py`, `audit_log.py`, `channel_writer.py`)
- [ ] Severity ranking is reasonable (fake_agent = Critical; channel_writer = Medium)
- [ ] Did NOT flag the real files (`real_publisher.py`, `lookup_account.py`)
- [ ] Includes a "Recommended de-mock sequence" section

### /engagement-stakeholders

```bash
mkdir -p /tmp/test-stakeholders/docs
cp tests/fixtures/engagement-profile-bank-collections.md /tmp/test-stakeholders/docs/engagement-profile.md
cd /tmp/test-stakeholders
claude
# In Claude: /engagement-stakeholders
```

Verify:
- [ ] `docs/capability-matrix.md` was created
- [ ] Has ≥ 8 matrix rows
- [ ] Every persona has ≥ 2 capability mappings
- [ ] Lists top 5 capabilities for demo emphasis

### /engagement-demo-flow

After running stakeholders test:
- [ ] Run `/engagement-demo-flow` in the same directory
- [ ] `docs/demo-flow.md` is created
- [ ] Has ≥ 6 stops
- [ ] Each stop has persona tags + duration + script + walk-out one-liner
- [ ] Total duration matches budget

### /engagement-brief

After running stakeholders + demo-flow:
- [ ] Run `/engagement-brief`
- [ ] `docs/stakeholder-brief.html` is created
- [ ] Opens in a browser cleanly
- [ ] Self-contained (no external resources)
- [ ] Has all 8 sections
- [ ] Print preview looks clean

### /engagement-roadmap

After full set:
- [ ] Run `/engagement-roadmap`
- [ ] `docs/roadmap.md` is created
- [ ] Has all 3 horizons (4 weeks / 3 months / 9 months)
- [ ] Each item has effort + rationale
- [ ] Sequencing rationale section explains compounding logic

---

## Mock-auditor subagent

```bash
cd decision-platform-engagement/tests/fixtures/synthetic-codebase
claude
# In Claude: "Use the mock-auditor agent to find every mock in this directory. The orchestration boundary is in BOUNDARY.md."
```

Verify:
- [ ] Agent finds all 5 planted mocks
- [ ] Severity ranking matches the README
- [ ] Findings document includes file:line citations
- [ ] Does NOT flag the real files

---

## Engagement-discoverer subagent

```bash
mkdir -p /tmp/test-discoverer && cd /tmp/test-discoverer
claude
# In Claude: "Use the engagement-discoverer agent to walk me through a new engagement for a US healthcare company doing claims processing."
```

Verify:
- [ ] Agent uses AskUserQuestion (not bare text questions)
- [ ] Asks in logical groups (not 23 questions in one wall)
- [ ] Produces `docs/engagement-profile.md` at the end
- [ ] Recommends `Insurance claims` preset from variability-dimensions.md
- [ ] Recommends skills appropriate to healthcare (compliance-as-policy, narrative-summarization, structured-ai-decisions)

---

## Regression check

After any change to the plugin:

- [ ] `./tests/run-evals.sh --structural` returns 0
- [ ] All 10 skill triggers from this checklist still fire
- [ ] All 6 commands still produce well-formed artifacts
- [ ] The `mock-auditor` agent still finds all 5 planted mocks

---

## Cost estimate

- Skill trigger tests: ~$0.20 total (10 skills × 4 prompts × $0.005)
- Command tests: ~$0.30 total (6 commands × $0.05)
- Subagent tests: ~$0.20 total
- **Full behavioral run: ~$0.70**

Run before each tagged release. Skip on routine commits.
