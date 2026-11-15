"""Filters + hybrid ranking. Pipeline: parse query -> hard filters (relaxed if too few chefs) -> TF-IDF similarity
-> weighted score -> top results with plain-language reasons that come only from real chef data."""
import math
from dataclasses import dataclass, field
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.ai import ml_ranker
from app.ai.parser import ParsedQuery, parse_query
from app.ai.service import get_index
from app.core.timeutils import now_local
from app.models import Booking, BookingStatus, ChefUnavailableDate
from app.services.pricing import INCLUDED_GUESTS, estimate_price

MIN_RESULTS = 3
RELAX_ORDER = ("availability", "budget", "city")  # first relaxed first; the city is the last thing we give up
WEIGHTS = {"similarity": 0.55, "rating": 0.20, "experience": 0.10, "budget_fit": 0.15}
OUT_OF_CITY_FACTOR = 0.85  # score multiplier for chefs outside the requested city (city comes first)


@dataclass
class Recommendation:
    chef_id: int
    score: float
    match_percent: int
    estimated_price: int
    reasons: list[str]
    metadata: dict
    factors: list[dict] = field(default_factory=list)  # "why this rank" from the ML model


@dataclass
class RecommendationResult:
    parsed: ParsedQuery
    relaxed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    results: list[Recommendation] = field(default_factory=list)
    scorer: str = "rules"  # "ml" when the LightGBM ranker produced the scores


def unavailable_chef_ids(db: Session, day: date) -> set[int]:
    blocked = db.scalars(select(ChefUnavailableDate.chef_id).where(ChefUnavailableDate.date == day))
    booked = db.scalars(select(Booking.chef_id).where(Booking.event_day == day, Booking.status == BookingStatus.accepted))
    return set(blocked) | set(booked)


def _estimate(meta: dict, p: ParsedQuery) -> int:
    return estimate_price(meta["price"], p.guests or INCLUDED_GUESTS, p.event_type or "Family dinner")


def _passes(cid: int, meta: dict, p: ParsedQuery, unavailable: set[int], relaxed: list[str]) -> bool:
    if p.city and "city" not in relaxed and (meta.get("city") or "").lower() != p.city.lower():
        return False
    if p.budget and "budget" not in relaxed and _estimate(meta, p) > p.budget:
        return False
    if p.date and "availability" not in relaxed and cid in unavailable:
        return False
    return True


def _select(idx, p, unavailable, relaxed) -> set[int]:
    return {cid for cid, meta in idx.metadata.items() if _passes(cid, meta, p, unavailable, relaxed)}


def _note(step: str, p: ParsedQuery) -> str:
    return {"availability": f"Few chefs are confirmed free on {p.date:%a %d %b}, so some results may not be available that day." if p.date else "",
            "budget": f"Few chefs fit a budget of ₹{p.budget:,.0f}, so some results cost more." if p.budget else "",
            "city": f"Few chefs were found in {p.city}, so I also included chefs from other cities."}[step]


def _reasons(meta, p, est, matched_cuisines, relaxed, unavailable_here) -> list[str]:
    """Requirements the user stated come first, then general strengths. At most 6 short lines."""
    out = []
    if matched_cuisines:
        out.append("Specialises in " + " and ".join(matched_cuisines) + " cuisine")
    if p.city:
        out.append(f"Based in {meta['city']}" if (meta.get("city") or "").lower() == p.city.lower()
                   else f"Based in {meta.get('city') or 'another city'} (you asked for {p.city})")
    if p.date and "availability" not in relaxed:
        out.append(f"Free on {p.date:%a %d %b}")
    elif p.date and unavailable_here:
        out.append(f"Not available on {p.date:%a %d %b}")
    if p.budget:
        out.append(f"Estimated ₹{est:,} for your request" + (", within your budget" if est <= p.budget else f", above your ₹{p.budget:,.0f} budget"))
    if meta["rating"] >= 4.5 and meta["reviews"]:
        out.append(f"Rated {meta['rating']:.1f} from {meta['reviews']} reviews")
    if meta["years"] >= 8:
        out.append(f"{meta['years']} years of experience")
    return out


def _to_unit(x: float) -> float:
    """LightGBM scores are unbounded; squash to 0..1 for the existing match_percent display."""
    x = max(-50.0, min(50.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def recommend(db: Session, query: str, limit: int = 5, today: date | None = None, min_results: int = MIN_RESULTS) -> RecommendationResult:
    idx = get_index(db)
    today = today or now_local().date()
    cities = {m["city"] for m in idx.metadata.values() if m.get("city")}
    cuisines = {c for m in idx.metadata.values() for c in m.get("cuisines", [])}
    p = parse_query(query, cities, cuisines, today)
    result = RecommendationResult(parsed=p)
    if idx.size == 0:
        return result
    unavailable = unavailable_chef_ids(db, p.date) if p.date else set()

    # 1. hard filters, relaxed one step at a time while there are too few chefs
    relaxed: list[str] = []
    candidates = _select(idx, p, unavailable, relaxed)
    applies = {"availability": bool(p.date), "budget": bool(p.budget), "city": bool(p.city)}
    for step in RELAX_ORDER:
        if len(candidates) >= min_results:
            break
        if not applies[step]:
            continue
        wider = _select(idx, p, unavailable, relaxed + [step])
        if len(wider) > len(candidates):  # only report a relaxation that actually added chefs
            relaxed.append(step)
            candidates = wider
    result.relaxed = relaxed
    result.notes = [_note(s, p) for s in relaxed]
    if not candidates:
        return result

    # 2. similarity among the remaining chefs
    sims = {h.chef_id: h.score for h in idx.search(query, top_k=idx.size, candidate_ids=candidates)}
    if not sims and not p.cuisines and not p.city:
        return result  # nothing in the request relates to any chef (e.g. unrelated text)
    top_sim = max(sims.values(), default=0.0)

    # 3. score: ML ranker when available, otherwise the hand-weighted formula
    ml_out = ml_ranker.score_candidates(
        db, query, p, candidates, lambda cid: _estimate(idx.metadata[cid], p))
    ml_scores, ml_factors = ml_out if ml_out is not None else (None, {})
    if ml_scores is not None and any(cid not in ml_scores for cid in candidates):
        ml_scores, ml_factors = None, {}  # chef list changed between index and model; use the safe path
    result.scorer = "ml" if ml_scores is not None else "rules"

    def in_city(cid: int) -> bool:
        """True when the chef is in the city the customer asked for."""
        return bool(p.city) and (idx.metadata[cid].get("city") or "").lower() == p.city.lower()

    wanted = [c.lower() for c in p.cuisines]
    ranked = []
    for cid in candidates:
        meta = idx.metadata[cid]
        have = {c.lower() for c in meta.get("cuisines", [])}
        matched = [c for c in p.cuisines if c.lower() in have]
        est = _estimate(meta, p)
        if ml_scores is not None:
            score = _to_unit(ml_scores[cid])
        else:
            sim_n = sims.get(cid, 0.0) / top_sim if top_sim else 0.0
            similarity = 0.6 * (len(matched) / len(wanted)) + 0.4 * sim_n if wanted else sim_n
            fit = 0.5 if not p.budget else max(0.0, min(1.0, 1 - 0.5 * est / p.budget))
            score = (WEIGHTS["similarity"] * similarity + WEIGHTS["rating"] * meta["rating"] / 5
                     + WEIGHTS["experience"] * min(meta["years"], 20) / 20 + WEIGHTS["budget_fit"] * fit)
        if p.city and not in_city(cid):
            score *= OUT_OF_CITY_FACTOR  # city comes first: out-of-city chefs show a lower match %
        ranked.append((score, meta["rating"], cid, est, matched))
    # local chefs first, then by score, then rating, then id (stable)
    ranked.sort(key=lambda r: (not in_city(r[2]), -r[0], -r[1], r[2]))

    for score, _, cid, est, matched in ranked[:limit]:
        meta = idx.metadata[cid]
        result.results.append(Recommendation(
            chef_id=cid, score=round(score, 4), match_percent=max(0, min(100, round(score * 100))), estimated_price=est,
            reasons=_reasons(meta, p, est, matched, relaxed, cid in unavailable), metadata=meta,
            factors=ml_factors.get(cid, [])))
    return result
