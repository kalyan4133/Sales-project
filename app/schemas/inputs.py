from pydantic import BaseModel, Field
from typing import Any

class AnalyzeTextRequest(BaseModel):
    text: str = Field(min_length=1)
    structured: dict[str, Any] | None = None  # optional structured fields from a form
