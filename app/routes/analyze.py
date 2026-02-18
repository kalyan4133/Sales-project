from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Any, Dict, Optional

from app.core.settings import Settings
from app.services.store import DataStore
from app.services.agent import RequirementsAgent
from app.services.file_extractor import extract_text_from_upload

router = APIRouter(prefix="/analyze", tags=["analyze"])

_settings = Settings()
_store = DataStore()

_agent = RequirementsAgent(_settings, _store)


class AnalyzeTextRequest(BaseModel):
    text: str
    structured: Optional[Dict[str, Any]] = None


@router.get("/debug/store")
def debug_store():
    return _store.stats()


@router.post("/text")
def analyze_text(payload: AnalyzeTextRequest):
    try:
        return _agent.analyze(payload.text, payload.structured)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/file")
async def analyze_file(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        text, filetype = extract_text_from_upload(file.filename or "upload", raw)

        if not text or len(text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail=f"Could not extract readable text from {file.filename} ({filetype}). Try TXT/DOCX/PDF/CSV/XLSX with real text."
            )

        return _agent.analyze(text, structured={})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    print("---- EXTRACTED TEXT START ----")
    print(text[:1200])
    print("---- EXTRACTED TEXT END ----")
    print("Extracted length:", len(text))

