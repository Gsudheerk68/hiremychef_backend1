"""Keeps one shared index in memory, loads it from disk, and rebuilds it when chef data changes."""
import threading
import time
from sqlalchemy.orm import Session
from app.ai.documents import build_documents
from app.ai.index import ChefIndex, Hit, fingerprint
from app.core.config import get_settings

_lock = threading.Lock()
_index: ChefIndex | None = None
_checked_at = 0.0
FRESHNESS_SECONDS = 60  # how often we compare the index with the database


def reset_index() -> None:
    """Forget the in-memory index (used by tests)."""
    global _index, _checked_at
    with _lock:
        _index, _checked_at = None, 0.0


def rebuild_index(db: Session) -> ChefIndex:
    global _index, _checked_at
    s = get_settings()
    idx = ChefIndex().fit(build_documents(db, s.ai_review_snippets))
    idx.save(s.ai_index_path)
    with _lock:
        _index, _checked_at = idx, time.monotonic()
    return idx


def get_index(db: Session, force_check: bool = False) -> ChefIndex:
    """Load from memory, then disk, then build. Re-checks the database at most once per minute."""
    global _index, _checked_at
    s = get_settings()
    if _index is None:
        loaded = ChefIndex.load(s.ai_index_path)
        with _lock:
            _index = loaded
    if _index is None:
        return rebuild_index(db)
    if force_check or time.monotonic() - _checked_at > FRESHNESS_SECONDS:
        current = fingerprint(build_documents(db, s.ai_review_snippets))
        if current != _index.fingerprint:
            return rebuild_index(db)
        _checked_at = time.monotonic()
    return _index


def search_chefs(db: Session, query: str, top_k: int = 10, candidate_ids: set[int] | None = None) -> list[Hit]:
    return get_index(db).search(query, top_k=top_k, candidate_ids=candidate_ids)
