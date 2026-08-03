"""Tests for GET /health."""

from fastapi.testclient import TestClient


def test_health_reports_model_availability(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"model_available": True}
