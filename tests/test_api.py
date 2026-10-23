from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.demo_data import DEMO_BUNDLE
from app.main import create_app


class FakeGitHubClient:
    def __init__(self, _: str | None = None) -> None:
        pass

    async def fetch_repository_bundle(self, repository: str) -> dict:
        assert repository == "northstar/atlas-api"
        bundle = deepcopy(DEMO_BUNDLE)
        bundle["repository"]["pushed_at"] = datetime.now(UTC).isoformat()
        return bundle


def test_create_and_read_analysis(tmp_path: Path) -> None:
    application = create_app(tmp_path / "quorum-test.db")
    application.state.github_client_factory = FakeGitHubClient

    with TestClient(application) as client:
        response = client.post("/api/analyses", json={"repository": "northstar/atlas-api"})
        listing = client.get("/api/analyses")

    assert response.status_code == 201
    assert response.json()["score"] == 100
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_create_action_item(tmp_path: Path) -> None:
    application = create_app(tmp_path / "quorum-actions.db")

    with TestClient(application) as client:
        response = client.post(
            "/api/action-items",
            json={
                "repository": "northstar/atlas-api",
                "title": "Add an integration test",
                "priority": "high",
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "open"
