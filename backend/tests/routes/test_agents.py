"""Tests for GET /agents."""

from fastapi.testclient import TestClient


def test_list_agents_returns_full_roster(client: TestClient) -> None:
    response = client.get("/agents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    ids = {agent["id"] for agent in body}
    assert ids == {"tapio", "ilmarinen", "sampo", "rauni", "otso"}
    expected_keys = {"id", "name", "title", "category", "summary", "color"}
    assert all(expected_keys <= agent.keys() for agent in body)
