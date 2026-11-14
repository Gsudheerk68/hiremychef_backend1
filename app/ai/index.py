"""TF-IDF retrieval index built with scikit-learn. No external service or API key needed.

Persistence uses joblib (pickle). Only load index files that this application wrote itself."""
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from app.ai.documents import ChefDoc

FORMAT_VERSION = 1


@dataclass(frozen=True)
class Hit:
    chef_id: int
    score: float  # cosine similarity, 0..1


def fingerprint(docs: list[ChefDoc]) -> str:
    """Changes whenever any chef document changes, so we know when the index is out of date."""
    h = hashlib.sha1()
    for d in sorted(docs, key=lambda x: x.chef_id):
        h.update(f"{d.chef_id}:{d.text}|{sorted(d.metadata.items())}".encode())
    return h.hexdigest()


class ChefIndex:
    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self.chef_ids: list[int] = []
        self.metadata: dict[int, dict] = {}
        self.fingerprint: str = ""
        self.built_at: str = ""

    @property
    def size(self) -> int:
        return len(self.chef_ids)

    def fit(self, docs: list[ChefDoc]) -> "ChefIndex":
        self.chef_ids = [d.chef_id for d in docs]
        self.metadata = {d.chef_id: d.metadata for d in docs}
        self.fingerprint = fingerprint(docs)
        self.built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not docs:
            self.vectorizer, self.matrix = None, None
            return self
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", lowercase=True)
        self.matrix = self.vectorizer.fit_transform([d.text for d in docs])
        return self

    def search(self, query: str, top_k: int = 10, candidate_ids: set[int] | None = None) -> list[Hit]:
        """Most similar chefs first. Chefs with zero similarity are never returned.
        `candidate_ids` limits the search to chefs that passed earlier filters."""
        if not query or not query.strip() or self.vectorizer is None or not self.chef_ids:
            return []
        q = self.vectorizer.transform([query])
        if q.nnz == 0:  # none of the query words exist in the index vocabulary
            return []
        sims = linear_kernel(q, self.matrix).ravel()  # rows are L2-normalised, so this is cosine similarity
        order = np.lexsort((np.array(self.chef_ids), -sims))  # score desc, then chef_id asc for stable ties
        hits = []
        for i in order:
            cid = self.chef_ids[i]
            if sims[i] <= 0 or (candidate_ids is not None and cid not in candidate_ids):
                continue
            hits.append(Hit(cid, round(float(sims[i]), 6)))
            if len(hits) >= top_k:
                break
        return hits

    # ---- persistence
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        joblib.dump({"v": FORMAT_VERSION, "vectorizer": self.vectorizer, "matrix": self.matrix, "chef_ids": self.chef_ids,
                     "metadata": self.metadata, "fingerprint": self.fingerprint, "built_at": self.built_at}, tmp)
        os.replace(tmp, path)  # atomic: a crash never leaves a half-written index

    @classmethod
    def load(cls, path: str) -> "ChefIndex | None":
        """Returns None if the file is missing, unreadable or from another format version."""
        if not os.path.exists(path):
            return None
        try:
            data = joblib.load(path)
            if data.get("v") != FORMAT_VERSION:
                return None
        except Exception:
            return None
        idx = cls()
        idx.vectorizer, idx.matrix, idx.chef_ids = data["vectorizer"], data["matrix"], data["chef_ids"]
        idx.metadata, idx.fingerprint, idx.built_at = data["metadata"], data["fingerprint"], data["built_at"]
        return idx
