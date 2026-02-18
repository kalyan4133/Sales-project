# agents/graph.py
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from .competition import compute_market_competition, load_competitors
from .pricing import build_price_catalog, price_products
from .tools import get_llm


class DealState(TypedDict, total=False):
    deal_id: str
    company_name: str
    products: List[str]

    priced_items: List[Dict[str, Any]]
    total_price: float

    market: Dict[str, Any]
    recommendation_confidence: float

    insights: Dict[str, Any]


@lru_cache(maxsize=1)
def get_price_catalog() -> Dict[str, float]:
    return build_price_catalog()


@lru_cache(maxsize=1)
def get_comp_df():
    return load_competitors()


def node_price(state: DealState) -> DealState:
    catalog = get_price_catalog()
    items, total = price_products(state.get("products", []), catalog)
    return {**state, "priced_items": items, "total_price": total}


def node_market(state: DealState) -> DealState:
    df = get_comp_df()
    products = state.get("products", [])
    market = compute_market_competition(products, df)

    # Coverage-based confidence: more dataset matches => higher confidence
    conf = 0.5 + 0.5 * float(market.get("coverage", 0))
    conf = round(min(conf, 0.95), 2)

    # UI display numbers (0–100)
    overall_comp = float(market.get("overall_market_competition", 0.5))
    competition_pct = int(round(overall_comp * 100))
    confidence_pct = int(round(conf * 100))

    # Simple, explainable win-rate estimate
    win_rate = int(round((0.55 * conf + 0.45 * (1 - overall_comp)) * 100))
    win_rate = max(5, min(95, win_rate))

    market["ui"] = {
        "competition_pct": competition_pct,
        "confidence_pct": confidence_pct,
        "win_rate_pct": win_rate,
        "competition_label": (
            "HIGHLY COMPETITIVE"
            if competition_pct >= 75
            else "MODERATE"
            if competition_pct >= 45
            else "LOW COMPETITION"
        ),
        "confidence_label": (
            "HIGH" if confidence_pct >= 85 else "MODERATE" if confidence_pct >= 60 else "LOW"
        ),
        "source_note": "Computed from competitors.csv (comparative_position + product matching).",
    }

    return {**state, "market": market, "recommendation_confidence": conf}


def node_strategy_llm(state: DealState) -> DealState:
    """
    Generates the right-side 'AI Sales Advisor' content.
    Never breaks the UI: returns a fallback payload on any LLM/API error.
    """
    try:
        llm = get_llm()

        market = state.get("market", {})
        ui = market.get("ui", {})
        products = state.get("products", [])
        total_value = state.get("total_price", 0)

        by_prod = market.get("by_product", [])
        competitor_summary = [
            f"{x.get('product','')}: {x.get('position','')} vs {x.get('top_competitor','')}"
            for x in by_prod
        ]

        prompt = f"""
You are an enterprise AI Sales Advisor for Thermo Fisher-like B2B scientific products.

Inputs:
- Company: {state.get('company_name', '')}
- Deal ID: {state.get('deal_id', '')}
- Products: {products}
- Estimated total value: {total_value}
- Market competition (dataset-based): {ui.get('competition_pct', 0)}%
- Confidence: {ui.get('confidence_pct', 0)}%
- Competitor summary (from competitors.csv): {competitor_summary}

Return STRICT JSON ONLY:
{{
  "advisor_actions": [
    "Action 1",
    "Action 2",
    "Action 3"
  ],
  "discount_advice": {{
    "should_discount": true/false,
    "discount_range": "e.g., 0% or 3-7%",
    "reason": "short reason"
  }},
  "alternative_strategies": [
    {{"name":"Strategy name","impact":"e.g., -₹3,717.75 or +₹12,000"}},
    {{"name":"Strategy name","impact":"e.g., 0% discount, add service"}}
  ]
}}

Rules:
- If competition >= 75%: suggest bundling, training/service, proof points; allow small discount only with guardrails.
- If competition <= 35%: avoid discount; focus differentiation and urgency.
- Keep actions short and practical.
"""

        resp = llm.invoke(prompt)
        raw = (resp.content or "").strip()

        # Extract JSON robustly (handles extra text around JSON)
        m = re.search(r"\{.*\}", raw, flags=re.S)
        payload = json.loads(m.group(0) if m else raw)

        # Ensure schema fields exist
        actions = payload.get("advisor_actions", [])
        if not isinstance(actions, list) or len(actions) == 0:
            actions = [
                "Bundle with specialized onsite training to reduce switching risk.",
                "Position total cost of ownership + uptime + service SLAs.",
                "Offer a time-bound commercial incentive only if competition is high.",
            ]
        payload["advisor_actions"] = actions[:5]

        if "discount_advice" not in payload or not isinstance(payload["discount_advice"], dict):
            payload["discount_advice"] = {
                "should_discount": False,
                "discount_range": "0%",
                "reason": "Default: protect margin; discount only if competitive pressure is high.",
            }

        if "alternative_strategies" not in payload or not isinstance(payload["alternative_strategies"], list):
            payload["alternative_strategies"] = [
                {"name": "Aggressive Growth", "impact": "-₹3,717.75"},
                {"name": "Bundle Service Plan", "impact": "+Higher close probability"},
            ]

        return {**state, "insights": payload}

    except Exception as e:
        # Fallback so quote + insights pages never fail
        fallback = {
            "advisor_actions": [
                "Negotiate a 2-year volume commitment to lock in value.",
                "Bundle with specialized onsite training to reduce switching risk.",
                "Offer a time-bound incentive only if competition is high.",
            ],
            "discount_advice": {
                "should_discount": False,
                "discount_range": "0%",
                "reason": f"LLM unavailable: {type(e).__name__}",
            },
            "alternative_strategies": [
                {"name": "Aggressive Growth", "impact": "-₹3,717.75"},
                {"name": "Bundle Service Plan", "impact": "+Higher close probability"},
            ],
        }
        return {**state, "insights": fallback}


def build_graph():
    g = StateGraph(DealState)

    g.add_node("price", node_price)
    # Node name must not collide with any state keys (state has key: "market")
    g.add_node("market_node", node_market)
    g.add_node("strategy", node_strategy_llm)

    g.set_entry_point("price")
    g.add_edge("price", "market_node")
    g.add_edge("market_node", "strategy")
    g.add_edge("strategy", END)

    return g.compile()


GRAPH = build_graph()
