"""Portfolio Intelligence Agent — analytics and strategy optimization across the book.

Analyzes portfolio-level trends, compares cohort performance, identifies strategy
effectiveness, and recommends configuration changes. Powers the Strategy Console
and Ops Dashboard with AI-driven insights.
"""
from __future__ import annotations

from events.models import AgentType
from services.ai_agents.base_agent import CollectionsAgent
from services.ai_agents.tools import (
    query_portfolio_metrics,
    query_strategy_performance,
    query_segment_trends,
    compare_cohorts,
    suggest_strategy_change,
)


class PortfolioIntelligenceAgent(CollectionsAgent):
    agent_type = AgentType.PORTFOLIO_INTELLIGENCE
    model = "claude-sonnet-4-6"
    max_tokens = 6144

    def get_system_prompt(self) -> str:
        return """You are a portfolio intelligence agent for a collections operation.

## Your Role
- Analyze portfolio-level metrics and trends
- Compare cohort performance across segments
- Evaluate strategy effectiveness
- Recommend strategy configuration changes with data-driven rationale
- Power the Strategy Console and Ops Dashboard with actionable insights

## Analysis Capabilities
- **Portfolio Health**: Delinquency distribution, balance at risk, flow rates
- **Strategy Performance**: Recovery rates, contact rates, PTP conversion by strategy version
- **Segment Analysis**: Performance by DPD bucket, risk tier, balance tier, value segment
- **Cohort Comparison**: Champion vs. challenger, treatment A vs. B
- **Trend Detection**: Deteriorating segments, emerging patterns, seasonality

## Output Format
Structure your analysis as:
- **Executive Summary**: 2-3 key takeaways
- **Metrics**: Relevant numbers with context (vs. benchmark, vs. prior period)
- **Findings**: What the data shows
- **Recommendations**: Specific, actionable strategy changes
- **Risk Assessment**: What to watch for

## Guidelines
- Always ground recommendations in data
- Quantify impact where possible (e.g., "could improve recovery by ~12%")
- Strategy changes are recommendations only — they require human approval
- Use suggest_strategy_change to formally log recommendations
- Consider operational constraints (agent capacity, channel costs, compliance)"""

    def get_tools(self) -> list:
        return [
            query_portfolio_metrics,
            query_strategy_performance,
            query_segment_trends,
            compare_cohorts,
            suggest_strategy_change,
        ]

    def _build_user_message(self, context: dict) -> str:
        analysis_type = context.get("analysis_type", "portfolio_health")
        question = context.get("question", "")
        segment = context.get("segment", "")
        time_range = context.get("time_range", "30 days")

        if question:
            return f"""Answer this portfolio question: {question}

Pull the relevant metrics and provide a data-driven analysis."""

        if analysis_type == "cohort_comparison":
            cohort_a = context.get("cohort_a", "EARLY")
            cohort_b = context.get("cohort_b", "MID")
            return f"""Compare performance between {cohort_a} and {cohort_b} segments.
Analyze recovery rates, contact effectiveness, and treatment outcomes.
Recommend any strategy adjustments based on the comparison."""

        if analysis_type == "strategy_review":
            return f"""Review the current strategy performance:
1. Query overall portfolio metrics
2. Check strategy performance and recent changes
3. Analyze segment trends
4. Identify underperforming segments or strategies
5. Recommend specific improvements with data backing"""

        return f"""Provide a portfolio health assessment:
1. Pull overall portfolio metrics (summary + delinquency breakdown)
2. Analyze channel performance
3. Review segment trends
4. Identify any concerning patterns
5. Provide an executive summary with key metrics and recommendations"""
