from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.analyzer import analyze_repository_bundle
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

    with TestClient(application, base_url="http://127.0.0.1") as client:
        response = client.post("/api/analyses", json={"repository": "northstar/atlas-api"})
        listing = client.get("/api/analyses")

    assert response.status_code == 201
    assert response.json()["score"] == 100
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_create_action_item(tmp_path: Path) -> None:
    application = create_app(tmp_path / "quorum-actions.db")

    with TestClient(application, base_url="http://127.0.0.1") as client:
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


def test_overview_counts_all_records_and_api_rejects_invalid_actions(tmp_path):
    application = create_app(tmp_path / "overview.db")
    with TestClient(application, base_url="http://127.0.0.1") as client:
        db = application.state.database
        for _ in range(101):
            db.save_analysis(analyze_repository_bundle(DEMO_BUNDLE))
            db.save_action_item("owner/repo", "Valid action", "medium")
        overview = client.get("/api/overview").json()
        assert overview["analyses"] == 102
        assert overview["open_actions"] == 101
        for changes in [{"repository": "owner/.."}, {"title": " " * 10}, {"priority": "invalid"}]:
            payload = {"repository": "owner/repo", "title": "Valid action", **changes}
            assert client.post("/api/action-items", json=payload).status_code == 422
        assert db.overview()["open_actions"] == 101


def test_rebinding_host_is_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "host.db"), base_url="http://127.0.0.1") as client:
        assert client.get("/api/analyses", headers={"host": "attacker.example"}).status_code == 400
        assert client.get("/api/analyses").status_code == 200
