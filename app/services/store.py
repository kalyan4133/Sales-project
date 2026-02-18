from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import re
import pandas as pd


class DataStore:
    def __init__(self):
        # Resolve project root dynamically (app/services -> app -> project root)
        project_root = Path(__file__).resolve().parents[2]

        self.history_path = project_root / "data" / "product_history.csv"
        self.catalog_path = project_root / "data" / "lab_products.txt"

        self.history_df = self._load_history()
        self.catalog = self._load_catalog()

        # build index once
        self._catalog_vec = None
        self._catalog_matrix = None
        self._build_catalog_index()

    # -----------------------------
    # Load history CSV
    # -----------------------------
    def _load_history(self):
        if not self.history_path.exists():
            raise FileNotFoundError(f"History file not found: {self.history_path}")

        df = pd.read_csv(self.history_path)
        df.columns = [c.strip().lower() for c in df.columns]
        return df

    # -----------------------------
    # Parse lab_products.txt
    # -----------------------------
    def _load_catalog(self) -> List[Dict[str, Any]]:
        if not self.catalog_path.exists():
            raise FileNotFoundError(f"Catalog file not found: {self.catalog_path}")

        raw = self.catalog_path.read_text(encoding="utf-8")
        blocks = re.split(r"\n\s*\d+\.\s+", raw)
        catalog: List[Dict[str, Any]] = []

        for block in blocks[1:]:
            lines = block.strip().split("\n")
            if not lines:
                continue

            product_name = lines[0].strip()

            description = self._extract_field(block, "Description")
            use_case = self._extract_field(block, "Use Case")
            key_features = self._extract_field(block, "Key Features")
            keywords = self._extract_field(block, "Keywords")

            catalog.append(
                {
                    "product_name": product_name,
                    "description": description,
                    "use_case": use_case,
                    "key_features": key_features,
                    "keywords": (keywords or "").lower(),
                }
            )

        return catalog

    def _extract_field(self, text: str, field: str) -> str:
        m = re.search(rf"{re.escape(field)}:\s*(.*)", text)
        return m.group(1).strip() if m else ""

    # -----------------------------
    # Matching (TF-IDF based)
    # -----------------------------
    def _build_catalog_index(self):
        """Build TF-IDF index for catalog items for better matching."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except Exception:
            self._catalog_vec = None
            self._catalog_matrix = None
            return

        texts = []
        for item in self.catalog:
            texts.append(
                " | ".join(
                    [
                        item.get("product_name", ""),
                        item.get("description", ""),
                        item.get("use_case", ""),
                        item.get("key_features", ""),
                        item.get("keywords", ""),
                    ]
                )
            )

        if not texts:
            self._catalog_vec = None
            self._catalog_matrix = None
            return

        self._catalog_vec = TfidfVectorizer(
            max_features=20000, ngram_range=(1, 2), stop_words="english"
        )
        self._catalog_matrix = self._catalog_vec.fit_transform(texts)

    def _ensure_index(self):
        if self._catalog_vec is None or self._catalog_matrix is None:
            self._build_catalog_index()

    def match_products(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Return top matching products from lab_products.txt with explainability."""
        q = (query or "").strip()
        if not q:
            return []

        self._ensure_index()

        # Fallback to keyword scoring if TF-IDF unavailable
        if self._catalog_vec is None or self._catalog_matrix is None:
            ql = q.lower()
            matches = []
            for item in self.catalog:
                score = 0
                reasons = []
                name = (item.get("product_name") or "")
                if name and name.lower() in ql:
                    score += 3
                    reasons.append(f"Product name mentioned: '{name}'")
                for token in (item.get("keywords") or "").split(","):
                    t = token.strip().lower()
                    if t and t in ql:
                        score += 1
                        reasons.append(f"Keyword match: '{t}'")
                if score > 0:
                    matches.append(
                        {
                            **item,
                            "score": score,
                            "confidence": min(1.0, score / 6.0),
                            "match_reason": reasons or ["Keyword overlap"],
                        }
                    )
            matches.sort(key=lambda x: x.get("score", 0), reverse=True)
            return matches[:top_k]

        from sklearn.metrics.pairwise import cosine_similarity

        q_vec = self._catalog_vec.transform([q])
        sims = cosine_similarity(q_vec, self._catalog_matrix).flatten()
        idxs = sims.argsort()[::-1][:top_k]

        q_tokens = set(
            [t for t in re.findall(r"[a-zA-Z0-9]+", q.lower()) if len(t) > 2]
        )

        out = []
        for i in idxs:
            item = self.catalog[int(i)]
            score = float(sims[int(i)])

            kw_tokens = set(
                [t.strip().lower() for t in (item.get("keywords") or "").split(",") if t.strip()]
            )
            overlap = sorted(list(q_tokens & kw_tokens))[:8]

            reasons = []
            if overlap:
                reasons.append("Matched keywords: " + ", ".join(overlap))

            name_tokens = set(
                [t for t in re.findall(r"[a-zA-Z0-9]+", (item.get("product_name") or "").lower()) if len(t) > 2]
            )
            name_overlap = sorted(list(q_tokens & name_tokens))[:6]
            if name_overlap:
                reasons.append("Matched name terms: " + ", ".join(name_overlap))

            if item.get("use_case"):
                reasons.append("Use case aligns with request context.")

            if not reasons:
                reasons.append("High semantic similarity to the request description (TF-IDF).")

            out.append(
                {
                    **item,
                    "score": score,
                    "confidence": max(0.0, min(1.0, score)),
                    "match_reason": reasons,
                }
            )
        return out

    # -----------------------------
    # History helpers (used by requirements pipeline)
    # -----------------------------
    def get_company_history(self, company: str):
        if "company_name" not in self.history_df.columns:
            return []
        df = self.history_df[self.history_df["company_name"].astype(str).str.lower() == company.lower()]
        return df.to_dict(orient="records")

    def stats(self):
        return {"catalog_items": len(self.catalog), "history_rows": len(self.history_df)}

    # Backward compatibility wrappers
    def search_catalog(self, text: str, top_k: int = 5):
        return self.match_products(text, top_k=top_k)

    def lookup_company_deals(self, company_name: str):
        return self.get_company_history(company_name)

    def search_history(self, text: str, top_k: int = 5):
        """Simple history similarity (kept stable for POC)."""
        if self.history_df is None or self.history_df.empty:
            return []
        q = (text or "").lower().strip()
        if not q:
            return []
        q_terms = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 2]
        if not q_terms:
            return []
        rows = []
        for _, row in self.history_df.iterrows():
            blob = " ".join([str(v) for v in row.values]).lower()
            hits = sum(1 for t in q_terms if t in blob)
            if hits:
                rows.append((hits, row.to_dict()))
        rows.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in rows[:top_k]]
