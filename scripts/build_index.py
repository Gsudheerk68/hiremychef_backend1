"""Build (or rebuild) the chef search index and print a summary.  Usage: python -m scripts.build_index"""
from app.ai.service import rebuild_index
from app.core.config import get_settings
from app.db.session import SessionLocal

with SessionLocal() as db:
    idx = rebuild_index(db)
print(f"Indexed {idx.size} chefs, vocabulary {len(idx.vectorizer.vocabulary_) if idx.vectorizer else 0} terms")
print("Saved to", get_settings().ai_index_path)
