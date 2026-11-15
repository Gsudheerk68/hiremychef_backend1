"""Scores filtered candidate chefs with the trained LightGBM ranker and explains the scores.

Chef text, TF-IDF settings and features must match scripts/ml_build_dataset_v2.py.
Returns None whenever ML scoring is unavailable, so the caller can fall back.
"""
import hashlib
import logging
import math
import os
import statistics
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import encode, similarity
from app.models.chef import ChefProfile

log = logging.getLogger(__name__)

MODEL_PATH = Path(os.getenv("ML_RANKER_PATH", "data/ml/ranker_v2.joblib"))

# Event order used in training (event_idx = position in this list)
TRAIN_EVENTS = ["Family dinner", "Weekly meals", "Birthday", "Festival", "Corporate", "Wedding"]
# Parser event names -> training event names
PARSER_TO_TRAIN = {
    "Family dinner": "Family dinner",
    "Weekly meals": "Weekly meals",
    "Birthday party": "Birthday",
    "Festival / Pooja": "Festival",
    "Corporate event": "Corporate",
    "Wedding / Reception": "Wedding",
}
DEFAULT_GUESTS = 6
FALLBACK_BUDGET = 5000

# (text when the factor raised the score, text when it lowered it)
FACTOR_TEXT = {
    "match": ("Matches what you described", "Weak match with what you described"),
    "cuisine": ("Cooks the cuisine you asked for", "Does not list that cuisine"),
    "city": ("Based in your city", "Not based in your city"),
    "budget": ("Price fits your budget", "Price is high for your budget"),
    "rating": ("High customer rating", "Lower customer rating"),
    "reviews": ("Well reviewed", "Few reviews so far"),
    "experience": ("Experienced chef", "Less experience"),
}


def is_enabled() -> bool:
    return os.getenv("ML_RANKER_ENABLED", "1") != "0" and MODEL_PATH.exists()


@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODEL_PATH)  # pickle: only load files this project wrote


def _load_chefs(db: Session) -> list[dict]:
    rows = db.scalars(select(ChefProfile).where(ChefProfile.is_verified.is_(True))).all()
    chefs = []
    for c in rows:
        cuisines = [str(x).strip().lower() for x in (c.cuisines or [])]
        chefs.append({
            "id": c.id,
            "city": (c.city or "").strip().lower(),
            "cuisines": cuisines,
            "years": c.years_experience or 0,
            "rating": float(c.rating_avg or 0),
            "reviews": c.review_count or 0,
            "text": f"{' '.join(cuisines)} {' '.join(cuisines)} {c.city or ''} {c.bio or ''}",
        })
    return chefs


@dataclass
class _TextIndex:
    signature: str
    tfidf: TfidfVectorizer
    matrix: object
    vecs: np.ndarray


_index: _TextIndex | None = None


def _get_index(chefs: list[dict]) -> _TextIndex:
    """Re-fit TF-IDF and embeddings only when chef text changes."""
    global _index
    sig = hashlib.md5("\n".join(f"{c['id']}:{c['text']}" for c in chefs).encode()).hexdigest()
    if _index is None or _index.signature != sig:
        texts = [c["text"] for c in chefs]
        tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        _index = _TextIndex(sig, tfidf, tfidf.fit_transform(texts), encode(texts))
    return _index


def _explain(contrib_row, features: list[str], has_cuisine: bool, has_city: bool, has_budget: bool) -> list[dict]:
    """Turn one row of LightGBM contributions (last value = base score) into readable factors.
    Only factors the customer actually asked about are included."""
    c = dict(zip(features, (float(x) for x in contrib_row[:-1])))
    parts = {
        "match": c.get("tfidf_sim", 0.0) + c.get("embed_sim", 0.0),
        "rating": c.get("rating", 0.0),
        "reviews": c.get("reviews_log", 0.0),
        "experience": c.get("years", 0.0),
    }
    if has_cuisine:
        parts["cuisine"] = c.get("cuisine_match", 0.0)
    if has_city:
        parts["city"] = c.get("city_match", 0.0)
    if has_budget:
        parts["budget"] = c.get("budget_fit", 0.0) + c.get("price_ratio", 0.0)

    total = sum(abs(v) for v in parts.values()) or 1.0
    out = []
    for key, value in sorted(parts.items(), key=lambda kv: -abs(kv[1])):
        weight = round(abs(value) / total * 100)
        if weight < 5:
            continue  # too small to mention
        up_text, down_text = FACTOR_TEXT[key]
        out.append({"label": up_text if value >= 0 else down_text,
                    "direction": "up" if value >= 0 else "down",
                    "weight": weight})
    return out[:4]


def score_candidates(
    db: Session,
    query_text: str,
    parsed,                              # app.ai.parser.ParsedQuery
    candidate_ids: set[int],
    price_fn: Callable[[int], int],      # chef_id -> estimated price (same one shown to the user)
) -> tuple[dict[int, float], dict[int, list[dict]]] | None:
    """Returns (scores, factors) keyed by chef id, or None when ML scoring is unavailable."""
    if not is_enabled() or not candidate_ids:
        return None
    try:
        bundle = _bundle()
        chefs = _load_chefs(db)
        idx = _get_index(chefs)

        tf = cosine_similarity(idx.tfidf.transform([query_text]), idx.matrix).ravel()
        emb = similarity(encode([query_text]), idx.vecs).ravel()

        picked = [(i, c) for i, c in enumerate(chefs) if c["id"] in candidate_ids]
        if not picked:
            return None
        prices = {c["id"]: price_fn(c["id"]) for _, c in picked}

        budget = float(parsed.budget) if parsed.budget else statistics.median(prices.values())
        budget = budget if budget > 0 else FALLBACK_BUDGET
        guests = parsed.guests or DEFAULT_GUESTS
        event = PARSER_TO_TRAIN.get(parsed.event_type or "", "Family dinner")
        city = (parsed.city or "").strip().lower()
        want = {x.strip().lower() for x in parsed.cuisines}

        rows = []
        for i, c in picked:
            price = prices[c["id"]]
            over = max(0.0, price - budget) / budget
            rows.append({
                "tfidf_sim": float(tf[i]),
                "embed_sim": float(emb[i]),
                "cuisine_match": int(bool(want & set(c["cuisines"]))),
                "city_match": int(bool(city) and city == c["city"]),
                "budget_fit": max(0.0, 1.0 - over),
                "price_ratio": price / budget,
                "rating": c["rating"],
                "reviews_log": math.log1p(c["reviews"]),
                "years": c["years"],
                "guests": guests,
                "event_idx": TRAIN_EVENTS.index(event),
            })
        X = pd.DataFrame(rows)[bundle["features"]]
        preds = bundle["model"].predict(X)
        scores = {c["id"]: float(s) for (_, c), s in zip(picked, preds)}

        factors: dict[int, list[dict]] = {}
        try:  # explanations are a bonus: never let them break ranking
            contribs = bundle["model"].predict(X, pred_contrib=True)
            for (_, c), row in zip(picked, contribs):
                factors[c["id"]] = _explain(row, bundle["features"], bool(want), bool(city), bool(parsed.budget))
        except Exception:
            log.exception("Could not compute ranking explanations")
        return scores, factors
    except Exception:
        log.exception("ML ranker failed; falling back to the weighted formula")
        return None
