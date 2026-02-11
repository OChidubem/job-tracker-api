import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

import main


@pytest.fixture()
def client(tmp_path):
    # New DB per test session
    db_path = tmp_path / "test.db"
    test_url = f"sqlite:///{db_path}"

    # Patch main.engine to point to the temp DB
    main.engine = create_engine(test_url, connect_args={"check_same_thread": False})

    # Create tables
    SQLModel.metadata.create_all(main.engine)

    with TestClient(main.app) as c:
        yield c


def test_create_job_accepts_lowercase_status(client):
    res = client.post(
        "/jobs",
        json={
            "company": "Amazon",
            "role": "Backend Intern",
            "status": "applied",
            "notes": "test",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "Applied"


def test_update_job_accepts_mixed_case_status(client):
    created = client.post(
        "/jobs",
        json={"company": "Google", "role": "SWE", "status": "Applied"},
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]

    updated = client.patch(
        f"/jobs/{job_id}",
        json={"status": "phone screen"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "Phone Screen"


def test_hello_endpoint_exists(client):
    res = client.get("/hello/User")
    assert res.status_code == 200, res.text
    assert res.json()["message"] == "Hello User"
