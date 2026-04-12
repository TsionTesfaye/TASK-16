"""Basic API test to verify the app starts and the health endpoint works."""


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"


def test_health_returns_json(client):
    response = client.get("/health")
    assert response.content_type == "application/json"
