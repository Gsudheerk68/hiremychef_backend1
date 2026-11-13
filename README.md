# Hire My Chef – Backend (Phase 3: Chefs, Search & Availability; includes Phases 1–2)

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

## Next phase
Phase 4: bookings (create, accept/reject/cancel/complete, price estimate) and reviews with rating updates.
