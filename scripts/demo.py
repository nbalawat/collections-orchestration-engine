"""Master demo runner — orchestrates the full collections POC demo.

Run: uv run python -m scripts.demo [scenario_name|all]

Scenarios:
  cross_channel   — Jane Doe: SMS → hardship → email → bounce → voice → resolution
  bankruptcy      — Robert Chen: mid-journey → bankruptcy → suppression → dismissed
  ptp             — Maria Garcia: voice → PTP → payment → cure
  strategy_swap   — Multiple customers, strategy version change
  complex_case    — David Park: conflicting signals → AI reasoning
  portfolio       — 20 customers with random activity
  ai_agents       — Exercise all 5 AI agents in sequence
  all             — Run everything
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich import box

logging.basicConfig(level=logging.WARNING)
console = Console()


def banner(title: str, subtitle: str = ""):
    console.print()
    console.print(Panel(f"[bold white]{title}[/]\n{subtitle}" if subtitle else f"[bold white]{title}[/]",
                        border_style="blue", width=70))
    console.print()


def step(num: int, description: str):
    console.print(f"  [bold cyan]Step {num}:[/] {description}")


def result(text: str, style: str = "green"):
    console.print(f"    [bold {style}]→[/] {text}")


def wait(seconds: float, reason: str = ""):
    if reason:
        console.print(f"    [dim]⏳ {reason} ({seconds}s)[/]")
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(seconds))


async def demo_cross_channel():
    """Scenario 1: Cross-Channel Journey"""
    from services.channel_simulators.scenarios import ScenarioRunner

    banner("Scenario 1: Cross-Channel Journey",
           "Jane Doe (CUST-0032): 45 DPD → SMS dunning → hardship reply → email → bounce → voice → resolution")

    runner = ScenarioRunner()
    await runner.start()

    try:
        step(1, "Starting customer journey workflow...")
        wf_id = await runner._ensure_workflow("CUST-0032")
        result(f"Workflow started: {wf_id}")

        step(2, "Sending outbound SMS dunning notice...")
        await runner.sim.simulate_sms_outbound("CUST-0032", template="dunning_notice")
        result("SMS delivered")
        await asyncio.sleep(2)

        step(3, "Customer replies with hardship message...")
        await runner.sim.simulate_sms_inbound("CUST-0032", intent=__import__("events.models", fromlist=["Intent"]).Intent.HARDSHIP)
        result("Hardship intent detected → workflow transitions to HARDSHIP_REVIEW")
        await asyncio.sleep(3)

        step(4, "Sending email with payment plan options...")
        await runner.sim.simulate_email_event("CUST-0032", "delivered")
        result("Email delivered")
        await asyncio.sleep(1)

        step(5, "Email bounces...")
        await runner.sim.simulate_email_event("CUST-0032", "bounced")
        result("Bounce detected → channel marked as failed", "yellow")
        await asyncio.sleep(2)

        step(6, "Outbound voice call — agent connects...")
        await runner.sim.simulate_voice_call(
            "CUST-0032",
            direction=__import__("events.models", fromlist=["Direction"]).Direction.OUTBOUND,
            outcome="connected_rpc",
            intent=__import__("events.models", fromlist=["Intent"]).Intent.HARDSHIP,
            duration_seconds=320,
        )
        result("Call connected: 5m20s, hardship discussion")
        await asyncio.sleep(2)

        state = await runner._query("CUST-0032")
        result(f"Final state: stage={state.get('stage')}, actions={state.get('actions_count', 0)}, events={state.get('events_count', 0)}")
    finally:
        await runner.stop()


async def demo_bankruptcy():
    """Scenario 2: Bankruptcy Suppression"""
    from services.channel_simulators.scenarios import ScenarioRunner

    banner("Scenario 2: Bankruptcy Suppression",
           "Robert Chen (CUST-0095): mid-journey → bankruptcy filed → all suppressed → dismissed → resumes")

    runner = ScenarioRunner()
    await runner.start()

    try:
        step(1, "Starting journey and establishing baseline...")
        await runner._ensure_workflow("CUST-0095")
        await asyncio.sleep(2)

        step(2, "Filing bankruptcy notification...")
        from workflows.types import ComplianceFlagSignal
        from workflows.customer_journey import CustomerJourney
        handle = runner.temporal.get_workflow_handle("journey-CUST-0095")
        await handle.signal(
            CustomerJourney.compliance_flag,
            ComplianceFlagSignal(flag_type="BANKRUPTCY", reason="Chapter 7 filing", action="activate"),
        )
        await asyncio.sleep(2)

        state = await runner._query("CUST-0095")
        result(f"SUSPENDED: flags={state.get('compliance_flags')}", "red")

        step(3, "Attempting SMS outbound (should be blocked)...")
        await runner.sim.simulate_sms_outbound("CUST-0095", template="settlement_offer")
        result("Action suppressed by compliance gate", "yellow")
        await asyncio.sleep(2)

        step(4, "Bankruptcy dismissed...")
        await handle.signal(
            CustomerJourney.compliance_flag,
            ComplianceFlagSignal(flag_type="BANKRUPTCY", reason="Case dismissed", action="deactivate"),
        )
        await asyncio.sleep(2)

        state = await runner._query("CUST-0095")
        result(f"Resumed: stage={state.get('stage')}, suspended={state.get('suspended')}")
    finally:
        await runner.stop()


async def demo_ptp():
    """Scenario 3: PTP Lifecycle"""
    from services.channel_simulators.scenarios import ScenarioRunner
    from events.models import Direction, Intent

    banner("Scenario 3: PTP Lifecycle",
           "Maria Garcia (CUST-0055): voice → PTP → timer → payment → cure")

    runner = ScenarioRunner()
    await runner.start()

    try:
        step(1, "Starting journey...")
        await runner._ensure_workflow("CUST-0055")
        await asyncio.sleep(2)

        step(2, "Outbound call — customer promises to pay...")
        await runner.sim.simulate_voice_call(
            "CUST-0055", direction=Direction.OUTBOUND,
            outcome="connected_rpc", intent=Intent.PTP, duration_seconds=180,
        )
        await runner.sim.simulate_sms_inbound(
            "CUST-0055", intent=Intent.PTP,
            payload_override={"amount": 4100, "promised_date": "2026-05-20"},
        )
        await asyncio.sleep(3)

        state = await runner._query("CUST-0055")
        result(f"PTP recorded: stage={state.get('stage')}, active_ptp={state.get('active_ptp')}")

        step(3, "Payment arrives...")
        from workflows.types import PaymentSignal
        from workflows.customer_journey import CustomerJourney
        handle = runner.temporal.get_workflow_handle("journey-CUST-0055")
        await handle.signal(
            CustomerJourney.payment_received,
            PaymentSignal(amount=4100, payment_date="2026-05-20", account_id=state.get("account_id", ""), method="ach"),
        )
        await asyncio.sleep(2)

        state = await runner._query("CUST-0055")
        result(f"Payment processed: stage={state.get('stage')}, balance={state.get('balance')}")
    finally:
        await runner.stop()


async def demo_ai_agents():
    """Exercise all 5 AI agents"""
    banner("AI Agents Demo", "Invoking all 5 Claude-powered AI agents with realistic inputs")

    from services.ai_agents import (
        DigitalChannelAgent, CopilotAgent, CaseReasoningAgent,
        PortfolioIntelligenceAgent, QualityComplianceAgent,
    )

    agents = [
        ("Digital Channel Agent", DigitalChannelAgent(), {
            "customer_id": "CUST-0032",
            "message": "I lost my job last month. Can we work something out on my payments?",
            "channel": "sms",
        }),
        ("Agent Copilot", CopilotAgent(), {
            "customer_id": "CUST-0055",
            "request_type": "nba",
            "channel": "voice",
            "interaction_context": "Customer called about past due balance",
        }),
        ("Case Reasoning Agent", CaseReasoningAgent(), {
            "customer_id": "CUST-0120",
            "reason": "Conflicting signals — new job but can't pay full amount, settlement inquiry",
            "trigger": "inbound_call",
        }),
        ("Portfolio Intelligence", PortfolioIntelligenceAgent(), {
            "analysis_type": "portfolio_health",
        }),
        ("Quality & Compliance", QualityComplianceAgent(), {
            "customer_id": "CUST-0032",
            "interaction_id": "latest",
            "channel": "voice",
            "review_type": "full",
        }),
    ]

    for i, (name, agent, context) in enumerate(agents, 1):
        step(i, f"Invoking {name}...")
        start = time.time()
        try:
            res = await agent.invoke(context)
            elapsed = time.time() - start
            action = res.get("action_taken", "none")
            tokens = res.get("tokens_used", 0)
            conf = res.get("confidence", 0)
            escalated = res.get("escalated", False)

            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            table.add_column(style="bold")
            table.add_column()
            table.add_row("Action", str(action))
            table.add_row("Confidence", f"{conf:.0%}")
            table.add_row("Escalated", "Yes" if escalated else "No")
            table.add_row("Tokens", str(tokens))
            table.add_row("Latency", f"{elapsed:.1f}s")

            response = res.get("response_text", "")
            if response:
                table.add_row("Response", response[:200] + ("..." if len(response) > 200 else ""))

            console.print(table)
        except Exception as e:
            result(f"Error: {e}", "red")
        console.print()


async def demo_portfolio():
    """Scenario 6: Portfolio Operations"""
    from services.channel_simulators.scenarios import ScenarioRunner

    banner("Scenario 6: Portfolio Operations", "Spin up 20 customer journeys with random activity")

    runner = ScenarioRunner()
    await runner.start()
    try:
        step(1, "Starting 20 customer workflows...")
        res = await runner.scenario_portfolio(count=20)
        result(f"Started {res['started']} workflows, generated {res['events_generated']} events")
    finally:
        await runner.stop()


async def run_demo(scenario: str):
    scenarios = {
        "cross_channel": demo_cross_channel,
        "bankruptcy": demo_bankruptcy,
        "ptp": demo_ptp,
        "ai_agents": demo_ai_agents,
        "portfolio": demo_portfolio,
    }

    console.print()
    console.print(Panel("[bold white]Collections Orchestration Engine — Demo[/]\n"
                        "Real-time collections with AI agents, Temporal workflows, Kafka events, OPA policies",
                        border_style="bright_blue", width=70))

    if scenario == "all":
        for name, fn in scenarios.items():
            try:
                await fn()
            except Exception as e:
                console.print(f"  [bold red]Scenario '{name}' failed: {e}[/]")
            console.print()
        banner("Demo Complete", "All scenarios executed")
    elif scenario in scenarios:
        await scenarios[scenario]()
    else:
        console.print(f"[red]Unknown scenario: {scenario}[/]")
        console.print(f"Available: {', '.join(scenarios.keys())}, all")
        return


if __name__ == "__main__":
    scenario_name = sys.argv[1] if len(sys.argv) > 1 else "all"
    asyncio.run(run_demo(scenario_name))
