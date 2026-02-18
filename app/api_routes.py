from __future__ import annotations
from fastapi import APIRouter
from app.routes.analyze import router as analyze_router
from app.routes.health import router as health_router
from app.routes.quote import router as quote_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(analyze_router, tags=["analyze"])

router.include_router(analyze_router)
router.include_router(quote_router)
