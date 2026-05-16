# Plugin test harness

Two levels of tests:

1. **Structural** — fast, local, no Claude API needed. Validates that skills + commands + agents + templates are well-formed (correct frontmatter, required sections, valid HTML, etc.). Run on every change.
2. **Behavioral** — slower, requires Claude API access. Validates that skills trigger when they should, commands produce the expected artifacts, and agents follow the protocol. Run before tagging a release.

## Quick start

```bash
# Structural tests only (always free, ~5 seconds)
./tests/run-evals.sh --structural

# Full evals including behavioral (requires ANTHROPIC_API_KEY, ~5 min, costs ~$0.50)
./tests/run-evals.sh --all

# Single skill test
./tests/run-evals.sh --skill mock-audit

# Single command test
./tests/run-evals.sh --command engagement-audit
```

## What gets tested

### Structural checks (fast, free)

For every skill in `skills/*/SKILL.md`:
- Frontmatter present with `name`, `description`, `metadata.type`
- `name` field matches the directory name
- `description` includes trigger language ("Trigger when…")
- Body has at least: "What this solves", "The pattern", and a "Worked example" section
- Markdown is valid

For every command in `commands/*.md`:
- Frontmatter with `name` + `description`
- Body describes inputs, outputs, and what to do next

For every agent in `agents/*.md`:
- Frontmatter with `name`, `description`, `tools`
- Tool list references real Claude Code tools

For every template in `templates/`:
- File exists, non-empty
- HTML template parses, has expected sections
- Markdown templates have all `{{placeholder}}` markers documented

### Behavioral checks (requires Claude API)

For each skill — does Claude fire it when triggered?
- Send a synthetic prompt that should trigger the skill
- Check that the skill is referenced in Claude's response or actions
- Send a non-trigger prompt — verify the skill is NOT fired

For each slash command — does it produce the expected artifact?
- Set up a fixture directory (sometimes with synthetic input)
- Invoke the command via `claude -p "/<command>"`
- Check the output file is created with expected structure

For the mock-auditor agent — does it find planted mocks?
- Run against `fixtures/synthetic-codebase/` which contains 5 known mocks
- Verify all 5 are found, ranked correctly, and reported in the findings doc

## Cost

Behavioral tests cost approximately:
- Skill trigger tests: ~$0.02 each × 10 skills = $0.20
- Command artifact tests: ~$0.05 each × 6 commands = $0.30
- Full agent test: ~$0.10
- **Total ~$0.60 per full run**

Structural tests cost $0.

## CI integration

`.github/workflows/test-plugin.yml` can run the structural tests on every push and the behavioral tests on tags.

## Adding tests

1. **For a new skill:** add a trigger scenario + non-trigger scenario to `scenarios/skills/<skill-name>.json`.
2. **For a new command:** add a fixture + verification spec to `scenarios/commands/<command-name>.json`.
3. The runner discovers tests automatically.
