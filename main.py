import os
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import desc
from sqlalchemy.pool import StaticPool


# ----------------------------
# Models / Schemas
# ----------------------------

class ApplicationStatus(str, Enum):
    WISHLIST = "Wishlist"
    APPLIED = "Applied"
    PHONE_SCREEN = "Phone Screen"
    TECHNICAL = "Technical"
    ONSITE = "Onsite"
    OFFER = "Offer"
    REJECTED = "Rejected"
    GHOSTED = "Ghosted"

    @classmethod
    def _missing_(cls, value: object):
        # Case-insensitive enum parsing, e.g. "applied", "APPLIED", "Applied"
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class Job(SQLModel, table=True):
    """DB table model."""
    id: Optional[int] = Field(default=None, primary_key=True)

    company: str = Field(index=True)
    role: str = Field(index=True)
    status: ApplicationStatus = Field(default=ApplicationStatus.APPLIED, index=True)

    notes: Optional[str] = None

    applied_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )


class JobCreate(SQLModel):
    company: str
    role: str
    status: ApplicationStatus = ApplicationStatus.APPLIED
    notes: Optional[str] = None
    applied_date: Optional[datetime] = None


class JobUpdate(SQLModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = None
    applied_date: Optional[datetime] = None


class JobRead(SQLModel):
    id: int
    company: str
    role: str
    status: ApplicationStatus
    notes: Optional[str]
    applied_date: datetime
    last_updated: datetime


# ----------------------------
# DB + App setup
# ----------------------------


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///jobs.db")

engine_kwargs = {"echo": False}

if DATABASE_URL == "sqlite:///:memory:":
    # IMPORTANT: share the same connection for in-memory DB
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool
elif DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)



@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Job Tracker API", version="1.0.0", lifespan=lifespan)


# ----------------------------
# Routes
# ----------------------------

@app.get("/", tags=["Meta"])
def root():
    return {"message": "Job Tracker API running"}


@app.get("/hello/{name}", tags=["Meta"])
def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobRead, tags=["Jobs"])
def create_job(payload: JobCreate):
    new_job = Job(
        company=payload.company,
        role=payload.role,
        status=payload.status,
        notes=payload.notes,
        applied_date=payload.applied_date or datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )

    with Session(engine) as session:
        session.add(new_job)
        session.commit()
        session.refresh(new_job)
        return new_job


@app.get("/jobs", response_model=List[JobRead], tags=["Jobs"])
def list_jobs(
    status: Optional[ApplicationStatus] = Query(default=None),
    company: Optional[str] = Query(default=None, description="Partial match, case-insensitive"),
    role: Optional[str] = Query(default=None, description="Partial match, case-insensitive"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    with Session(engine) as session:
        stmt = select(Job)

        if status is not None:
            stmt = stmt.where(Job.status == status)

        if company:
            stmt = stmt.where(Job.company.ilike(f"%{company}%"))

        if role:
            stmt = stmt.where(Job.role.ilike(f"%{role}%"))

        stmt = stmt.order_by(desc(Job.last_updated)).offset(offset).limit(limit)
        return session.exec(stmt).all()


@app.get("/jobs/{job_id}", response_model=JobRead, tags=["Jobs"])
def get_job(job_id: int):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


@app.patch("/jobs/{job_id}", response_model=JobRead, tags=["Jobs"])
def update_job(job_id: int, payload: JobUpdate):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        for key, value in update_data.items():
            setattr(job, key, value)

        job.last_updated = datetime.now(timezone.utc)

        session.add(job)
        session.commit()
        session.refresh(job)
        return job


@app.delete("/jobs/{job_id}", tags=["Jobs"])
def delete_job(job_id: int):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        session.delete(job)
        session.commit()
        return {"message": "Job deleted", "job_id": job_id}
