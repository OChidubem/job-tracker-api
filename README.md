# Job Tracker API 🚀

A FastAPI + SQLModel REST API to track job applications.

## Features
- Create, list, update, delete jobs
- Case-insensitive status enum (e.g. "applied", "Applied")
- Filter by company, role, status
- Pagination (limit/offset)
- SQLite (prod) + in-memory SQLite (CI tests)

## Tech Stack
- FastAPI
- SQLModel
- SQLAlchemy
- Pytest
- GitHub Actions CI

## Run Locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload
