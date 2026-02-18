import pandas as pd

HISTORY_XLSX = "data/product_history.xlsx"

def build_price_catalog() -> dict:
    df = pd.read_excel(HISTORY_XLSX)

    # ✅ Clean column names: remove leading/trailing spaces
    df.columns = [c.strip() for c in df.columns]

    # ✅ Auto-find profit column robustly
    profit_col = None
    for c in df.columns:
        if c.lower() == "profit":
            profit_col = c
            break
    if profit_col is None:
        raise ValueError(f"Profit column not found. Available columns: {list(df.columns)}")

    if "product_names_purchased" not in df.columns:
        raise ValueError(f"'product_names_purchased' not found. Available: {list(df.columns)}")

    catalog = {}
    counts = {}

    for _, row in df.iterrows():
        names = str(row.get("product_names_purchased", "")).strip()
        profit = float(row.get(profit_col, 0) or 0)

        if not names:
            continue

        products = [p.strip() for p in names.split(",") if p.strip()]
        if not products:
            continue

        per_item = profit / len(products)

        for p in products:
            catalog[p] = catalog.get(p, 0) + per_item
            counts[p] = counts.get(p, 0) + 1

    # average estimate
    for p in list(catalog.keys()):
        catalog[p] = round(catalog[p] / counts[p], 2)

    return catalog


def price_products(requested_products: list[str], catalog: dict) -> tuple[list[dict], float]:
    items = []
    total = 0.0

    for prod in requested_products:
        prod = prod.strip()
        price = catalog.get(prod)

        # fallback: fuzzy containment match
        if price is None:
            hit = None
            for k in catalog.keys():
                if prod.lower() in k.lower() or k.lower() in prod.lower():
                    hit = k
                    break
            price = catalog.get(hit, 0.0) if hit else 0.0

        price = float(price or 0.0)
        items.append({"product": prod, "unit_price": price})
        total += price

    return items, round(total, 2)
