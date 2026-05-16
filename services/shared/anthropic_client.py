"""Shared Anthropic client factory that handles both API keys and OAuth tokens.

The Anthropic SDK accepts two auth mechanisms:
  - api_key=sk-ant-api03-…  → sent as `x-api-key` header
  - auth_token=sk-ant-oat01-… → sent as `Authorization: Bearer …` header

ANTHROPIC_API_KEY env var may contain either form. We detect by prefix and
construct the client with the right argument so OAuth tokens work without
code changes elsewhere.
"""
from __future__ import annotations

import os

from anthropic import AsyncAnthropic, Anthropic


def _credentials() -> dict[str, str]:
    """Pick auth_token vs api_key based on the token format."""
    token = (
        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    ).strip()
    if not token:
        return {}
    if token.startswith("sk-ant-oat") or token.startswith("oat_"):
        # OAuth bearer token — wire to auth_token so SDK uses `Authorization: Bearer`
        return {"auth_token": token}
    return {"api_key": token}


def make_async_client() -> AsyncAnthropic:
    return AsyncAnthropic(**_credentials())


def make_sync_client() -> Anthropic:
    return Anthropic(**_credentials())
