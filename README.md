# Job Tracker

Your job hunt deserves better than a messy notes app, twelve open tabs, and vague optimism.

This project is a FastAPI-powered job tracker with:

- personal accounts
- isolated job pipelines per user
- a built-in frontend
- filtering, status updates, and notes
- deployment-ready configuration

It is part API, part dashboard, part career-control panel.

## What it does

You can:

- create an account
- log in from different devices
- add applications
- move jobs across statuses like `Applied`, `Technical`, `Offer`, or `Rejected`
- keep notes without losing context
- filter your pipeline when things get noisy

## Run it locally

Fire it up:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:

- frontend: `http://localhost:8000/`
- API info: `http://localhost:8000/api`
- health check: `http://localhost:8000/health`

By default, the app uses a local SQLite database at `./data/jobs.db`.

## Authentication

Each user gets their own account and their own job data.

Available auth endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

All `/jobs` endpoints require:

```text
Authorization: Bearer <token>
```

If the password is wrong, the app tells the user directly instead of pretending all mistakes are equally mysterious.

## Deployment

This repo includes a `Procfile`, so it is already shaped for straightforward deployment.

Environment variables:

- `PORT`: usually supplied by your hosting provider
- `DATABASE_URL`: optional locally, required for real multi-device production use

If you deploy it for actual users, use Postgres instead of local SQLite.

Nice detail: URLs starting with `postgres://` or `postgresql://` are normalized automatically for SQLAlchemy + `psycopg`, so the app is less likely to throw a fit during deploy.

## Make it public

If you want this app available from anywhere in the world:

1. Push the repo to GitHub.
2. Deploy it to a host like Render, Railway, or Fly.io.
3. Attach a hosted Postgres database.
4. Set `DATABASE_URL`.
5. Open the public URL from any device.

## Quick route guide

- `GET /` -> frontend
- `GET /app` -> frontend
- `GET /api` -> API message
- `GET /health` -> health check
- `GET /jobs` -> your jobs
- `POST /jobs` -> create a job
- `PATCH /jobs/{job_id}` -> update a job
- `DELETE /jobs/{job_id}` -> delete a job

## Final note

This app will not get you the job.

It will, however, stop your application pipeline from looking like a crime scene.
