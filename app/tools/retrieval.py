from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import json
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

@dataclass
class CatalogItem:
    product_id: str | None
    product_name: str
    description: str
    use_case: str
    key_features: str
    keywords: list[str]

    @property
    def text(self) -> str:
        return " | ".join([
            self.product_name,
            self.description,
            self.use_case,
            self.key_features,
            ", ".join(self.keywords or [])
        ])

class RetrievalStore:
    """In-memory TF-IDF store for catalog + historic deal similarity."""
    def __init__(self, catalog_items: list[CatalogItem], deals_df: pd.DataFrame, max_features: int = 20000):
        self.catalog_items = catalog_items
        self.deals_df = deals_df.copy()
        # normalize columns
        self.deals_df.columns = [c.strip() for c in self.deals_df.columns]

        # Build catalog index
        self._catalog_vec = TfidfVectorizer(max_features=max_features, ngram_range=(1,2))
        self._catalog_matrix = self._catalog_vec.fit_transform([c.text for c in self.catalog_items])

        # Build deal index (for similarity against request)
        self._deal_vec = TfidfVectorizer(max_features=max_features, ngram_range=(1,2))
        deal_texts = []
        for _, r in self.deals_df.iterrows():
            deal_texts.append(f"{r.get('company_name','')} | {r.get('product_names_purchased','')}")
        self._deal_matrix = self._deal_vec.fit_transform(deal_texts)

    @staticmethod
    def load(catalog_json_path: str, history_csv_path: str, max_features: int = 20000) -> "RetrievalStore":
        with open(catalog_json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        catalog_items = []
        for r in raw:
            catalog_items.append(CatalogItem(
                product_id=r.get("product_id"),
                product_name=r.get("product_name",""),
                description=r.get("description",""),
                use_case=r.get("use_case",""),
                key_features=r.get("key_features",""),
                keywords=r.get("keywords") or []
            ))

        deals_df = pd.read_csv(history_csv_path)
        return RetrievalStore(catalog_items=catalog_items, deals_df=deals_df, max_features=max_features)

    def search_catalog(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q = self._catalog_vec.transform([query])
        sims = cosine_similarity(q, self._catalog_matrix).flatten()
        idxs = sims.argsort()[::-1][:top_k]
        out = []
        for i in idxs:
            item = self.catalog_items[int(i)]
            out.append({
                "product_id": item.product_id,
                "product_name": item.product_name,
                "score": float(sims[int(i)]),
                "description": item.description,
                "use_case": item.use_case,
                "keywords": item.keywords
            })
        return out

    def search_deals(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q = self._deal_vec.transform([query])
        sims = cosine_similarity(q, self._deal_matrix).flatten()
        idxs = sims.argsort()[::-1][:top_k]
        out = []
        for i in idxs:
            r = self.deals_df.iloc[int(i)].to_dict()
            r["score"] = float(sims[int(i)])
            out.append(r)
        return out

    def lookup_company(self, company_name: str) -> dict[str, Any] | None:
        if not company_name:
            return None
        # exact-ish match
        matches = self.deals_df[self.deals_df["company_name"].str.lower() == company_name.lower()]
        if matches.empty:
            return None
        # pick most recent row order (as given) – you can replace with a date column later
        r = matches.iloc[-1].to_dict()
        return r

    def company_deals(self, company_name: str) -> list[dict[str, Any]]:
        if not company_name:
            return []
        matches = self.deals_df[self.deals_df["company_name"].str.lower() == company_name.lower()]
        return [r.to_dict() for _, r in matches.iterrows()]
