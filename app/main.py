from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api_routes import router as api_router

app = FastAPI(title="Sales Requirements Agent (Gemini)")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/static_quote", StaticFiles(directory="static_quote"), name="static_quote")
templates = Jinja2Templates(directory="templates")

app.include_router(api_router)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    return templates.TemplateResponse("output.html", {"request": request})

@app.get("/health")
def health():
    return {"status": "ok"}
