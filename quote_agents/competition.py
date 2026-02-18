import pandas as pd

COMPETITORS_CSV = "data/competitors.csv"

POSITION_SCORE = {
    "Competitor Advantage": 0.85,
    "Neutral": 0.55,
    "Thermo Advantage": 0.25,
}

def load_competitors():
    df = pd.read_csv(COMPETITORS_CSV)
    df.columns = [c.strip() for c in df.columns]
    # columns include: thermo_product, comparative_position, competitor_company, competitor_product, ...
    return df

def compute_market_competition(products: list[str], df: pd.DataFrame) -> dict:
    results = []
    for p in products:
        # Match against thermo_product (primary) and competitor_product (secondary)
        m = df[
            df["thermo_product"].astype(str).str.contains(p, case=False, na=False)
            | df["competitor_product"].astype(str).str.contains(p, case=False, na=False)
        ].copy()

        if m.empty:
            results.append({
                "product": p,
                "competition_score": 0.5,
                "matched_rows": 0,
                "top_competitor": "Unknown",
                "position": "Unknown"
            })
            continue

        # pick highest “risk” competitor advantage first
        m["score"] = m["comparative_position"].map(POSITION_SCORE).fillna(0.55)
        top = m.sort_values("score", ascending=False).iloc[0]

        results.append({
            "product": p,
            "competition_score": round(float(top["score"]), 2),
            "matched_rows": int(len(m)),
            "top_competitor": str(top.get("competitor_company", "Unknown")),
            "position": str(top.get("comparative_position", "Unknown")),
            "summary": str(top.get("net_assessment_summary", ""))[:240]
        })

    overall = round(sum(r["competition_score"] for r in results) / len(results), 2) if results else 0.5
    coverage = sum(1 for r in results if r["matched_rows"] > 0) / max(len(results), 1)

    return {
        "overall_market_competition": overall,
        "coverage": round(coverage, 2),
        "by_product": results
    }
