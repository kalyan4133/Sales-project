from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.llm_client import build_llm, LLMConfig
from app.services.store import DataStore


# -----------------------------
# Rule-based extraction helpers
# -----------------------------
def _clean_text(s: str) -> str:
    return " ".join((s or "").strip().split())


def _find_timeline(text: str) -> Tuple[str, float]:
    t = text.lower()

    # direct urgency words
    if any(w in t for w in ["asap", "urgent", "immediately", "right away", "today", "tomorrow"]):
        return "Immediate (0–7 days)", 0.85

    # date-like and relative time
    m = re.search(r"\b(in|within)\s+(\d+)\s*(day|days|week|weeks|month|months)\b", t)
    if m:
        n = int(m.group(2))
        unit = m.group(3)
        if "day" in unit:
            return f"Within {n} days", 0.8
        if "week" in unit:
            return f"Within {n} weeks", 0.8
        if "month" in unit:
            return f"Within {n} months", 0.75

    if any(w in t for w in ["this week", "this month", "this quarter", "next week", "next month", "next quarter"]):
        phrase = next(w for w in ["this week", "this month", "this quarter", "next week", "next month", "next quarter"] if w in t)
        return phrase.title(), 0.7

    return "", 0.0


def _find_quantity(text: str) -> Tuple[str, float]:
    t = text.lower()

    # units/kits/reactions/samples etc.
    m = re.search(r"\b(\d+)\s*(kits|kit|units|unit|boxes|box|reactions|rxns|samples)\b", t)
    if m:
        return f"{m.group(1)} {m.group(2)}", 0.85

    # “bulk / large volume”
    if any(w in t for w in ["bulk", "high volume", "large volume", "scale up", "scaling up"]):
        return "High volume (bulk)", 0.65

    return "", 0.0


def _find_budget(text: str) -> Tuple[str, float]:
    t = text.lower()

    # currency patterns
    m = re.search(r"(₹|rs\.?|inr|\$|usd|eur|gbp)\s*([\d,]+(\.\d+)?)", t)
    if m:
        return f"{m.group(1)} {m.group(2)}", 0.85

    # budget signals
    if any(w in t for w in ["low cost", "cheaper", "affordable", "budget", "tight budget", "limited budget", "cost sensitive"]):
        return "Budget-sensitive", 0.7

    if any(w in t for w in ["premium", "best quality", "top tier", "no budget issue"]):
        return "Premium-ready", 0.65

    # grant/academic often budget constrained
    if any(w in t for w in ["grant", "academic", "university", "student"]):
        return "Likely budget-sensitive (grant/academic)", 0.55

    return "", 0.0


def _find_throughput(text: str) -> Tuple[str, float]:
    t = text.lower()

    # numeric throughput e.g. 500 samples/week
    m = re.search(r"\b(\d+)\s*(samples|runs|tests|rxns|reactions)\s*/\s*(day|week|month)\b", t)
    if m:
        return f"{m.group(1)} {m.group(2)}/{m.group(3)}", 0.85

    if any(w in t for w in ["high throughput", "automation", "robot", "screening"]):
        return "High throughput", 0.7

    if any(w in t for w in ["small lab", "few samples", "pilot", "prototype"]):
        return "Low throughput", 0.6

    return "", 0.0


def _find_compliance(text: str) -> Tuple[str, float]:
    t = text.lower()
    keywords = [
        ("gmp", "GMP"),
        ("iso", "ISO"),
        ("ce", "CE"),
        ("fda", "FDA"),
        ("ivd", "IVD"),
        ("clinical", "Clinical"),
        ("validated", "Validated workflow"),
        ("ruo", "Research Use Only (RUO)"),
    ]
    for k, label in keywords:
        if re.search(rf"\b{k}\b", t):
            return label, 0.8

    # If not specified, assume RUO (most common) but low confidence
    return "Research Use Only (assumed)", 0.35


def _extract_constraints(text: str) -> Tuple[Dict[str, str], Dict[str, float]]:
    timeline, ct = _find_timeline(text)
    quantity, cq = _find_quantity(text)
    budget, cb = _find_budget(text)
    throughput, cth = _find_throughput(text)
    compliance, cc = _find_compliance(text)

    constraints = {
        "timeline": timeline,
        "quantity": quantity,
        "budget": budget,
        "throughput": throughput,
        "compliance": compliance,
    }
    conf = {
        "timeline": ct,
        "quantity": cq,
        "budget": cb,
        "throughput": cth,
        "compliance": cc,
    }
    return constraints, conf


def _deal_score(constraints: Dict[str, str], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Simple but useful scoring for demo:
    - Product relevance contributes
    - Quantity/Throughput indicates scale
    - Timeline indicates urgency
    - Budget indicates risk/opportunity
    """
    score = 0
    reasons = []

    # product relevance
    if matches:
        top = matches[0].get("score", 0)
        score += min(int(top) * 10, 30)
        reasons.append(f"Top product match score={top}")

    # urgency
    tl = (constraints.get("timeline") or "").lower()
    if "immediate" in tl or "within" in tl:
        score += 15
        reasons.append("Urgent timeline")
    elif tl:
        score += 8
        reasons.append("Timeline provided")

    # quantity
    qty = (constraints.get("quantity") or "").lower()
    if any(x in qty for x in ["bulk", "high volume"]):
        score += 15
        reasons.append("Bulk quantity intent")
    elif re.search(r"\b\d+\b", qty):
        score += 10
        reasons.append("Quantity provided")

    # throughput
    th = (constraints.get("throughput") or "").lower()
    if "high throughput" in th or re.search(r"\b\d+\b.*\/(day|week|month)\b", th):
        score += 12
        reasons.append("High throughput")

    # budget
    bd = (constraints.get("budget") or "").lower()
    if "budget-sensitive" in bd:
        score -= 5
        reasons.append("Price sensitivity risk")
    elif "premium" in bd or "$" in bd or "₹" in bd or "usd" in bd:
        score += 5
        reasons.append("Budget signal present")

    # clamp
    score = max(0, min(score, 100))
    band = "LOW" if score < 35 else "MODERATE" if score < 70 else "HIGH"

    return {"score": score, "band": band, "reasons": reasons}


def _confidence(req_explicit: List[Dict[str, Any]], req_implicit: List[Dict[str, Any]], constraint_conf: Dict[str, float]) -> int:
    # % confidence based on extracted signals
    c = 0.0
    c += min(len(req_explicit) * 0.15, 0.45)
    c += min(len(req_implicit) * 0.10, 0.25)
    c += min(sum(constraint_conf.values()) / 5.0 * 0.30, 0.30)
    return int(round(max(0.05, min(c, 0.98)) * 100))


def _questions_to_ask(constraints: Dict[str, str], matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    qs = []

    if not constraints.get("timeline"):
        qs.append({"missing_field": "timeline", "question_to_ask": "When do you need this delivered?", "priority": "high"})

    if not constraints.get("quantity"):
        qs.append({"missing_field": "quantity", "question_to_ask": "How many kits/units or how many samples will you process?", "priority": "high"})

    if "assumed" in (constraints.get("compliance") or "").lower():
        qs.append({"missing_field": "compliance", "question_to_ask": "Is this for RUO only, or do you need GMP/clinical-grade compliance?", "priority": "medium"})

    if not constraints.get("budget"):
        qs.append({"missing_field": "budget", "question_to_ask": "Do you have a target budget range or preferred tier (standard vs premium)?", "priority": "medium"})

    # product-specific
    if matches:
        top_name = matches[0].get("product_name", "")
        if "plasmid" in top_name.lower():
            qs.append({"missing_field": "workflow", "question_to_ask": "What plasmid size and expected yield range do you need?", "priority": "medium"})
        if any("nanodrop" in (m.get("product_name","").lower()) for m in matches):
            qs.append({"missing_field": "instrument", "question_to_ask": "Do you need a NanoDrop specifically or any UV-Vis microvolume spectrophotometer works?", "priority": "low"})

    return qs


# -----------------------------
# Agent
# -----------------------------
class RequirementsAgent:
    def _fallback_explicit(self, text: str):
        t = text.lower()
        out = []
        if "endotoxin" in t:
            out.append({"type":"Product Type","value":"Endotoxin-free plasmid kit","evidence":"endotoxin","confidence":0.8})
        if "transfection" in t:
            out.append({"type":"Application","value":"Transfection","evidence":"transfection","confidence":0.8})
        if "nanodrop" in t:
            out.append({"type":"Instrument","value":"NanoDrop / microvolume UV-Vis","evidence":"nanodrop","confidence":0.8})
        if "pcr" in t:
            out.append({"type":"Application","value":"PCR","evidence":"pcr","confidence":0.75})
        if "cloning" in t:
            out.append({"type":"Application","value":"Cloning","evidence":"cloning","confidence":0.75})
        return out

    def _fallback_implicit(self, text: str):
        t = text.lower()
        out = []
        if "endotoxin" in t or "transfection" in t:
            out.append({"type":"Quality","value":"High purity / transfection-grade","evidence":"endotoxin/transfection context","confidence":0.7})
        if any(x in t for x in ["500", "samples/week", "high throughput", "automation"]):
            out.append({"type":"Scale","value":"High throughput workflow likely required","evidence":"throughput signals","confidence":0.65})
        return out

    def __init__(self, settings, store: DataStore):
        self.settings = settings
        self.store = store

        llm_cfg = LLMConfig(
            provider=getattr(settings, "llm_provider", "gemini"),
            model=getattr(settings, "llm_model", "gemini-3-flash-preview"),
            temperature=float(getattr(settings, "llm_temperature", 0.2)),
            max_tokens=int(getattr(settings, "llm_max_tokens", 700)),
            gemini_api_key=getattr(settings, "GEMINI_API_KEY", None),
        )
        self.llm = build_llm(llm_cfg)

        self.catalog_top_k = int(getattr(settings, "catalog_top_k", 5))
        self.history_top_k = int(getattr(settings, "history_top_k", 5))

    def analyze(self, text: str, structured: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        structured = structured or {}
        text = _clean_text(text)
        company_name = (structured.get("company_name") or structured.get("company") or "").strip()

        # Use store wrappers (compatible)
        catalog_matches = self.store.search_catalog(text, top_k=self.catalog_top_k)
        company_deals = self.store.lookup_company_deals(company_name) if company_name else []
        similar_deals = self.store.search_history(text, top_k=self.history_top_k)

        # Extract constraints (rule-based always works)
        constraints, constraint_conf = _extract_constraints(text)

        # LLM extraction (explicit/implicit). If LLM fails, we’ll still show constraints + matches + questions.
        extracted = self._extract_requirements_llm(
            text=text,
            structured=structured,
            catalog_matches=catalog_matches,
            company_deals=company_deals,
            similar_deals=similar_deals,
            constraints=constraints,
        )

        # Normalize requirements
        req = extracted.get("requirements", {}) if isinstance(extracted, dict) else {}
        explicit = req.get("explicit") if isinstance(req.get("explicit"), list) else []
        implicit = req.get("implicit") if isinstance(req.get("implicit"), list) else []

        # Force constraints into output (with values)
        if "constraints" not in req or not isinstance(req.get("constraints"), dict):
            req["constraints"] = {}
        req["constraints"].update(constraints)
        extracted["requirements"] = req

        # Questions + scoring + confidence
        questions = extracted.get("gaps_and_questions")
        if not isinstance(questions, list) or not questions:
            questions = _questions_to_ask(constraints, catalog_matches)

        deal = _deal_score(constraints, catalog_matches)
        conf_pct = _confidence(explicit, implicit, constraint_conf)

        return {
            "customer": {
                "company_name": company_name,
                "company_seen_before": bool(company_deals),
            },
            "request_summary": {
                "one_line": extracted.get("request_summary", text[:160]),
                "raw_text_excerpt": text[:800],
            },
            "requirements": extracted.get("requirements", {}),
            "product_matches": catalog_matches,
            "history_context": {
                "company_deals": company_deals[:10],
                "most_similar_deals": similar_deals[:10],
            },
            "gaps_and_questions": questions,
            "deal_intelligence": {
                "deal_score": deal["score"],
                "deal_band": deal["band"],
                "reasons": deal["reasons"],
                "confidence_pct": conf_pct,
                "constraint_confidence": constraint_conf,
            },
        }

    def _extract_requirements_llm(
        self,
        text: str,
        structured: Dict[str, Any],
        catalog_matches: List[Dict[str, Any]],
        company_deals: List[Dict[str, Any]],
        similar_deals: List[Dict[str, Any]],
        constraints: Dict[str, str],
    ) -> Dict[str, Any]:
        system = (
            "You are an enterprise Sales Requirements Extraction Agent. "
            "Return ONLY valid JSON, no markdown. "
            "Extract explicit and implicit requirements from the sales text. "
            "Use catalog matches & history as context. "
            "Do NOT invent SKUs; only infer requirements and questions."
        )

        schema_hint = """
{
  "request_summary": "string",
  "requirements": {
    "explicit": [{"type":"string","value":"string","evidence":"string","confidence":0.0}],
    "implicit": [{"type":"string","value":"string","evidence":"string","confidence":0.0}],
    "constraints": {
      "timeline": "string",
      "quantity": "string",
      "budget": "string",
      "throughput": "string",
      "compliance": "string"
    }
  },
  "gaps_and_questions": [{"missing_field":"string","question_to_ask":"string","priority":"low|medium|high"}]
}
""".strip()

        payload = {
            "sales_rep_text": text,
            "structured_fields": structured,
            "detected_constraints_preliminary": constraints,
            "top_catalog_matches": catalog_matches,
            "company_purchase_history": company_deals[:5],
            "similar_historic_deals": similar_deals[:5],
        }

        out = self.llm.generate_json(system=system, user=f"INPUT:\n{payload}", schema_hint=schema_hint)

        if not isinstance(out, dict):
            out = {}

        out.setdefault("request_summary", text[:160])
        out.setdefault("requirements", {})
        if not isinstance(out["requirements"], dict):
            out["requirements"] = {}

        req = out["requirements"]
        req.setdefault("explicit", [])
        req.setdefault("implicit", [])
        req.setdefault("constraints", {})
        if not isinstance(req["constraints"], dict):
            req["constraints"] = {}

        # Ensure keys exist
        for k in ["timeline", "quantity", "budget", "throughput", "compliance"]:
            req["constraints"].setdefault(k, "")

        out.setdefault("gaps_and_questions", [])
        if not isinstance(out["gaps_and_questions"], list):
            out["gaps_and_questions"] = []

        return out
