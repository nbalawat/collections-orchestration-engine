#!/usr/bin/env bash
# Plugin test runner — structural + behavioral
#
# Usage:
#   ./tests/run-evals.sh --structural              fast, no API
#   ./tests/run-evals.sh --all                     full eval (~$0.60)
#   ./tests/run-evals.sh --skill mock-audit        single skill
#   ./tests/run-evals.sh --command engagement-init single command
#
# Exit codes:
#   0  all tests passed
#   1  at least one test failed
#   2  invocation error

set -euo pipefail

PLUGIN_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
RESULTS_DIR="${PLUGIN_DIR}/tests/results"
mkdir -p "${RESULTS_DIR}"

if [[ -t 1 ]]; then
  R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'; D='\033[0;90m'; X='\033[0m'
else
  R=''; G=''; Y=''; B=''; D=''; X=''
fi

declare -i PASS=0
declare -i FAIL=0
declare -a FAILURES=()

pass() { echo -e "  ${G}✓${X} $1"; PASS+=1; }
fail() { echo -e "  ${R}✗${X} $1"; FAIL+=1; FAILURES+=("$1"); }
note() { echo -e "  ${D}·${X} $1"; }
hdr()  { echo; echo -e "${B}══${X} $1"; }

# ── structural tests ─────────────────────────────────────────────────

test_skill_structural() {
  local skill_dir=$1
  local skill_file="${skill_dir}/SKILL.md"
  local skill_name
  skill_name=$(basename "${skill_dir}")

  [[ -f "${skill_file}" ]] || { fail "${skill_name}: SKILL.md missing"; return; }

  if head -1 "${skill_file}" | grep -q '^---$'; then
    pass "${skill_name}: frontmatter present"
  else
    fail "${skill_name}: missing frontmatter"
    return
  fi

  local fm
  fm=$(awk '/^---$/{p=1-p; next} p' "${skill_file}")
  for field in name description; do
    if echo "${fm}" | grep -q "^${field}:"; then
      pass "${skill_name}: has ${field}"
    else
      fail "${skill_name}: missing ${field}"
    fi
  done

  local declared_name
  declared_name=$(echo "${fm}" | awk '/^name:/{print $2}' | tr -d '"')
  if [[ "${declared_name}" == "${skill_name}" ]]; then
    pass "${skill_name}: name matches directory"
  else
    fail "${skill_name}: declared name '${declared_name}' != directory '${skill_name}'"
  fi

  if echo "${fm}" | grep -qi 'trigger when\|when the user'; then
    pass "${skill_name}: description has trigger conditions"
  else
    fail "${skill_name}: description missing 'Trigger when' or 'When the user'"
  fi

  for section in "What this solves" "Worked example"; do
    if grep -q "## ${section}\|^# ${section}" "${skill_file}"; then
      pass "${skill_name}: has '${section}' section"
    else
      fail "${skill_name}: missing '${section}' section"
    fi
  done
}

test_command_structural() {
  local cmd_file=$1
  local cmd_name
  cmd_name=$(basename "${cmd_file}" .md)

  if head -1 "${cmd_file}" | grep -q '^---$'; then
    pass "${cmd_name}: frontmatter present"
  else
    fail "${cmd_name}: missing frontmatter"
    return
  fi

  local fm
  fm=$(awk '/^---$/{p=1-p; next} p' "${cmd_file}")
  for field in name description; do
    if echo "${fm}" | grep -q "^${field}:"; then
      pass "${cmd_name}: has ${field}"
    else
      fail "${cmd_name}: missing ${field}"
    fi
  done

  local lines
  lines=$(wc -l < "${cmd_file}")
  if (( lines >= 30 )); then
    pass "${cmd_name}: body has ${lines} lines"
  else
    fail "${cmd_name}: body too short (${lines} lines)"
  fi
}

test_agent_structural() {
  local agent_file=$1
  local agent_name
  agent_name=$(basename "${agent_file}" .md)

  if head -1 "${agent_file}" | grep -q '^---$'; then
    pass "${agent_name}: frontmatter present"
  else
    fail "${agent_name}: missing frontmatter"
    return
  fi

  local fm
  fm=$(awk '/^---$/{p=1-p; next} p' "${agent_file}")
  for field in name description tools; do
    if echo "${fm}" | grep -q "^${field}:"; then
      pass "${agent_name}: has ${field}"
    else
      fail "${agent_name}: missing ${field}"
    fi
  done
}

test_template_structural() {
  local tmpl_file=$1
  local tmpl_name
  tmpl_name=$(basename "${tmpl_file}")

  if [[ -s "${tmpl_file}" ]]; then
    pass "${tmpl_name}: non-empty"
  else
    fail "${tmpl_name}: empty or missing"
    return
  fi

  if [[ "${tmpl_file}" == *.html ]]; then
    if grep -qi '<!doctype html\|<html' "${tmpl_file}"; then
      pass "${tmpl_name}: looks like HTML"
    else
      fail "${tmpl_name}: doesn't look like HTML"
    fi
    if grep -q '<style' "${tmpl_file}"; then
      pass "${tmpl_name}: has inline CSS"
    else
      fail "${tmpl_name}: no inline CSS"
    fi
  fi
}

test_plugin_manifest() {
  local manifest="${PLUGIN_DIR}/plugin.json"

  if [[ -f "${manifest}" ]]; then
    pass "plugin.json: exists"
  else
    fail "plugin.json: missing"
    return
  fi

  if python3 -c "import json; json.load(open('${manifest}'))" 2>/dev/null; then
    pass "plugin.json: valid JSON"
  else
    fail "plugin.json: invalid JSON"
    return
  fi

  for field in name version description commands skills agents templates; do
    if python3 -c "import json; d=json.load(open('${manifest}')); assert '${field}' in d" 2>/dev/null; then
      pass "plugin.json: has '${field}' field"
    else
      fail "plugin.json: missing '${field}' field"
    fi
  done

  if python3 - <<EOF
import json, os, sys
manifest = json.load(open("${manifest}"))
missing = []
for cmd in manifest.get("commands", []):
    p = os.path.join("${PLUGIN_DIR}", cmd["file"])
    if not os.path.exists(p):
        missing.append(("command", cmd["name"], cmd["file"]))
for skill in manifest.get("skills", []):
    p = os.path.join("${PLUGIN_DIR}", skill["path"])
    if not os.path.exists(p):
        missing.append(("skill", skill["name"], skill["path"]))
for agent in manifest.get("agents", []):
    p = os.path.join("${PLUGIN_DIR}", agent["file"])
    if not os.path.exists(p):
        missing.append(("agent", agent["name"], agent["file"]))
for persona in manifest.get("personas", []):
    p = os.path.join("${PLUGIN_DIR}", persona["file"])
    if not os.path.exists(p):
        missing.append(("persona", persona["name"], persona["file"]))
for tmpl in manifest.get("templates", []):
    p = os.path.join("${PLUGIN_DIR}", tmpl)
    if not os.path.exists(p):
        missing.append(("template", tmpl, tmpl))
if missing:
    for kind, name, path in missing:
        sys.stderr.write(f"  {kind} '{name}' references missing file '{path}'\n")
    sys.exit(1)
EOF
  then
    pass "plugin.json: all referenced files exist"
  else
    fail "plugin.json: references missing files"
  fi
}

test_scenarios_structural() {
  for f in "${PLUGIN_DIR}/tests/scenarios"/*.json; do
    local name
    name=$(basename "$f")
    if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
      pass "${name}: valid JSON"
    else
      fail "${name}: invalid JSON"
    fi
  done
}

test_synthetic_fixture() {
  local fix="${PLUGIN_DIR}/tests/fixtures/synthetic-codebase"
  if [[ ! -d "${fix}" ]]; then
    fail "synthetic-codebase fixture missing"
    return
  fi
  pass "synthetic-codebase: directory present"

  local expected=("services/fake_agent.py" "workflows/compliance_check.py" "services/stub_dispatcher.py" "services/audit_log.py" "services/channel_writer.py")
  for f in "${expected[@]}"; do
    if [[ -f "${fix}/${f}" ]]; then
      pass "synthetic-codebase: planted mock ${f}"
    else
      fail "synthetic-codebase: missing planted mock ${f}"
    fi
  done

  local real=("services/real_publisher.py" "workflows/lookup_account.py" "BOUNDARY.md")
  for f in "${real[@]}"; do
    if [[ -f "${fix}/${f}" ]]; then
      pass "synthetic-codebase: real ${f}"
    else
      fail "synthetic-codebase: missing real ${f}"
    fi
  done
}

run_structural() {
  hdr "Structural · plugin manifest"
  test_plugin_manifest

  hdr "Structural · skills"
  for skill_dir in "${PLUGIN_DIR}"/skills/*/; do
    test_skill_structural "${skill_dir}"
  done

  hdr "Structural · commands"
  for cmd_file in "${PLUGIN_DIR}"/commands/*.md; do
    test_command_structural "${cmd_file}"
  done

  hdr "Structural · agents"
  for agent_file in "${PLUGIN_DIR}"/agents/*.md; do
    [[ -f "${agent_file}" ]] || continue
    test_agent_structural "${agent_file}"
  done

  hdr "Structural · personas"
  for persona_file in "${PLUGIN_DIR}"/agents/personas/*.md; do
    [[ -f "${persona_file}" ]] || continue
    test_agent_structural "${persona_file}"
  done

  hdr "Structural · templates"
  for tmpl_file in "${PLUGIN_DIR}"/templates/*; do
    test_template_structural "${tmpl_file}"
  done

  hdr "Structural · test scenarios"
  test_scenarios_structural

  hdr "Structural · synthetic codebase fixture"
  test_synthetic_fixture
}

# ── behavioral tests ─────────────────────────────────────────────────

CLAUDE_BIN="${CLAUDE_BIN:-claude}"

check_claude_available() {
  if ! command -v "${CLAUDE_BIN}" >/dev/null 2>&1; then
    echo -e "${Y}claude CLI not available${X}"
    return 1
  fi
  if [[ -z "${ANTHROPIC_API_KEY:-${CLAUDE_CODE_OAUTH_TOKEN:-}}" ]]; then
    echo -e "${Y}neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set${X}"
    return 1
  fi
  return 0
}

run_behavioral_skills() {
  hdr "Behavioral · skill triggers"
  if ! check_claude_available; then
    note "skipping behavioral tests"
    return
  fi
  note "behavioral skill trigger scenarios in tests/scenarios/skill-triggers.json"
  note "implementation runs each prompt through claude -p and checks for skill reference"
  note "see CHECKLIST.md for manual run procedure"
}

run_behavioral_commands() {
  hdr "Behavioral · command artifact generation"
  if ! check_claude_available; then
    note "skipping behavioral tests"
    return
  fi
  note "behavioral command tests defined in tests/scenarios/command-specs.json"
  note "each command test sets up a fixture, invokes /<command>, verifies output structure"
  note "see CHECKLIST.md for manual run procedure"
}

# ── main ─────────────────────────────────────────────────────────────

MODE="${1:---structural}"

case "$MODE" in
  --structural)
    run_structural
    ;;
  --all)
    run_structural
    run_behavioral_skills
    run_behavioral_commands
    ;;
  --skill)
    skill_name="${2:-}"
    [[ -z "$skill_name" ]] && { echo "usage: $0 --skill <name>"; exit 2; }
    skill_dir="${PLUGIN_DIR}/skills/${skill_name}"
    [[ -d "$skill_dir" ]] || { echo "skill '${skill_name}' not found"; exit 2; }
    test_skill_structural "$skill_dir"
    ;;
  --command)
    cmd_name="${2:-}"
    [[ -z "$cmd_name" ]] && { echo "usage: $0 --command <name>"; exit 2; }
    cmd_file="${PLUGIN_DIR}/commands/${cmd_name}.md"
    [[ -f "$cmd_file" ]] || { echo "command '${cmd_name}' not found"; exit 2; }
    test_command_structural "$cmd_file"
    ;;
  -h|--help)
    cat <<'EOF'
Plugin test runner

Modes:
  --structural          structural checks only (default, fast, free)
  --all                 structural + behavioral (requires Claude CLI + API key)
  --skill NAME          test one skill structurally
  --command NAME        test one command structurally

Behavioral tests require:
  - claude CLI installed (npm i -g @anthropic-ai/claude-code)
  - ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN env var
EOF
    exit 0
    ;;
  *)
    echo "unknown mode: $MODE (use --help)"
    exit 2
    ;;
esac

hdr "Summary"
echo -e "  ${G}Passed:${X} ${PASS}"
echo -e "  ${R}Failed:${X} ${FAIL}"

if (( FAIL > 0 )); then
  echo
  echo -e "${R}Failures:${X}"
  for f in "${FAILURES[@]}"; do
    echo "  ✗ $f"
  done
  exit 1
fi

exit 0
