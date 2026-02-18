from __future__ import annotations

from fastapi import APIRouter, Request, Form
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import json

from quote_agents.graph import GRAPH

router = APIRouter(prefix="/quote", tags=["quote"])

templates = Jinja2Templates(directory="templates_quote")

# shared in-memory store for demo
DEALS: dict[str, dict] = {}

class ProductViewRequest(BaseModel):
    product_name: str

@router.get("", response_class=HTMLResponse)
def new_deal(
    request: Request,
    deal_id: str | None = None,
    company_name: str | None = None,
    products: str | None = None,
    products_json: str | None = None,
):
    # Pre-fill if coming from Sales Requirements
    return templates.TemplateResponse("index.html", {
        "request": request,
        "prefill": {
            "deal_id": deal_id or "",
            "company_name": company_name or "",
            "products": products or "",
            "products_json": products_json or "",
        }
    })

@router.post("/generate-quote", response_class=HTMLResponse)
def generate_quote(
    request: Request,
    deal_id: str = Form(...),
    company_name: str = Form(...),
    products: str = Form(""),
    products_json: str = Form(""),
):
    # Prefer JSON list if provided; fall back to comma-separated string
    product_list: list[str] = []
    if products_json:
        try:
            product_list = [str(p).strip() for p in json.loads(products_json) if str(p).strip()]
        except Exception:
            product_list = []
    if not product_list:
        product_list = [p.strip() for p in (products or "").replace("\n", ",").split(",") if p.strip()]

    state = {
        "deal_id": deal_id,
        "company_name": company_name,
        "products": product_list,
    }

    try:
        out = GRAPH.invoke(state)
        DEALS[deal_id] = out
    except Exception as e:
        # Surface a clean error page instead of 500 blank
        return templates.TemplateResponse("index.html", {
            "request": request,
            "prefill": {"deal_id": deal_id, "company_name": company_name, "products": products, "products_json": products_json},
            "error": f"Internal Server Error while generating quote: {type(e).__name__}: {e}",
        })

    return templates.TemplateResponse("quote.html", {
        "request": request,
        "deal": out
    })

@router.post("/reprice", response_class=JSONResponse)
def reprice(
    deal_id: str = Form(...),
    company_name: str = Form(...),
    products: str = Form(""),
    products_json: str = Form(""),
):
    product_list: list[str] = []
    if products_json:
        try:
            product_list = [str(p).strip() for p in json.loads(products_json) if str(p).strip()]
        except Exception:
            product_list = []
    if not product_list:
        product_list = [p.strip() for p in (products or "").replace("\n", ",").split(",") if p.strip()]
    state = {"deal_id": deal_id, "company_name": company_name, "products": product_list}
    out = GRAPH.invoke(state)
    DEALS[deal_id] = out
    return out

@router.get("/insights/{deal_id}", response_class=HTMLResponse)
def insights(request: Request, deal_id: str):
    deal = DEALS.get(deal_id)
    if not deal:
        return HTMLResponse("<h2>Deal not found</h2>", status_code=404)

    return templates.TemplateResponse("insights.html", {
        "request": request,
        "deal": deal
    })

@router.post("/quote/product/view")
def view_product(req: ProductViewRequest):
    # Read from your dataset (example: product_history.csv/xlsx)
    data_dir = Path("data")
    csv_path = data_dir / "product_history.csv"
    xlsx_path = data_dir / "product_history.xlsx"

    df = None
    if csv_path.exists():
        df = pd.read_csv(csv_path)
    elif xlsx_path.exists():
        df = pd.read_excel(xlsx_path)

    product_id = None
    if df is not None and "product_name" in df.columns:
        hit = df[df["product_name"].astype(str).str.lower() == req.product_name.lower()]
        if not hit.empty:
            # adapt column name if your dataset uses different key
            for col in ["product_id", "id", "sku", "Product ID"]:
                if col in hit.columns:
                    product_id = str(hit.iloc[0][col])
                    break

    return {
        "product_name": req.product_name,
        "product_id": product_id or "TBD",
        "pros": [],
        "cons": [],
        "graph": {"labels": [], "values": []},
        "reason_to_buy": ""
    }