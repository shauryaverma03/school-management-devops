import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
for name in ["TEACHER_TOKEN", "OTHER_TEACHER_TOKEN", "STUDENT_TOKEN"]:
    os.environ[name] = name + "x" * 32

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def test_attendance_rules():
    with TestClient(app) as client:
        payload = {
            "student_id": 1,
            "day": "2026-11-15",
            "session": "morning",
            "present": True,
        }
        endpoint = "/classes/1/attendance"
        assert client.get("/ready").status_code == 200
        assert client.post(endpoint, json=payload).status_code == 401
        for name in ["OTHER_TEACHER_TOKEN", "STUDENT_TOKEN"]:
            assert (
                client.post(
                    endpoint,
                    json=payload,
                    headers={"Authorization": "Bearer " + os.environ[name]},
                ).status_code
                == 403
            )
        headers = {"Authorization": "Bearer " + os.environ["TEACHER_TOKEN"]}
        assert (
            client.post(
                endpoint, json={**payload, "student_id": 2}, headers=headers
            ).status_code
            == 422
        )
        assert client.post(endpoint, json=payload, headers=headers).status_code == 201
        assert client.post(endpoint, json=payload, headers=headers).status_code == 409
