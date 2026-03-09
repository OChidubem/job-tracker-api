# Job Tracker API

FastAPI service for tracking job applications.
Each user has their own account and isolated job pipeline.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The app defaults to a local SQLite database at `./data/jobs.db`.

Frontend: open `http://localhost:8000/`

## Deployment

The repo now includes a `Procfile` for platforms that expect a start command.

Environment variables:

- `PORT`: supplied by most hosts
- `DATABASE_URL`: optional; defaults to SQLite

Postgres URLs using either `postgres://` or `postgresql://` are normalized automatically for SQLAlchemy/psycopg.

Health check endpoint: `GET /health`
Frontend route: `GET /` or `GET /app`
API info route: `GET /api`

## Authentication

Use the built-in frontend or call the auth endpoints directly:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

All `/jobs` endpoints now require an `Authorization: Bearer <token>` header and only return the signed-in user's data.
