"""Check a running deployment using synthetic attendance and authorization rules."""

import os
import uuid

import httpx

base = os.getenv("BASE_URL", "https://localhost:8443")
session = "smoke-" + uuid.uuid4().hex[:12]
headers = {"Authorization": "Bearer " + os.environ["TEACHER_TOKEN"]}
with httpx.Client(
    base_url=base, verify=os.getenv("LOCAL_TLS") != "1", timeout=15
) as client:
    assert client.get("/").status_code == 200
    assert client.get("/ready").status_code == 200
    body = {"student_id": 1, "day": "2026-11-15", "session": session, "present": True}
    endpoint = "/classes/1/attendance"
    assert client.post(endpoint, json=body).status_code == 401
    assert (
        client.post(
            endpoint,
            json=body,
            headers={"Authorization": "Bearer " + os.environ["STUDENT_TOKEN"]},
        ).status_code
        == 403
    )
    assert client.post(endpoint, json=body, headers=headers).status_code == 201
    assert client.post(endpoint, json=body, headers=headers).status_code == 409
    assert client.get("/operations", headers=headers).status_code == 200
    assert "school_http_requests_total" in client.get("/metrics").text
print("Deployment smoke checks passed.")
