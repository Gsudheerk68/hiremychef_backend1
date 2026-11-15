"""Train the ranker, compare with baselines, save the model and a JSON report for the UI.
Run: python -m scripts.ml_train_ranker [data.csv] [model.joblib]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRanker
from sklearn.metrics import ndcg_score
from sklearn.model_selection import GroupShuffleSplit

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/ml/train.csv")
MODEL_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/ml/ranker.joblib")
REPORT_PATH = MODEL_PATH.with_suffix(".report.json")

BASE_FEATURES = ["tfidf_sim", "cuisine_match", "city_match", "budget_fit",
                 "price_ratio", "rating", "reviews_log", "years", "guests", "event_idx"]
_cols = pd.read_csv(DATA, nrows=0).columns
FEATURES = BASE_FEATURES + (["embed_sim"] if "embed_sim" in _cols else [])

FEATURE_LABELS = {
    "tfidf_sim": "Keyword similarity (TF-IDF)", "embed_sim": "Meaning similarity (embeddings)",
    "cuisine_match": "Cuisine match", "city_match": "City match", "budget_fit": "Budget fit",
    "price_ratio": "Price vs budget", "rating": "Chef rating", "reviews_log": "Number of reviews",
    "years": "Years of experience", "guests": "Guest count", "event_idx": "Event type",
}


def current_formula_score(df: pd.DataFrame) -> np.ndarray:
    """The original hand-tuned ranking from RAG Phase 2, used as the baseline."""
    sim = 0.6 * df["cuisine_match"] + 0.4 * df["tfidf_sim"]
    return (0.55 * sim + 0.20 * df["rating"] / 5
            + 0.10 * np.minimum(df["years"], 20) / 20 + 0.15 * df["budget_fit"]).to_numpy()


def mean_ndcg(df: pd.DataFrame, scores: np.ndarray, k: int) -> float:
    df = df.assign(_s=scores)
    results = []
    for _, g in df.groupby("qid"):
        if len(g) < 2 or g["label"].sum() == 0:
            continue
        results.append(ndcg_score([g["label"].to_numpy()], [g["_s"].to_numpy()], k=k))
    return float(np.mean(results))


def main() -> None:
    df = pd.read_csv(DATA).sort_values("qid").reset_index(drop=True)

    # split by QUERY so the same query never appears in both train and test
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(splitter.split(df, groups=df["qid"]))
    train, test = df.iloc[train_idx], df.iloc[test_idx]

    model = LGBMRanker(objective="lambdarank", n_estimators=300, learning_rate=0.05,
                       num_leaves=15, min_child_samples=20, subsample=0.8,
                       colsample_bytree=0.8, random_state=42, verbose=-1)
    model.fit(train[FEATURES], train["label"], group=train.groupby("qid", sort=True).size().to_numpy())

    rng = np.random.default_rng(0)
    metrics = {}
    for k in (3, 5):
        metrics[f"ndcg@{k}"] = {
            "random": round(mean_ndcg(test, rng.random(len(test)), k), 4),
            "current_formula": round(mean_ndcg(test, current_formula_score(test), k), 4),
            "lightgbm": round(mean_ndcg(test, model.predict(test[FEATURES]), k), 4),
        }

    gain = model.booster_.feature_importance(importance_type="gain").astype(float)
    share = gain / gain.sum() * 100 if gain.sum() else gain
    features = sorted(
        ({"name": n, "label": FEATURE_LABELS.get(n, n), "importance_percent": round(float(s), 1)}
         for n, s in zip(FEATURES, share)),
        key=lambda f: -f["importance_percent"])

    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": "LightGBM LGBMRanker (LambdaRank)",
        "dataset": DATA.name,
        "label_source": "simulated",
        "data": {"rows": int(len(df)), "queries": int(df["qid"].nunique()),
                 "train_queries": int(train["qid"].nunique()), "test_queries": int(test["qid"].nunique())},
        "metrics": metrics,
        "features": features,
        "note": ("Labels come from a simulated user-preference model, so these scores show the "
                 "pipeline works. They are not real-world accuracy. Real clicks and bookings are "
                 "needed to measure that."),
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "version": 1}, MODEL_PATH)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Test queries: {report['data']['test_queries']}")
    for k, m in metrics.items():
        print(f"  {k}: random {m['random']:.3f} | current formula {m['current_formula']:.3f} | LightGBM {m['lightgbm']:.3f}")
    print("Top features:", ", ".join(f"{f['label']} ({f['importance_percent']}%)" for f in features[:4]))
    print(f"Saved model  -> {MODEL_PATH}\nSaved report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
