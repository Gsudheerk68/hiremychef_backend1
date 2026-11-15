"""Phase 1: build a learning-to-rank dataset.
Run: python -m scripts.ml_build_dataset
Output: data/ml/train.csv  (one row per query-chef pair)
"""
import csv
import math
import random
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

N_QUERIES = 600
SEED = 42
OUT = Path("data/ml/train.csv")

EVENT_FACTOR = {"Family dinner": 1.0, "Weekly meals": 0.9, "Birthday": 1.15,
                "Festival": 1.1, "Corporate": 1.3, "Wedding": 1.5}


def estimate_price(base: float, guests: int, event: str) -> int:
    """Same rule as your booking price: base covers 6 guests, +6% per extra."""
    extra = max(0, guests - 6)
    price = base * (1 + 0.06 * extra) * EVENT_FACTOR[event]
    return int(round(price / 50) * 50)


def load_chefs() -> list[dict]:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models.chef import ChefProfile

    # Works whether app/db/session.py exposes SessionLocal or only an engine
    try:
        from app.db.session import SessionLocal
        db_ctx = SessionLocal()
    except ImportError:
        from app.db.session import engine
        db_ctx = Session(engine)

    with db_ctx as db:
        rows = db.scalars(
            select(ChefProfile).where(ChefProfile.is_verified.is_(True))
        ).all()
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
                "base_price": float(c.price_per_session or 0),
                "text": f"{' '.join(cuisines)} {' '.join(cuisines)} "
                        f"{c.city or ''} {c.bio or ''}",
            })
        return chefs


def make_query(chefs: list[dict], rng: random.Random) -> dict:
    cuisines = sorted({x for c in chefs for x in c["cuisines"]})
    cities = sorted({c["city"] for c in chefs if c["city"]})
    q = {
        "cuisine": rng.choice(cuisines),
        "city": rng.choice(cities),
        "event": rng.choice(list(EVENT_FACTOR)),
        "guests": rng.choice([4, 6, 8, 10, 15, 20, 30, 50]),
    }
    q["budget"] = int(rng.choice([2000, 3000, 5000, 8000, 12000, 20000]))
    templates = [
        "{cuisine} chef for {event} for {guests} people in {city}, budget {budget}",
        "need a {cuisine} cook in {city} for a {event}, {guests} guests",
        "{event} in {city}, {guests} people, {cuisine} food under {budget}",
        "{cuisine} chef {city}",
    ]
    q["text"] = rng.choice(templates).format(**q)
    return q


def simulated_relevance(q: dict, c: dict, price: int, rng: random.Random) -> int:
    """Pretend-user preference model. Replaced by real clicks/bookings in Phase 5."""
    cuisine_match = 1.0 if q["cuisine"] in c["cuisines"] else 0.0
    city_match = 1.0 if q["city"] == c["city"] else 0.0
    over = max(0.0, price - q["budget"]) / q["budget"]
    budget_fit = max(0.0, 1.0 - over)
    trust = min(1.0, math.log1p(c["reviews"]) / math.log1p(50))
    score = (2.0 * cuisine_match + 1.2 * city_match + 1.0 * budget_fit
             + 0.8 * c["rating"] / 5 + 0.3 * trust + 0.2 * min(c["years"], 20) / 20)
    score += rng.gauss(0, 0.25)                 # people are not perfectly consistent
    return int(np.clip(round(score / 5.5 * 3), 0, 3))


def main() -> None:
    rng = random.Random(SEED)
    chefs = load_chefs()
    if len(chefs) < 10:
        raise SystemExit(
            f"Found only {len(chefs)} verified chefs; need at least ~10. "
            "Run: python -m scripts.seed_demo && python -m scripts.seed_ai_demo"
        )

    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    chef_matrix = tfidf.fit_transform([c["text"] for c in chefs])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["qid", "chef_id", "label", "tfidf_sim", "cuisine_match", "city_match",
            "budget_fit", "price_ratio", "rating", "reviews_log", "years",
            "guests", "event_idx", "query_text"]
    events = list(EVENT_FACTOR)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for qid in range(N_QUERIES):
            q = make_query(chefs, rng)
            sims = cosine_similarity(tfidf.transform([q["text"]]), chef_matrix).ravel()
            for c, sim in zip(chefs, sims):
                price = estimate_price(c["base_price"], q["guests"], q["event"])
                over = max(0.0, price - q["budget"]) / q["budget"]
                w.writerow([
                    qid, c["id"],
                    simulated_relevance(q, c, price, rng),
                    round(float(sim), 4),
                    int(q["cuisine"] in c["cuisines"]),
                    int(q["city"] == c["city"]),
                    round(max(0.0, 1.0 - over), 4),
                    round(price / q["budget"], 4),
                    c["rating"],
                    round(math.log1p(c["reviews"]), 4),
                    c["years"],
                    q["guests"],
                    events.index(q["event"]),
                    q["text"],
                ])
    print(f"Wrote {N_QUERIES} queries x {len(chefs)} chefs -> {OUT}")


if __name__ == "__main__":
    main()
