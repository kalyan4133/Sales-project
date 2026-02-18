from pydantic import BaseModel, Field
from typing import Any, Literal

class EvidenceItem(BaseModel):
    type: str
    value: str
    evidence: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

class Constraints(BaseModel):
    timeline: str | None = None
    quantity: str | None = None
    budget: str | None = None
    compliance: str | None = None
    throughput: str | None = None

class RequirementBlock(BaseModel):
    explicit: list[EvidenceItem] = Field(default_factory=list)
    implicit: list[EvidenceItem] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)

class ProductMatch(BaseModel):
    product_name: str
    product_id_from_history: str | None = None
    match_reason: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

class SimilarDeal(BaseModel):
    deal_id: str
    company_name: str
    products: list[str]
    profit: float | int | None = None
    similarity: float = Field(ge=0.0, le=1.0, default=0.0)

class HistoryContext(BaseModel):
    company_seen_before: bool
    similar_companies: list[str] = Field(default_factory=list)
    most_similar_deals: list[SimilarDeal] = Field(default_factory=list)

class GapQuestion(BaseModel):
    missing_field: str
    question_to_ask: str
    priority: Literal["low","medium","high"] = "medium"

class CustomerBlock(BaseModel):
    company_name: str | None = None
    company_id_match: str | None = None
    contact_person: str | None = None
    region: str | None = None

class RequestSummary(BaseModel):
    one_line: str
    raw_text_excerpt: str

class RequirementOutput(BaseModel):
    customer: CustomerBlock
    request_summary: RequestSummary
    requirements: RequirementBlock
    product_matches: list[ProductMatch]
    history_context: HistoryContext
    gaps_and_questions: list[GapQuestion] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)
