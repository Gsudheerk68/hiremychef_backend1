"""Try the retrieval from the terminal.  Usage: python -m scripts.search_demo "south indian family dinner" """
import sys
from app.ai.service import get_index
from app.db.session import SessionLocal

query = " ".join(sys.argv[1:]) or "south indian chef"
with SessionLocal() as db:
    idx = get_index(db, force_check=True)
    hits = idx.search(query, top_k=5)
if not hits:
    print("No matching chefs")
for h in hits:
    m = idx.metadata[h.chef_id]
    print(f"{h.score:.3f}  #{h.chef_id} {m['name']} ({m['city']}) {', '.join(m['cuisines'])}  Rs {m['price']:.0f}")
