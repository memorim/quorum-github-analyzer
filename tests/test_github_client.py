import asyncio
from copy import deepcopy

import httpx
import pytest

from app.analyzer import analyze_repository_bundle
from app.demo_data import DEMO_BUNDLE
from app.github_client import GitHubClient, GitHubClientError

client_type = httpx.AsyncClient


def test_malformed_required_json_is_a_domain_error(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: client_type(
            **kw,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json")),
        ),
    )
    try:
        asyncio.run(GitHubClient().fetch_repository_bundle("owner/repo"))
    except GitHubClientError:
        return
    raise AssertionError("Malformed upstream JSON must not escape as an internal exception")


def test_optional_failures_are_not_silent(monkeypatch):
    def respond(request):
        if request.url.path == "/repos/owner/repo":
            return httpx.Response(200, json={"full_name": "owner/repo", "pushed_at": None})
        return httpx.Response(403, json={"message": "private upstream details"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client_type(**kw, transport=httpx.MockTransport(respond))
    )
    result = asyncio.run(GitHubClient().fetch_repository_bundle("owner/repo"))
    assert result.get("collection", {}).get("workflow_runs", {}).get("available") is False


def install_transport(monkeypatch, handler):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: client_type(**kw, transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    "code,headers,expected",
    [
        (404, {}, "not found"),
        (401, {}, "permissions"),
        (403, {}, "permissions"),
        (403, {"x-ratelimit-remaining": "0"}, "rate limit"),
        (403, {"retry-after": "5"}, "rate limit"),
        (429, {}, "rate limit"),
        (500, {}, "500"),
        (301, {"location": "http://127.0.0.1/secret"}, "moved"),
    ],
)
def test_required_errors_are_bounded_and_never_retried(monkeypatch, code, headers, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(code, headers=headers, json={"message": "private upstream payload"})

    install_transport(monkeypatch, handler)
    with pytest.raises(GitHubClientError, match=expected) as caught:
        asyncio.run(GitHubClient("test-secret").fetch_repository_bundle("owner/repo"))
    assert len(calls) == 1
    assert calls[0].url.host == "api.github.com"
    assert "test-secret" not in str(caught.value)
    assert "private upstream" not in str(caught.value)


def test_timeout_is_a_safe_domain_error(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("test-secret", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(GitHubClientError, match="Could not connect") as caught:
        asyncio.run(GitHubClient().fetch_repository_bundle("owner/repo"))
    assert "test-secret" not in str(caught.value)


def test_pagination_is_bounded_and_never_follows_link_hosts(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        page = int(request.url.params.get("page", 1))
        if path == "/repos/owner/repo":
            return httpx.Response(
                200, json={**DEMO_BUNDLE["repository"], "full_name": "renamed/repo"}
            )
        if path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 100})
        if path.endswith("/issues"):
            items = [
                {
                    "number": page * 100 + i + 1,
                    "title": "Issue",
                    "pull_request": {} if i == 0 else None,
                }
                for i in range(50)
            ]
            return httpx.Response(
                200, json=items, headers={"link": '<http://127.0.0.1/secret>; rel="next"'}
            )
        if path.endswith("/pulls"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"workflow_runs": []})

    install_transport(monkeypatch, handler)
    bundle = asyncio.run(GitHubClient().fetch_repository_bundle("owner/repo"))
    assert len(bundle["issues"]) == 147
    assert bundle["collection"]["issues"] == {"available": True, "truncated": True, "error": None}
    assert len([r for r in calls if r.url.path.endswith("/issues")]) == 3
    assert all(r.url.host == "api.github.com" for r in calls)
    assert bundle["repository"]["html_url"] == "https://github.com/renamed/repo"
    assert bundle["issues"][0]["html_url"].startswith("https://github.com/renamed/repo/issues/")
    report = analyze_repository_bundle(bundle)
    assert report["metrics"]["analysis_scope"] == "github_metadata_only"
    assert report["metrics"]["open_issues"] == 147
    assert "partial snapshot" in report["verdict"]


def test_second_page_failure_preserves_sample_and_reports_incompleteness(monkeypatch):
    def handler(request):
        path = request.url.path
        if path == "/repos/owner/repo":
            return httpx.Response(
                200, json={**DEMO_BUNDLE["repository"], "full_name": "owner/repo"}
            )
        if path.endswith("/languages"):
            return httpx.Response(200, json={})
        if path.endswith("/issues"):
            if request.url.params["page"] == "1":
                return httpx.Response(
                    200,
                    json=[{"number": 1, "title": "Keep this issue"}],
                    headers={"link": '<ignored>; rel="next"'},
                )
            return httpx.Response(429)
        if path.endswith("/pulls"):
            return httpx.Response(200, json=[])
        return httpx.Response(403)

    install_transport(monkeypatch, handler)
    bundle = asyncio.run(GitHubClient().fetch_repository_bundle("owner/repo"))
    assert len(bundle["issues"]) == 1
    assert bundle["collection"]["issues"]["available"] is False
    report = analyze_repository_bundle(bundle)
    assert report["metrics"]["ci_success_rate"] is None
    assert not any(r["title"] == "No recent CI runs found" for r in report["risks"])


@pytest.mark.parametrize(
    "repository",
    [
        "../..",
        "owner/.",
        "owner/..",
        "https://github.com/owner/repo",
        "owner/repo?x=1",
        "owner/repo/sub",
    ],
)
def test_invalid_repository_never_reaches_network(monkeypatch, repository):
    def handler(request):
        raise AssertionError("Must not perform a request")

    install_transport(monkeypatch, handler)
    with pytest.raises(GitHubClientError):
        asyncio.run(GitHubClient().fetch_repository_bundle(repository))


def test_empty_repository_unknown_date_does_not_mean_999_days_inactive():
    bundle = deepcopy(DEMO_BUNDLE)
    bundle["repository"]["pushed_at"] = None
    report = analyze_repository_bundle(bundle)
    assert report["metrics"]["days_since_push"] is None
    assert not any(r["title"] == "Repository is inactive" for r in report["risks"])


@pytest.mark.parametrize(
    "payload",
    [None, [], {"wrong": "shape"}, {"full_name": "owner/repo", "pushed_at": "invalid-date"}],
)
def test_invalid_repository_shapes_are_domain_errors(monkeypatch, payload):
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(GitHubClientError):
        asyncio.run(GitHubClient().fetch_repository_bundle("owner/repo"))
