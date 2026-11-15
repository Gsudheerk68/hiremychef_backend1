"""Phase 3: dataset with vibe queries and an embedding-similarity feature.
Run: python -m scripts.ml_build_dataset_v2
Output: data/ml/train_v2.csv
"""
import csv
import math
import random
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.ai.embeddings import encode, similarity
from scripts.ml_build_dataset import (
    EVENT_FACTOR, estimate_price, load_chefs, make_query, simulated_relevance,
)

N_QUERIES = 800
SEED = 7
OUT = Path("data/ml/train_v2.csv")

# phrase the user types -> words that, if in a chef's bio, make the chef a true match
VIBES = {
    "something light and nutritious": ["healthy", "light", "low-oil", "low oil", "nutritious", "diet"],
    "very spicy authentic food": ["spicy", "authentic", "fiery", "chilli", "chili"],
    "traditional home-style cooking": ["traditional", "home-style", "homestyle", "authentic", "heritage"],
    "pure vegetarian meals": ["vegetarian", "veg", "satvik", "sattvic"],
    "grand festive feast": ["feast", "festive", "wedding", "banquet", "catering"],
    "kid friendly mild dishes": ["kids", "kid-friendly", "children", "mild"],
}


def main() -> None:
    rng = random.Random(SEED)
    chefs = load_chefs()
    if len(chefs) < 10:
        raise SystemExit("Need at least ~10 verified chefs (run the seed scripts).")

    # 1) build all queries first, so we can embed them in one batch
    queries = []
    for _ in range(N_QUERIES):
        q = make_query(chefs, rng)
        q["vibe"] = rng.choice(list(VIBES)) if rng.random() < 0.6 else None
        if q["vibe"]:
            q["text"] = f"{q['text']}, {q['vibe']}"
        queries.append(q)

    chef_texts = [c["text"] for c in chefs]
    chef_vecs = encode(chef_texts)
    query_vecs = encode([q["text"] for q in queries])
    embed_sims = similarity(query_vecs, chef_vecs)

    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    chef_matrix = tfidf.fit_transform(chef_texts)
    events = list(EVENT_FACTOR)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["qid", "chef_id", "label", "tfidf_sim", "embed_sim", "cuisine_match",
            "city_match", "budget_fit", "price_ratio", "rating", "reviews_log",
            "years", "guests", "event_idx", "query_text"]
    matched_pairs = total_vibe_pairs = 0

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for qid, q in enumerate(queries):
            tf_sims = cosine_similarity(tfidf.transform([q["text"]]), chef_matrix).ravel()
            for i, c in enumerate(chefs):
                price = estimate_price(c["base_price"], q["guests"], q["event"])
                over = max(0.0, price - q["budget"]) / q["budget"]
                label = simulated_relevance(q, c, price, rng)
                if q["vibe"]:                       # hidden truth, never a feature
                    hit = any(k in c["text"].lower() for k in VIBES[q["vibe"]])
                    label = int(np.clip(label + (1 if hit else -1), 0, 3))
                    total_vibe_pairs += 1
                    matched_pairs += int(hit)
                w.writerow([
                    qid, c["id"], label,
                    round(float(tf_sims[i]), 4),
                    round(float(embed_sims[qid, i]), 4),
                    int(q["cuisine"] in c["cuisines"]),
                    int(q["city"] == c["city"]),
                    round(max(0.0, 1.0 - over), 4),
                    round(price / q["budget"], 4),
                    c["rating"],
                    round(math.log1p(c["reviews"]), 4),
                    c["years"], q["guests"], events.index(q["event"]),
                    q["text"],
                ])
    rate = matched_pairs / max(1, total_vibe_pairs)
    print(f"Wrote {N_QUERIES} queries x {len(chefs)} chefs -> {OUT}")
    print(f"Vibe keyword hit rate across chef bios: {rate:.0%}")


if __name__ == "__main__":
    main()
