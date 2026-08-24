from fastapi.testclient import TestClient


def test_health_returns_service_and_database_status(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "memoryscope-api",
        "version": "0.1.0",
        "database": {
            "engine": "sqlite",
            "status": "configured",
        },
    }
