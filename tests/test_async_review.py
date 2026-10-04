from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_review_storage_round_trip():
    payload = {
        "product_id": "SKU-TEST-REVIEW-001",
        "decision": "HUMAN_REVIEW",
        "reviewer": "analyst_demo",
        "notes": "Needs manual confirmation for category drift.",
        "evidence": ["taxonomy mismatch", "missing color"],
    }
    response = client.post("/api/reviews", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_id"] == payload["product_id"]
    assert body["decision"] == payload["decision"]

    list_response = client.get("/api/reviews")
    assert list_response.status_code == 200, list_response.text
    items = list_response.json()["items"]
    assert any(item["product_id"] == payload["product_id"] for item in items)


def test_async_batch_job_flow():
    response = client.post("/api/jobs/process_batch", json={"batch_size": 5})
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] in {"queued", "processing", "completed"}
    job_id = job["job_id"]

    poll = client.get(f"/api/jobs/{job_id}")
    assert poll.status_code == 200, poll.text
    data = poll.json()
    assert data["job_id"] == job_id
    assert "summary" in data or data["status"] in {"processing", "completed"}
