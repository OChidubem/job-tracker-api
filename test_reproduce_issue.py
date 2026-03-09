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


def register_and_login(client, username="userone", password="password123"):
    res = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert res.status_code == 201, res.text
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_job_accepts_lowercase_status(client):
    headers = register_and_login(client)
    res = client.post(
        "/jobs",
        json={
            "company": "Amazon",
            "role": "Backend Intern",
            "status": "applied",
            "notes": "test",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "Applied"


def test_update_job_accepts_mixed_case_status(client):
    headers = register_and_login(client)
    created = client.post(
        "/jobs",
        json={"company": "Google", "role": "SWE", "status": "Applied"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]

    updated = client.patch(
        f"/jobs/{job_id}",
        json={"status": "phone screen"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "Phone Screen"


def test_hello_endpoint_exists(client):
    res = client.get("/hello/User")
    assert res.status_code == 200, res.text
    assert res.json()["message"] == "Hello User"


def test_frontend_route_serves_html(client):
    res = client.get("/app")
    assert res.status_code == 200, res.text
    assert "text/html" in res.headers["content-type"]
    assert "Career Pipeline Hub" in res.text


def test_root_redirects_to_frontend(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307, res.text
    assert res.headers["location"] == "/app"


def test_register_returns_token_and_profile(client):
    res = client.post(
        "/auth/register",
        json={"username": "janedoe", "password": "password123"},
    )
    assert res.status_code == 201, res.text
    payload = res.json()
    assert payload["token"]
    assert payload["user"]["username"] == "janedoe"


def test_login_returns_new_token(client):
    register_and_login(client, username="janedoe", password="password123")
    res = client.post(
        "/auth/login",
        json={"username": "janedoe", "password": "password123"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["token"]


def test_login_with_wrong_password_returns_specific_message(client):
    register_and_login(client, username="janedoe", password="password123")
    res = client.post(
        "/auth/login",
        json={"username": "janedoe", "password": "wrongpass123"},
    )
    assert res.status_code == 401, res.text
    assert res.json()["detail"] == "Wrong password"


def test_jobs_require_authentication(client):
    res = client.get("/jobs")
    assert res.status_code == 401, res.text


def test_jobs_are_scoped_per_user(client):
    first_headers = register_and_login(client, username="firstuser", password="password123")
    second_headers = register_and_login(client, username="seconduser", password="password123")

    created = client.post(
        "/jobs",
        json={"company": "Acme", "role": "Engineer", "status": "Applied"},
        headers=first_headers,
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]

    first_list = client.get("/jobs", headers=first_headers)
    second_list = client.get("/jobs", headers=second_headers)
    second_get = client.get(f"/jobs/{job_id}", headers=second_headers)

    assert len(first_list.json()) == 1
    assert second_list.json() == []
    assert second_get.status_code == 404, second_get.text


def test_create_job_rejects_blank_company(client):
    headers = register_and_login(client)
    res = client.post(
        "/jobs",
        json={
            "company": "   ",
            "role": "Backend Engineer",
            "status": "Applied",
        },
        headers=headers,
    )
    assert res.status_code == 422, res.text


def test_update_job_rejects_blank_role(client):
    headers = register_and_login(client)
    created = client.post(
        "/jobs",
        json={"company": "Google", "role": "SWE", "status": "Applied"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]

    updated = client.patch(
        f"/jobs/{job_id}",
        json={"role": "   "},
        headers=headers,
    )
    assert updated.status_code == 422, updated.text
