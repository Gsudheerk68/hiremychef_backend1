"""GET /ml/ranker-report: public, read-only model metrics (no user data)."""
import json

from fastapi import APIRouter, HTTPException

from app.ai import ml_ranker

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/ranker-report")
def ranker_report():
    path = ml_ranker.MODEL_PATH.with_suffix(".report.json")
    if not path.exists():
        raise HTTPException(404, "No report yet. Run: python -m scripts.ml_train_ranker")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["serving"] = {"enabled": ml_ranker.is_enabled(), "model_file": ml_ranker.MODEL_PATH.name}
    return data
