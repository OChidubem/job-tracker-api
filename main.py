from datetime import datetime, timezone
from contextlib import asynccontextmanager
from enum import Enum
import hashlib
import hmac
import os
from pathlib import Path
import secrets
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import field_validator
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import desc, inspect, text
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
    user_id: int = Field(foreign_key="users.id", index=True)

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

    @field_validator("company", "role")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JobUpdate(SQLModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = None
    applied_date: Optional[datetime] = None

    @field_validator("company", "role")
    @classmethod
    def validate_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_optional_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JobRead(SQLModel):
    id: int
    user_id: int
    company: str
    role: str
    status: ApplicationStatus
    notes: Optional[str]
    applied_date: datetime
    last_updated: datetime


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuthToken(SQLModel, table=True):
    __tablename__ = "auth_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuthPayload(SQLModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) < 3:
            raise ValueError("username must be at least 3 characters")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters")
        return value


class UserRead(SQLModel):
    id: int
    username: str
    created_at: datetime


class AuthResponse(SQLModel):
    token: str
    user: UserRead


# ----------------------------
# DB + App setup
# ----------------------------


def resolve_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")

    # Some platforms still inject `postgres://`, which SQLAlchemy 2 rejects.
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)

    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    return database_url


def ensure_sqlite_path(database_url: str) -> None:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return

    db_path = database_url.removeprefix("sqlite:///")
    if not db_path or db_path == ":memory:":
        return

    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


DATABASE_URL = resolve_database_url()
ensure_sqlite_path(DATABASE_URL)
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
PASSWORD_ITERATIONS = 120_000

engine_kwargs = {"echo": False}

if DATABASE_URL == "sqlite:///:memory:":
    # IMPORTANT: share the same connection for in-memory DB
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool
elif DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    iterations_text, salt, expected_digest = password_hash.split("$", 2)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations_text),
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def issue_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_schema() -> None:
    SQLModel.metadata.create_all(engine)

    inspector = inspect(engine)
    job_columns = {column["name"] for column in inspector.get_columns("job")} if inspector.has_table("job") else set()

    if "user_id" not in job_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE job ADD COLUMN user_id INTEGER"))


def create_auth_response(session: Session, user: User) -> AuthResponse:
    token = AuthToken(user_id=user.id, token=issue_token())
    session.add(token)
    session.commit()
    session.refresh(token)
    return AuthResponse(
        token=token.token,
        user=UserRead.model_validate(user),
    )


def get_current_user(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    token_value = authorization.removeprefix("Bearer ").strip()
    if not token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    with Session(engine) as session:
        token = session.exec(select(AuthToken).where(AuthToken.token == token_value)).first()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = session.get(User, token.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(title="Job Tracker API", version="1.0.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


# ----------------------------
# Routes
# ----------------------------

@app.get("/", tags=["Meta"])
def root():
    return RedirectResponse(url="/app", status_code=307)


@app.get("/api", tags=["Meta"])
def api_root():
    return {"message": "Job Tracker API running"}


@app.post("/auth/register", response_model=AuthResponse, tags=["Auth"], status_code=status.HTTP_201_CREATED)
def register(payload: AuthPayload):
    with Session(engine) as session:
        existing_user = session.exec(select(User).where(User.username == payload.username)).first()
        if existing_user:
            raise HTTPException(status_code=409, detail="Username already exists")

        user = User(username=payload.username, password_hash=hash_password(payload.password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return create_auth_response(session, user)


@app.post("/auth/login", response_model=AuthResponse, tags=["Auth"])
def login(payload: AuthPayload):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == payload.username)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong password")

        return create_auth_response(session, user)


@app.post("/auth/logout", tags=["Auth"])
def logout(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    token_value = authorization.removeprefix("Bearer ").strip()
    with Session(engine) as session:
        token = session.exec(select(AuthToken).where(AuthToken.token == token_value)).first()
        if token:
            session.delete(token)
            session.commit()
    return {"message": "Logged out"}


@app.get("/auth/me", response_model=UserRead, tags=["Auth"])
def me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user)


@app.get("/app", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/hello/{name}", tags=["Meta"])
def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobRead, tags=["Jobs"])
def create_job(payload: JobCreate, current_user: User = Depends(get_current_user)):
    new_job = Job(
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        stmt = select(Job).where(Job.user_id == current_user.id)

        if status is not None:
            stmt = stmt.where(Job.status == status)

        if company:
            stmt = stmt.where(Job.company.ilike(f"%{company}%"))

        if role:
            stmt = stmt.where(Job.role.ilike(f"%{role}%"))

        stmt = stmt.order_by(desc(Job.last_updated)).offset(offset).limit(limit)
        return session.exec(stmt).all()


@app.get("/jobs/{job_id}", response_model=JobRead, tags=["Jobs"])
def get_job(job_id: int, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


@app.patch("/jobs/{job_id}", response_model=JobRead, tags=["Jobs"])
def update_job(job_id: int, payload: JobUpdate, current_user: User = Depends(get_current_user)):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Job not found")

        for key, value in update_data.items():
            setattr(job, key, value)

        job.last_updated = datetime.now(timezone.utc)

        session.add(job)
        session.commit()
        session.refresh(job)
        return job


@app.delete("/jobs/{job_id}", tags=["Jobs"])
def delete_job(job_id: int, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Job not found")

        session.delete(job)
        session.commit()
        return {"message": "Job deleted", "job_id": job_id}
