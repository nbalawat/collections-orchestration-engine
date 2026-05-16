# mock-audit · reference code

A grep recipe + shell script that does a first-pass mock hunt across a codebase. Useful as a precursor to the deeper `/engagement-audit` Claude command.

## Files

- `find-mocks.sh` — runs the standard grep patterns and produces a tab-separated findings file
- `patterns.txt` — the search patterns the script uses

## Usage

```bash
./find-mocks.sh path/to/codebase > findings.tsv
column -t -s $'\t' findings.tsv | less -S
```

## When to use

- Quick sanity check before the deeper Claude audit
- CI hook ("did anyone reintroduce a mock?")
- Onboarding ("here's what we already audited; here's the current count")

Note: this is pattern-matching, not understanding. It will produce false positives. The deeper `/engagement-audit` command uses Claude to verify each match in context.
