"""python -m scripts.ml_recommend_demo "your query"
Compare:  ML_RANKER_ENABLED=0 python -m scripts.ml_recommend_demo "..."
"""
import sys

from app.ai.ranking import recommend
from app.db.session import SessionLocal

query = " ".join(sys.argv[1:]) or "south indian chef for family dinner for 10 people in nellore, budget 5000"
with SessionLocal() as db:
    res = recommend(db, query, limit=5)

print("Parsed :", res.parsed.to_dict())
print("Relaxed:", res.relaxed, "|", res.notes)
for i, r in enumerate(res.results, 1):
    print(f"\n#{i} chef_id={r.chef_id}  match={r.match_percent}%  ₹{r.estimated_price:,}")
    for reason in r.reasons:
        print("   -", reason)
