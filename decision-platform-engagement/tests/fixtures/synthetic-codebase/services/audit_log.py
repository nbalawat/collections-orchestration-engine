"""[PLANTED MOCK #4 — High]

Audit writes use a try/except that swallows ALL errors and returns success.
The caller thinks everything was audited. The auditor finds no rows.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def write_audit_row(table: str, row: dict) -> dict:
    try:
        # Imagine a real DB write here... but we never actually wrote anything
        # because someone wrapped it in a try/except that hides failures.
        result = await _legacy_writer_that_doesnt_exist(table, row)
        return {"status": "audited", "table": table}
    except Exception as e:
        # ANTIPATTERN: silent error swallowing dressed as success
        logger.warning("audit write failed, ignoring: %s", e)
        return {"status": "audited", "table": table}


async def _legacy_writer_that_doesnt_exist(*_args, **_kwargs):
    raise NotImplementedError("legacy writer not connected")
