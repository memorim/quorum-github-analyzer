import hashlib
import json
import os
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.access import access_configuration
from app.demo_data import DEMO_BUNDLE
from app.github_client import GitHubClientError
from app.main import create_app
from app.postgres import verified_dsn


def configure(monkeypatch):
    keys = {"first": "first-test-key-" + "a" * 36, "second": "second-test-key-" + "b" * 36}
    monkeypatch.setenv("QUORUM_PUBLIC_ORIGIN", "https://quorum.example.test")
    monkeypatch.setenv(
        "QUORUM_USERS",
        json.dumps(
            {
                name: {"key_hash": hashlib.sha256(key.encode()).hexdigest()}
                for name, key in keys.items()
            }
        ),
    )
    return keys


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_public_accounts_isolate_reports_actions_cache_and_survive_restart(
    tmp_path, monkeypatch, backend
):
    if backend == "postgres":
        if not os.getenv("QUORUM_TEST_DATABASE_URL"):
            pytest.skip("Configure a separate PostgreSQL test database")
        monkeypatch.setenv("QUORUM_DATABASE_URL", os.environ["QUORUM_TEST_DATABASE_URL"])
    keys = configure(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "operator-private-token-must-not-be-inherited")
    path = tmp_path / "quorum.db"
    first, second = (name for name in keys)
    app = create_app(path)

    class Client:
        calls = 0

        def __init__(self, token):
            assert token is None

        async def fetch_repository_bundle(self, _repository):
            Client.calls += 1
            return deepcopy(DEMO_BUNDLE)

    app.state.github_client_factory = Client
    with TestClient(app, base_url="https://quorum.example.test") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/analyses").status_code == 401
        assert client.get("/", auth=(first, "wrong-key-" + "a" * 40)).status_code == 401
        client.auth = (first, keys[first])
        assert client.post("/api/analyses/demo").status_code == 403
        client.headers["Origin"] = "https://quorum.example.test"
        result = client.post("/api/analyses", json={"repository": "owner/repo"})
        assert result.status_code == 201
        identifier = result.json()["id"]
        cached = client.post("/api/analyses", json={"repository": "owner/repo"})
        assert cached.status_code == 201
        assert cached.json()["metrics"]["collection"]["cache"]["available"]
        assert Client.calls == 1
        action = client.post(
            "/api/action-items",
            json={
                "repository": "owner/repo",
                "title": "Private first-user action",
                "priority": "high",
            },
        )
        assert action.status_code == 201
        assert client.get("/api/overview").json()["analyses"] == 2
        client.auth = (second, keys[second])
        assert client.get("/api/analyses").json() == []
        assert client.get("/api/analyses/" + identifier).status_code == 404
        assert client.get("/api/action-items").json() == []
        assert client.post("/api/analyses", json={"repository": "owner/repo"}).status_code == 201
        assert Client.calls == 2  # Account caches and upstream credentials are separate.
    reopened = create_app(path)
    with TestClient(reopened, base_url="https://quorum.example.test") as client:
        client.auth = (first, keys[first])
        assert client.get("/api/analyses/" + identifier).status_code == 200
        assert len(client.get("/api/action-items").json()) == 1
        assert "no-store" in client.get("/api/analyses").headers["Cache-Control"]


def test_rate_limit_cooldown_survives_restart_without_repeating_upstream(tmp_path):
    class Limited:
        calls = 0

        def __init__(self, _token):
            pass

        async def fetch_repository_bundle(self, _repository):
            Limited.calls += 1
            raise GitHubClientError("GitHub API rate limit reached.", retry_after=120)

    path = tmp_path / "rate.db"
    for _ in range(2):
        app = create_app(path)
        app.state.github_client_factory = Limited
        with TestClient(app, base_url="http://127.0.0.1") as client:
            result = client.post("/api/analyses", json={"repository": "owner/repo"})
            assert result.status_code == 429
            assert 1 <= int(result.headers["Retry-After"]) <= 120
    assert Limited.calls == 1


def test_public_configuration_fails_closed_and_remote_postgres_verifies_tls(monkeypatch):
    monkeypatch.setenv("QUORUM_PUBLIC_ORIGIN", "http://quorum.example")
    with pytest.raises(ValueError, match="HTTPS"):
        access_configuration()
    monkeypatch.setenv("QUORUM_PUBLIC_ORIGIN", "https://quorum.example")
    monkeypatch.setenv("QUORUM_USERS", "{}")
    with pytest.raises(ValueError, match="individual"):
        access_configuration()
    dsn = verified_dsn("postgresql://user:secret@db.example/app?sslmode=disable")
    assert "sslmode=verify-full" in dsn and "sslrootcert=system" in dsn
