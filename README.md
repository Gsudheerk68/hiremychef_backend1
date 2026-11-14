# Hire My Chef – Backend (Phases 1–4 + RAG Recommendation Phases 1–2)

## What was built
The backend skeleton for the Hire My Chef platform: project structure, environment config,
PostgreSQL connection, the full database schema (users, chef profiles, bookings, reviews,
messages), Alembic migrations, a health-check endpoint, and Docker Compose for local setup.
No business endpoints yet; auth starts in Phase 2.

## Tech used
- **FastAPI**: REST API framework (auto docs at `/docs`)
- **PostgreSQL 16**: primary database
- **SQLAlchemy 2.0**: ORM using typed `Mapped` models
- **Alembic**: database migrations
- **pydantic-settings**: config from `.env`
- **Docker / Docker Compose**: PostgreSQL + API containers

## Technical workflow
1. `app/core/config.py` loads settings from environment variables (`.env`).
2. `app/db/session.py` creates one SQLAlchemy engine and a `get_db` dependency that gives
   each request its own session and closes it afterwards.
3. `app/models/*` define the tables. Relationships: User 1–1 ChefProfile, ChefProfile 1–N
   Booking, Booking 1–1 Review, Message links two Users (optionally to a Booking).
   Booking status enum: Pending, Accepted, Rejected, Completed, Cancelled.
   `ChefProfile.is_verified` is the admin-approval flag.
4. `alembic/env.py` imports all models, so `alembic revision --autogenerate` produces the
   migration from the models, and `alembic upgrade head` applies it to PostgreSQL.
5. `app/main.py` creates the FastAPI app, enables CORS for the React frontend
   (`http://localhost:5173`) and mounts routers under `/api/v1`. This matches the frontend's
   `VITE_API_BASE_URL`.
6. Request flow: client → FastAPI router → `get_db` session → SQLAlchemy models → PostgreSQL.

## Run
    cp .env.example .env
    docker compose up -d db
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head
    uvicorn app.main:app --reload
Open http://localhost:8000/docs and call `GET /api/v1/health`.
(Or run everything in Docker: `docker compose up --build`; this applies migrations on start,
so run the autogenerate step above once first.)

## Test
    pip install pytest && pytest

## Phase 2 – what was added
**Built:** registration (customer or chef), login, current-user endpoint, forgot/reset password,
role-based access control, an admin-only sample endpoint, an admin seed script and 6 tests.

**Tech:** PyJWT (tokens), bcrypt (password hashing), Pydantic v2 + email-validator (validation),
FastAPI dependencies (auth and roles), pytest + FastAPI TestClient.

**Endpoints (prefix `/api/v1`)**
- `POST /auth/register`: body `full_name, email, password, role(customer|chef)`; chefs may add `city, cuisines, years_experience`
- `POST /auth/login`: returns `{ token, token_type, user }` (the shape the React `authService` expects)
- `GET /auth/me`: current user (Bearer token)
- `POST /auth/forgot-password`, `POST /auth/reset-password`
- `GET /admin/users`: admin only (403 for other roles, 401 without a token)

**Technical workflow**
1. Register: Pydantic validates input, the email is lowercased, duplicates give 409, and the password is
   bcrypt-hashed. `role=admin` is rejected (422). A chef also gets an unverified `ChefProfile`,
   which an admin must approve in Phase 5 before the chef is listed.
2. Login: the password is checked against the hash, and a JWT is issued with `sub` (user id), `purpose`, `iat`
   and `exp`. Wrong email and wrong password return the same 401 message.
3. Protected routes: `get_current_user` reads the `Authorization: Bearer` header, verifies the JWT, loads the user
   from the database and rejects missing, invalid or disabled users. Roles are always read from the
   database, never from the client.
4. RBAC: `require_roles(UserRole.admin)` wraps a router or endpoint and returns 403 for other roles.
5. Password reset: a separate short-lived JWT with `purpose=reset`. Access tokens cannot be used for reset and vice
   versa. In development the reset token is logged to the console because email sending is not built yet.
6. Frontend: set `VITE_USE_MOCK=false` in the React app. Its Axios interceptor already sends the Bearer token.

## Run Phase 2 additions
    pip install -r requirements.txt && pytest
    python -m scripts.create_admin admin@example.com "Admin" StrongPass123   # first admin

## Phase 3 – what was added
**Built:** public chef search with filters, sorting and pagination; chef detail; chef self-service profile
update; availability calendar (blocked dates + accepted bookings); admin chef approval; demo seed script;
6 new tests (13 in total).

**Tech:** FastAPI query parameters with validation, SQLAlchemy 2.0 (`contains_eager`, `exists()` subqueries),
a new `chef_unavailable_dates` table (Alembic migration), pytest.

**Endpoints (prefix `/api/v1`)**
- `GET /chefs`: params `q, city, cuisine, min_price, max_price, min_rating, min_experience, available_on,
  available_now, sort(rating|price_asc|price_desc|experience|newest), page, page_size`. Returns `{items, total, page, page_size, pages}`
- `GET /chefs/recommended`: top-rated chefs (the ML recommender replaces this in Phase 6)
- `GET /chefs/{id}`, `GET /chefs/{id}/availability?start&end`
- `GET/PUT /chefs/me`: chef role only
- `POST /chefs/me/availability/block` and `/unblock`: body `{"dates": ["2026-12-25"]}`
- `GET /admin/chefs?verified=false`, `POST /admin/chefs/{id}/verify` and `/unverify`: admin only

**Technical workflow**
1. A chef registers (Phase 2) with `is_verified=false`. Public endpoints only return verified chefs with an
   active account, and an unverified profile returns 404 unless the viewer is its owner or an admin
   (`get_optional_user` reads the token if one is sent).
2. An admin approves the chef via `POST /admin/chefs/{id}/verify`. Chefs cannot verify themselves, because
   `is_verified` is not a field of `ChefUpdate`.
3. `GET /chefs` builds the WHERE conditions dynamically, runs a COUNT query for the total, then fetches one page
   with ORDER BY, LIMIT and OFFSET. Cuisine and text search use a case-insensitive match on the JSON column cast to text.
4. Availability: a chef is available by default. A day is unavailable if the chef blocked it or has an
   *Accepted* booking on that date. `available_on=<date>` excludes those chefs using NOT EXISTS subqueries.
   Phase 4 will make accepting a booking trigger this automatically.
5. Response field names (`name, years, rating, reviews, price, available, photo`) match the React app's chef objects.

## Run Phase 3 additions
    alembic revision --autogenerate -m "add chef availability"
    alembic upgrade head
    python -m scripts.seed_demo        # 6 verified demo chefs (password ChefPass123)
    pytest
Then open `/docs` and try `GET /api/v1/chefs?cuisine=south&sort=price_asc`.

## Phase 4 – what was added
**Built:** booking creation with a server-side price, the booking status workflow, admin booking list,
reviews that update chef ratings, and automatic availability blocking when a booking is accepted.
7 new tests (20 in total). The API follows the frontend's `API_CONTRACT.md`.

**Tech:** FastAPI path/Literal validation, SQLAlchemy 2.0 (`selectinload`, `with_for_update` row lock),
Alembic (new `event_day` column), fixed India timezone helper, pytest.

**Endpoints (prefix `/api/v1`)**
- `POST /bookings/estimate`: `{chef_id, guests, service_type}` returns `{estimated_price}`
- `POST /bookings`: customers only. `GET /bookings`: filtered by the token (customer: own, chef: for their profile, admin: all)
- `POST /bookings/{id}/accept|reject|cancel|complete`: returns the updated booking
- `GET /admin/bookings`: admin only
- `POST /reviews` `{booking_id, rating 1-5, comment}`: customers only. `GET /chefs/{id}/reviews`: public
- `ChefOut` now also returns `user_id`

**Technical workflow**
1. Create: the customer sends `chef_id, service_type, event_date, guests, location...`. The server checks that the chef is
   verified, that the date is in the future and that the day is free (not blocked and no *Accepted* booking). It then computes
   the price itself and ignores any `estimated_price` sent by the client. Conflicts return 409.
2. Price rule (same as the frontend): base price covers 6 guests, plus 6% of base per extra guest, times an event factor
   (Family dinner 1.0, Weekly meals 0.9, Birthday 1.15, Festival 1.1, Corporate 1.3, Wedding 1.5), rounded to Rs 50.
3. Time handling: `event_date` is sent as local India time without an offset (`2026-12-25T19:00:00`). It is stored as a UTC
   instant, and the India calendar day is stored in `event_day`, so availability never shifts a day. Responses return the same
   offset-free local format.
4. Status workflow: Pending to Accepted or Rejected (chef); Accepted to Completed (chef); Pending or Accepted to Cancelled
   (customer or chef). Admins can do any action. Other people get 404, wrong role gets 403, wrong state gets 409.
5. Accept: the chef row is locked (`FOR UPDATE`) so two requests cannot take the same day. The accept fails with 409 if the
   day is blocked or already has an accepted booking. An accepted booking appears in `/chefs/{id}/availability` and is excluded by
   `available_on`; cancelling frees the day.
6. Reviews: only the booking's customer, only when it is Completed, once per booking. The chef's rating is updated as a running average
   and `review_count` increases.

## Run Phase 4 additions
    alembic revision --autogenerate -m "bookings event_day"
    alembic upgrade head
    pytest
The new `event_day` column is NOT NULL, so the migration works on an empty bookings table (true if you have not
created bookings before).

**Frontend:** in `src/api/client.js` change
`new Set(['auth','chefs','admin.chefs','admin.users'])` to
`new Set(['auth','chefs','admin.chefs','admin.users','bookings','reviews'])`, keep `VITE_USE_MOCK=hybrid`, and restart `npm run dev`.

## RAG chef recommendation – Phase 1 (retrieval index)
**Built:** the searchable knowledge base for the AI chef finder: one text document per chef, a TF-IDF search index,
saving/loading of the index, automatic refresh when chef data changes, demo data and 9 tests (29 in total).
There is no public endpoint yet; the recommender endpoint arrives in Phase 3. Progress notes: `docs/AI_RAG_PROGRESS.md`.

**Tech:** scikit-learn (`TfidfVectorizer`, cosine similarity), joblib (persistence), numpy, SQLAlchemy.
LangChain is added in Phase 3 and does not need an API key to run.

**Technical workflow**
1. `app/ai/documents.py` loads verified, active chefs and their latest review comments and writes one document per chef:
   name, city, cuisines (twice, for weight), certifications, bio, and what customers say. It also keeps metadata
   (city, cuisines, price, rating, years) for the filters and ranking added in Phase 2.
2. `app/ai/index.py` fits a `TfidfVectorizer` (1-2 word phrases, sublinear tf, English stop words) on all documents.
   `search(query)` turns the query into a vector, computes cosine similarity with every chef and returns the best
   matches. Chefs with zero similarity are never returned, and `candidate_ids` limits the search to chefs that passed filters.
3. Saving: the index is written to `AI_INDEX_PATH` with joblib (atomic write). Loading returns nothing if the file is
   missing, damaged or from another format version, and the index is simply rebuilt.
4. `app/ai/service.py` keeps one shared index in memory. It loads from disk or builds on first use, and checks the
   database at most once a minute: if any chef document changed (hash comparison), it rebuilds automatically.
5. Only load index files that this app wrote, because joblib files are pickles.

## Try it
    pip install -r requirements.txt
    python -m scripts.seed_demo         # 6 chefs (skip if done)
    python -m scripts.seed_ai_demo      # 14 more chefs with bios and reviews
    python -m scripts.build_index
    python -m scripts.search_demo "spicy andhra gongura mutton"
    pytest                              # 29 passed
No migration is needed in this phase.

## RAG chef recommendation – Phase 2 (understanding + ranking)
**Built:** the query parser, hard filters with automatic relaxation, hybrid ranking, plain-language reasons per chef, a
terminal demo and 44 new tests (73 in total). There is still no public endpoint; Phase 3 wraps this in LangChain and `POST /ai/recommend`.

**Tech:** Python `re` rule-based parsing (no LLM), scikit-learn TF-IDF similarity from Phase 1, SQLAlchemy for availability, pytest.

**Technical workflow** (`app/ai/ranking.py: recommend()`)
1. Parse (`app/ai/parser.py`): the query is turned into city, cuisines, budget, guests, event type and date. Cities and cuisines are
   matched against what exists in the index (with aliases such as Vizag, Bangalore, "veg", "fish", "pasta"). Budgets understand
   `₹5,000`, `under 4000`, `5k`, `2 lakh`, `rs 500 per head`; guests understand "for 10 people", "party of 8"; dates understand
   today, tomorrow, weekdays, "next Saturday", "25 December", `2026-12-25`, `05/12/2026`. Past dates are ignored with a warning.
2. Hard filters: only chefs in the requested city, whose *estimated price* (same price rule as bookings) is within the budget, and who are free
   on the date (not blocked, no accepted booking). Unverified chefs are never in the index.
3. Relaxation: if fewer than 3 chefs pass, the filters are relaxed in this order: availability, budget, city. Only a relaxation that adds
   chefs is applied, and each one is reported in `notes` and in the chef's reasons (e.g. "Based in Chennai (you asked for Guntur)").
4. Ranking: `score = 0.55 x similarity + 0.20 x rating/5 + 0.10 x min(years,20)/20 + 0.15 x budget fit`. Similarity mixes the cuisine
   match (60%) with TF-IDF text similarity (40%). If nothing in the request relates to any chef, nothing is returned.
5. Reasons come only from stored data: cuisine, city, availability, price estimate, rating and experience. No text is invented.

## Try it
    python -m scripts.recommend_demo "South Indian chef for a family dinner for 10 people in Nellore this Sunday, budget ₹5000"
    pytest      # 73 passed
No migration and no new packages are needed in this phase.

## Next
RAG Phase 3: LangChain retriever and chain (pluggable LLM with template fallback), `POST /api/v1/ai/recommend`, admin reindex endpoint.
