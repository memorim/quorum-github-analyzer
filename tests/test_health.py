from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint(tmp_path) -> None:
    with TestClient(create_app(tmp_path / "health.db"), base_url="http://127.0.0.1") as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "quorum-git-agent"}
