# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the app
```bash
PYTHONPATH=. uvicorn app.main:app --reload
```

### Linting and formatting
```bash
ruff check .
black --check .
black .          # auto-fix formatting
```

### Tests
```bash
PYTHONPATH=. pytest                        # all tests
PYTHONPATH=. pytest app/tests/test_auth.py # single file
```

### Database migrations (Alembic)
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

## Environment

Requires a `.env` file with:
```
DATABASE_URL=postgresql+asyncpg://...
JWT_SECRET_KEY=...
JWT_REFRESH_SECRET_KEY=...
```

GCS bucket name is hardcoded in `app/core/config.py` as `GCS_BUCKET_NAME = "onlyfats-private-media"`. Google Cloud credentials must be available in the environment (ADC or `GOOGLE_APPLICATION_CREDENTIALS`).

## Architecture

**Stack:** FastAPI + SQLAlchemy (async) + PostgreSQL (via `asyncpg`) + Alembic + Celery/Redis + Google Cloud Storage.

**Layer structure:**
- `app/api/v1/` — FastAPI route handlers (thin, delegate to services)
- `app/services/` — Business logic layer
- `app/repositories/` — Database query layer (currently mostly empty stubs)
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — Pydantic request/response models
- `app/core/` — Shared infrastructure: config, DB session, security, dependencies
- `app/workers/` — Celery tasks (stubs, not yet implemented)

**Auth flow:**
- JWT access tokens (short-lived, 60 min) + refresh tokens (30 days, stored hashed in DB as `refresh_tokens` table).
- `app/core/dependencies.py::get_current_user` is the FastAPI dependency for protected routes.
- Passwords hashed with `pwdlib` (Argon2). Refresh tokens hashed with SHA-256 before DB storage.
- Supports regular users, guest users (no email/password), and creators (role-based).

**User/Creator model:**
- `User` has `role` field (`creator` or `visitor`) and `is_guest` flag.
- `Creator` is a separate profile record linked 1:1 to a `User` via `user_id`. A user must have a `Creator` record to upload creator content or manage posts.

**File uploads:**
- `POST /api/v1/uploads` — multipart upload to GCS. `purpose` form field determines path: `creator_profile`, `user_profile`, or `post_media` (requires `post_id` of a draft post owned by the caller's creator profile).
- GCS paths follow the pattern: `creators/{id}/profile/`, `users/{id}/profile/`, `posts/{id}/orig/`.
- Note: `app/api/v1/uploads.py` and `app/services/upload_service.py` are both present with overlapping logic; the router currently uses the inline approach in `uploads.py`.

**Active API routes** (registered in `app/api/v1/router.py`):
- `/auth/*` — signup, login, guest login, refresh, logout, me
- `/creators/*` — creator profile CRUD
- Creator posts routes (prefix-less)
- `/uploads` — file upload to GCS

Routes for `users`, `posts`, `subscriptions`, `payments`, and `media` exist as files in `app/api/v1/` but are **not yet registered** in the router.
