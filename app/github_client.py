from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field, NonNegativeInt, TypeAdapter, ValidationError

from app.schemas import normalize_repository


class GitHubClientError(RuntimeError):
    pass


class RepositoryMetadata(BaseModel):
    full_name: str
    description: str | None = None
    stargazers_count: NonNegativeInt = 0
    forks_count: NonNegativeInt = 0
    archived: bool = False
    default_branch: str = "main"
    pushed_at: datetime | None = None
    license: dict | None = None
    topics: list[str] = Field(default_factory=list)


class IssueMetadata(BaseModel):
    number: int = Field(gt=0)
    title: str = Field(max_length=1000)
    comments: NonNegativeInt = 0
    created_at: datetime | None = None
    labels: list[dict | str] = Field(default_factory=list)
    pull_request: dict | None = None


class WorkflowMetadata(BaseModel):
    conclusion: str | None = None


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    async def fetch_repository_bundle(self, repository: str) -> dict[str, Any]:
        try:
            repository = normalize_repository(repository)
        except ValueError as error:
            raise GitHubClientError(str(error)) from error
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "quorum-git-agent",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=15,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            payload, _ = await self._get(client, f"/repos/{repository}")
            try:
                repo = RepositoryMetadata.model_validate(payload).model_dump(mode="json")
                canonical = normalize_repository(repo["full_name"])
            except (ValueError, ValidationError) as error:
                raise GitHubClientError("GitHub returned invalid repository metadata.") from error
            # Construct paths and links ourselves; never follow a supplied Link/Location URL.
            repo["html_url"] = f"https://github.com/{canonical}"
            collection = {}
            languages, collection["languages"] = await self._collect(
                client,
                f"/repos/{canonical}/languages",
                {},
                TypeAdapter(dict[str, NonNegativeInt]),
            )
            issues, collection["issues"] = await self._collect(
                client,
                f"/repos/{canonical}/issues",
                [],
                TypeAdapter(list[IssueMetadata]),
                params={"state": "open", "per_page": 50, "sort": "updated"},
                pages=3,
            )
            pulls, collection["pulls"] = await self._collect(
                client,
                f"/repos/{canonical}/pulls",
                [],
                TypeAdapter(list[IssueMetadata]),
                params={"state": "open", "per_page": 50},
                pages=2,
            )
            runs, collection["workflow_runs"] = await self._collect(
                client,
                f"/repos/{canonical}/actions/runs",
                [],
                TypeAdapter(list[WorkflowMetadata]),
                params={"per_page": 20},
                field="workflow_runs",
                pages=1,
            )
        issues = [item for item in issues if item.pop("pull_request", None) is None]
        for issue in issues:
            issue["html_url"] = f"https://github.com/{canonical}/issues/{issue['number']}"
        return {
            "repository": repo,
            "languages": languages,
            "issues": issues,
            "pulls": pulls,
            "workflow_runs": runs,
            "collection": collection,
        }

    @staticmethod
    async def _get(client: httpx.AsyncClient, path: str, params: dict | None = None):
        try:
            response = await client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            response = error.response
            code = response.status_code
            if code == 404:
                message = "Repository was not found or is private."
            elif code == 429 or (
                code == 403
                and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in response.headers
                )
            ):
                message = "GitHub API rate limit reached. Wait before retrying."
            elif code in {401, 403}:
                message = "GitHub denied access. Check token permissions."
            elif code in {301, 302, 307, 308}:
                message = "Repository moved. Retry using its current owner/name."
            else:
                message = f"GitHub API returned {code}."
            raise GitHubClientError(message) from error
        except httpx.HTTPError as error:
            raise GitHubClientError("Could not connect to the GitHub API.") from error
        try:
            return response.json(), 'rel="next"' in response.headers.get("link", "")
        except ValueError as error:
            raise GitHubClientError("GitHub returned invalid JSON.") from error

    async def _collect(self, client, path, fallback, adapter, *, params=None, pages=1, field=None):
        result = fallback.copy()
        status = {"available": True, "truncated": False, "error": None}
        try:
            for page in range(1, pages + 1):
                data, has_next = await self._get(
                    client,
                    path,
                    {**params, "page": page} if params else None,
                )
                if field:
                    data = data[field]
                validated = adapter.validate_python(data)
                if isinstance(validated, list):
                    # Bound output even if a broken upstream ignores per_page.
                    if len(validated) > (params or {}).get("per_page", 100):
                        raise ValueError("Oversized collection")
                    result.extend(item.model_dump(mode="json") for item in validated)
                else:
                    result = validated
                status["truncated"] = has_next
                if not has_next:
                    break
        except (GitHubClientError, ValueError, KeyError, TypeError) as error:
            status.update(
                available=False,
                truncated=bool(result),
                error=(
                    str(error) if isinstance(error, GitHubClientError) else "Invalid GitHub data."
                ),
            )
        return result, status
