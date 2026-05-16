#!/usr/bin/env bash
# Quick grep-based mock audit. Produces a TSV with file:line<TAB>pattern<TAB>matched-line.
# Use as a precursor to the deeper /engagement-audit Claude command.

set -euo pipefail
ROOT="${1:-.}"

declare -a patterns=(
  "random\.choice"                                           "random-choice-for-business-outcome"
  "random\.randint"                                          "random-int-for-business-outcome"
  "return\s*\{[^}]*\"status\"\s*:\s*\"(ok|success|sent|escalated|completed)\""  "stub-success-return"
  "^\s*pass\s*$"                                             "empty-pass-stub"
  "raise\s+NotImplementedError"                              "not-implemented"
  "#\s*TODO"                                                 "TODO"
  "#\s*FIXME"                                                "FIXME"
  "from unittest.mock"                                       "import-unittest-mock"
  "from\s+\w+_mock\b"                                        "import-mock-module"
  "from\s+\w+_fake\b"                                        "import-fake-module"
  "from\s+\w+_stub\b"                                        "import-stub-module"
  "time\.sleep\("                                            "sleep-for-fake-processing"
  "confidence\s*=\s*0\.85"                                   "hardcoded-confidence"
  "voice_attempts_7d\s*=\s*0"                                "hardcoded-policy-input"
  "customer_local_hour\s*=\s*14"                             "hardcoded-policy-input"
  "if\s+\"[a-z]+\"\s+in\s+response_text"                     "keyword-match-on-llm-response"
  "if\s+\"[a-z]+\"\s+in\s+response_lower"                    "keyword-match-on-llm-response"
)

i=0
while (( i < ${#patterns[@]} )); do
  pattern="${patterns[$i]}"
  name="${patterns[$((i+1))]}"
  i=$((i+2))
  grep -rIE "${pattern}" "${ROOT}" \
    --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.go" \
    --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=dist --exclude-dir=build \
    -n 2>/dev/null | while IFS= read -r line; do
      file_lineno=$(echo "$line" | cut -d: -f1-2)
      content=$(echo "$line" | cut -d: -f3-)
      echo -e "${file_lineno}\t${name}\t${content}"
  done
done
