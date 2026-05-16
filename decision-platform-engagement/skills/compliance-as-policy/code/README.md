# compliance-as-policy · reference code

Example OPA Rego policy modules + Python wrapper. The Rego modules cite specific regulations (Reg F here; adapt for your regulatory frame).

## Files

- `compliance.rego` — Reg F §1006.6(b) quiet hours + §1006.14(b) frequency caps + full suppression
- `transcript_audit.rego` — FDCPA §807 prohibited language + Mini-Miranda + recording disclosure
- `wrapper.py` — Python helper that calls OPA via HTTP; emits compliance events on BOTH pass and fail
- `docker-compose.snippet.yml` — OPA service configuration (mount policies, watch for changes)

## Adaptation

1. Mount the Rego files into OPA via `--watch /policies` (see docker-compose snippet).
2. Replace `collections` package name and Reg F citations with your domain + regulations:
   - Healthcare → HIPAA citations
   - Lending → Reg B / Reg Z citations
   - EU → GDPR / DORA / MiFID citations
3. Wire `wrapper.check_action_gate(...)` into your workflow at the dispatch boundary.
4. Apply the WORM trigger to `customer_events` so compliance events are tamper-evident.
