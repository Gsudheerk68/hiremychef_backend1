# RAG Chef Recommendation – progress (resume from here in a new chat)

Goal: natural-language query -> recommended chefs with profiles. Stack: scikit-learn (TF-IDF retrieval) + LangChain
(retriever/chain, pluggable LLM, template fallback) + FastAPI + React.

## Checklist
- [x] Phase 1: chef documents, TF-IDF index, joblib persistence, search, freshness check, seeds, 9 tests (29 total)
- [x] Phase 2: query parser (city, cuisine, budget, guests, event type, date), hard filters, hybrid ranking, relaxation, 44 tests (73 total)
- [ ] Phase 3: LangChain retriever + chain, LLM_PROVIDER none|anthropic|openai|ollama, POST /ai/recommend, admin reindex
- [ ] Phase 4: frontend aiService + mock + "AI Chef Finder" UI with chef profile cards
- [ ] Phase 5: evaluation script (precision@3), caching, rate limit, final docs

## Decisions made
- Retrieval is TF-IDF (word 1-2 grams, sublinear tf, English stop words) + cosine similarity. No API key needed.
- One document per chef: name, city, cuisines (written twice for weight), certifications, bio, up to 5 recent review comments.
- Only verified chefs with active accounts are indexed, so nobody else can be recommended.
- Index lives in memory, is saved with joblib to `AI_INDEX_PATH` (atomic write) and is compared with the database
  (document fingerprint) at most once a minute; a change triggers a rebuild. Phase 3 adds an admin reindex endpoint.
- Zero-similarity chefs are never returned; `candidate_ids` lets Phase 2 filters run before retrieval.
- joblib files are pickles: only load files this app wrote.

- Phase 2 parser is rule-based (regex + synonym tables), works with the cities/cuisines found in the index, and uses India's date (UTC+05:30).
  "this/bare weekday" = next on-or-after today; "next <weekday>" = that day in next week (Mon-Sun); budgets accept ₹5,000 / under 4000 / 5k / 2 lakh / rs 500 per head.
- Hard filters: city, budget (using the estimated price for the guests and event type, via app/services/pricing.py), availability on the date
  (blocked date or Accepted booking). If fewer than 3 chefs pass, filters are relaxed in this order: availability, budget, city; only a
  relaxation that adds chefs is reported. Cuisine is a soft signal (ranking), not a filter.
- Score = 0.55 similarity + 0.20 rating/5 + 0.10 min(years,20)/20 + 0.15 budget fit. Similarity = 0.6 cuisine match + 0.4 TF-IDF (scaled to the best
  candidate) when a cuisine was asked for, otherwise TF-IDF alone. No relevance signal (no TF-IDF hit, cuisine or city) returns nothing.
- Reasons are built only from stored chef data (cuisines, city, rating, years, price estimate, availability), never from an LLM.
- Entry point for Phase 3: `app.ai.ranking.recommend(db, query, limit, today) -> RecommendationResult(parsed, relaxed, notes, results)`.

## Key files
`app/ai/documents.py` (text + metadata), `app/ai/index.py` (ChefIndex: fit/search/save/load),
`app/ai/service.py` (shared index, rebuild, freshness), `app/ai/parser.py` (query understanding),
`app/ai/ranking.py` (filters, relaxation, scoring, reasons), `scripts/recommend_demo.py`, `scripts/build_index.py`, `scripts/search_demo.py`,
`scripts/seed_ai_demo.py`, `tests/test_ai_index.py`, `tests/test_ai_parser.py`, `tests/test_ai_ranking.py`.
