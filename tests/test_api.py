import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest

_test_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "sqlite:///" + _test_directory.name + "/test.db"
)
for name in ["TEACHER_TOKEN", "OTHER_TEACHER_TOKEN", "STUDENT_TOKEN"]:
    os.environ[name] = name + "x" * 32

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.main import app, engine  # noqa: E402

TEACHER = {"Authorization": "Bearer " + os.environ["TEACHER_TOKEN"]}
OTHER = {"Authorization": "Bearer " + os.environ["OTHER_TEACHER_TOKEN"]}
STUDENT = {"Authorization": "Bearer " + os.environ["STUDENT_TOKEN"]}
PAYLOAD = {"student_id": 1, "day": "2026-11-15", "session": "morning", "present": True}
ENDPOINT = "/classes/1/attendance"


@pytest.fixture
def client():
    with TestClient(app) as instance:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit"))
            conn.execute(text("DELETE FROM attendance"))
        yield instance


def test_attendance_permissions_and_membership(client):
    assert client.post(ENDPOINT, json=PAYLOAD).status_code == 401
    for headers in [OTHER, STUDENT]:
        assert client.post(ENDPOINT, json=PAYLOAD, headers=headers).status_code == 403
    assert (
        client.post(
            ENDPOINT, json={**PAYLOAD, "student_id": 2}, headers=TEACHER
        ).status_code
        == 422
    )
    assert client.post(ENDPOINT, json=PAYLOAD, headers=TEACHER).status_code == 201
    assert client.post(ENDPOINT, json=PAYLOAD, headers=TEACHER).status_code == 409


def test_batch_is_atomic_and_normalizes_session(client):
    assert client.post(ENDPOINT, json=PAYLOAD, headers=TEACHER).status_code == 201
    batch = {
        "day": PAYLOAD["day"],
        "session": " MORNING ",
        "entries": [
            {"student_id": 10, "present": True},
            {"student_id": 1, "present": False},
        ],
    }
    assert (
        client.post(ENDPOINT + "/batch", json=batch, headers=TEACHER).status_code == 409
    )
    rows = client.get(
        ENDPOINT, params={"day": PAYLOAD["day"], "session": "morning"}, headers=TEACHER
    ).json()
    assert len(rows) == 1
    assert len(client.get("/audit", headers=TEACHER).json()) == 1


def test_batch_validation_permissions_and_success(client):
    batch = {
        "day": PAYLOAD["day"],
        "session": "morning",
        "entries": [
            {"student_id": 10, "present": True},
            {"student_id": 11, "present": False},
        ],
    }
    for headers in [OTHER, STUDENT]:
        assert (
            client.post(ENDPOINT + "/batch", json=batch, headers=headers).status_code
            == 403
        )
    for entries in [
        [],
        [{"student_id": 2, "present": True}],
        [batch["entries"][0]] * 2,
    ]:
        assert (
            client.post(
                ENDPOINT + "/batch", json={**batch, "entries": entries}, headers=TEACHER
            ).status_code
            == 422
        )
    result = client.post(ENDPOINT + "/batch", json=batch, headers=TEACHER)
    assert result.status_code == 201
    assert result.json()["count"] == 2
    assert len(client.get("/audit", headers=TEACHER).json()) == 2


def test_concurrent_duplicate_has_one_winner(client):
    def submit(_):
        return client.post(ENDPOINT, json=PAYLOAD, headers=TEACHER).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(submit, range(2))) == [201, 409]
    assert len(client.get("/audit", headers=TEACHER).json()) == 1


def test_export_audit_and_operations_permissions(client):
    client.post(ENDPOINT, json=PAYLOAD, headers=TEACHER)
    params = {"day": PAYLOAD["day"], "session": "morning"}
    export = client.get(ENDPOINT + ".csv", params=params, headers=TEACHER)
    assert export.status_code == 200
    assert "Present" in export.text and "Pending" in export.text
    for headers in [OTHER, STUDENT]:
        assert (
            client.get(ENDPOINT + ".csv", params=params, headers=headers).status_code
            == 403
        )
    assert client.get("/audit", headers=STUDENT).status_code == 403
    assert client.get("/audit", headers=OTHER).json() == []
    assert client.get("/operations", headers=STUDENT).status_code == 403
    assert client.get("/operations", headers=TEACHER).json()["attendance_records"] == 1


def test_ui_health_and_observability(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/ready").json() == {"status": "ready"}
    assert client.get("/health").headers["X-Request-ID"]
    assert "school_http_requests_total" in client.get("/metrics").text


def test_readiness_failure_preserves_liveness(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def fail_connect():
        raise OperationalError("SELECT 1", {}, Exception("simulated unavailable DB"))

    monkeypatch.setattr(engine, "connect", fail_connect)
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200
