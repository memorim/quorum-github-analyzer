from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analyzer import analyze_repository_bundle
from app.config import PROJECT_ROOT, database_path, github_token
from app.database import Database
from app.demo_data import DEMO_BUNDLE
from app.github_client import GitHubClient, GitHubClientError
from app.schemas import ActionItemRequest, AnalysisRequest


def create_app(database_file: Path | None = None) -> FastAPI:
    database = Database(database_file or database_path())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        if database.count_analyses() == 0:
            database.save_analysis(analyze_repository_bundle(DEMO_BUNDLE))
        yield

    application = FastAPI(
        title="Quorum Git Agent",
        version="0.2.0",
        description="Repository intelligence through REST and MCP.",
        lifespan=lifespan,
    )
    application.state.database = database
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"]
    )
    application.state.github_client_factory = GitHubClient
    static_directory = PROJECT_ROOT / "app" / "static"
    application.mount("/static", StaticFiles(directory=static_directory), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(static_directory / "index.html")

    @application.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "quorum-git-agent"}

    @application.get("/api/overview", tags=["analysis"])
    async def overview() -> dict[str, float | int]:
        return database.overview()

    @application.get("/api/analyses", tags=["analysis"])
    async def list_analyses(limit: int = 20) -> list[dict]:
        return database.list_analyses(limit=max(1, min(limit, 100)))

    @application.get("/api/analyses/{analysis_id}", tags=["analysis"])
    async def get_analysis(analysis_id: str) -> dict:
        analysis = database.get_analysis(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return analysis

    @application.post("/api/analyses/demo", status_code=201, tags=["analysis"])
    async def create_demo_analysis() -> dict:
        return database.save_analysis(analyze_repository_bundle(DEMO_BUNDLE))

    @application.post("/api/analyses", status_code=201, tags=["analysis"])
    async def create_analysis(payload: AnalysisRequest) -> dict:
        client = application.state.github_client_factory(github_token())
        try:
            bundle = await client.fetch_repository_bundle(payload.repository)
        except GitHubClientError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return database.save_analysis(analyze_repository_bundle(bundle))

    @application.get("/api/action-items", tags=["actions"])
    async def list_action_items(limit: int = 30) -> list[dict]:
        return database.list_action_items(limit=max(1, min(limit, 100)))

    @application.post("/api/action-items", status_code=201, tags=["actions"])
    async def create_action_item(payload: ActionItemRequest) -> dict:
        return database.save_action_item(
            repository=payload.repository,
            title=payload.title,
            priority=payload.priority,
        )

    return application


app = create_app()
