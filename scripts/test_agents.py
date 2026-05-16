"""Smoke test for all 5 AI agents using the Claude Agent SDK tool runner.

Run: python -m scripts.test_agents
Requires: Postgres with seeded data, OPA running, ANTHROPIC_API_KEY set.
Optional: Temporal (journey state lookups will gracefully degrade).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("test_agents")


async def test_digital_channel():
    from services.ai_agents.digital_channel_agent import DigitalChannelAgent

    agent = DigitalChannelAgent()
    logger.info("=== Digital Channel Agent ===")

    result = await agent.invoke({
        "customer_id": "CUST-0032",
        "message": "I lost my job last month and I can't make my payment. Can we work something out?",
        "channel": "sms",
    })

    logger.info("Action: %s | Confidence: %s | Escalated: %s",
                result.get("action_taken"), result.get("confidence"), result.get("escalated"))
    logger.info("Tokens: %s | Latency: %sms", result.get("tokens_used"), result.get("latency_ms"))
    logger.info("Response: %s", result.get("response_text", "")[:200])

    trace = result.get("reasoning_trace", {})
    steps = trace.get("reasoning_steps", [])
    logger.info("Reasoning steps: %d", len(steps))
    for s in steps:
        logger.info("  → %s: %s", s.get("step"), s.get("result", "")[:100])

    return result


async def test_copilot():
    from services.ai_agents.copilot_agent import CopilotAgent

    agent = CopilotAgent()
    logger.info("\n=== Agent Copilot ===")

    result = await agent.invoke({
        "customer_id": "CUST-0055",
        "request_type": "nba",
        "channel": "voice",
        "interaction_context": "Customer called about their past due balance, mentioned difficulty paying",
    })

    logger.info("Action: %s | Tokens: %s | Latency: %sms",
                result.get("action_taken"), result.get("tokens_used"), result.get("latency_ms"))
    logger.info("Response: %s", result.get("response_text", "")[:300])
    return result


async def test_case_reasoning():
    from services.ai_agents.case_reasoning_agent import CaseReasoningAgent

    agent = CaseReasoningAgent()
    logger.info("\n=== Case Reasoning Agent ===")

    result = await agent.invoke({
        "customer_id": "CUST-0120",
        "reason": "Conflicting signals — customer mentions new job but also says can't pay full amount. Settlement inquiry on high-value account.",
        "trigger": "inbound_call_settlement_inquiry",
        "prior_actions": ["sms_dunning", "email_notice", "voice_outbound_no_answer"],
    })

    logger.info("Action: %s | Confidence: %s | Escalated: %s",
                result.get("action_taken"), result.get("confidence"), result.get("escalated"))
    logger.info("Tokens: %s | Latency: %sms", result.get("tokens_used"), result.get("latency_ms"))
    logger.info("Response: %s", result.get("response_text", "")[:400])
    return result


async def test_portfolio_intelligence():
    from services.ai_agents.portfolio_intelligence_agent import PortfolioIntelligenceAgent

    agent = PortfolioIntelligenceAgent()
    logger.info("\n=== Portfolio Intelligence Agent ===")

    result = await agent.invoke({
        "analysis_type": "portfolio_health",
        "time_range": "30 days",
    })

    logger.info("Tokens: %s | Latency: %sms", result.get("tokens_used"), result.get("latency_ms"))
    logger.info("Response: %s", result.get("response_text", "")[:400])
    return result


async def test_quality_compliance():
    from services.ai_agents.quality_compliance_agent import QualityComplianceAgent

    agent = QualityComplianceAgent()
    logger.info("\n=== Quality & Compliance Agent ===")

    result = await agent.invoke({
        "customer_id": "CUST-0032",
        "interaction_id": "latest",
        "agent_id": "AGT-101",
        "channel": "voice",
        "review_type": "full",
    })

    logger.info("Action: %s | Tokens: %s | Latency: %sms",
                result.get("action_taken"), result.get("tokens_used"), result.get("latency_ms"))
    logger.info("Response: %s", result.get("response_text", "")[:300])
    return result


async def main():
    agent_name = sys.argv[1] if len(sys.argv) > 1 else "all"

    tests = {
        "digital": test_digital_channel,
        "copilot": test_copilot,
        "case": test_case_reasoning,
        "portfolio": test_portfolio_intelligence,
        "quality": test_quality_compliance,
    }

    if agent_name == "all":
        for name, test_fn in tests.items():
            try:
                await test_fn()
            except Exception as e:
                logger.error("Agent '%s' failed: %s", name, e, exc_info=True)
            print()
    elif agent_name in tests:
        await tests[agent_name]()
    else:
        print(f"Usage: python -m scripts.test_agents [{'|'.join(tests.keys())}|all]")


if __name__ == "__main__":
    asyncio.run(main())
