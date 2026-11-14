"""See the full Phase 2 pipeline from the terminal.
Usage: python -m scripts.recommend_demo "South Indian chef for a family dinner for 10 people in Nellore this Sunday, budget ₹5000" """
import sys
from app.ai.ranking import recommend
from app.db.session import SessionLocal

query = " ".join(sys.argv[1:]) or "south indian chef for 10 people in Nellore under 5000"
with SessionLocal() as db:
    r = recommend(db, query)
print("Understood:", r.parsed.to_dict())
for w in r.parsed.warnings + r.notes:
    print("Note:", w)
if not r.results:
    print("No matching chefs")
for i, x in enumerate(r.results, 1):
    m = x.metadata
    print(f"\n{i}. {m['name']} ({m['city']})  {x.match_percent}% match  est. ₹{x.estimated_price:,}")
    for reason in x.reasons:
        print("   -", reason)
