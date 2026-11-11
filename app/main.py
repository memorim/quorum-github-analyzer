from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.access import access_configuration
from app.analyzer import analyze_repository_bundle
from app.config import PROJECT_ROOT, database_path, github_token
from app.database import Database
from app.demo_data import DEMO_BUNDLE
from app.github_client import GitHubClient, GitHubClientError
from app.postgres import PostgresDatabase
from app.schemas import ActionItemRequest, AnalysisRequest


def create_app(database_file: Path | None = None) -> FastAPI:
    access = access_configuration()
    dsn = os.getenv("QUORUM_DATABASE_URL", "")
    if access and not dsn and database_file is None and not os.getenv("QUORUM_DATABASE_PATH"):
        raise ValueError(
            "Public mode requires persistent QUORUM_DATABASE_URL or QUORUM_DATABASE_PATH"
        )
    path = database_file or database_path()
    database = PostgresDatabase(dsn, "local") if dsn else Database(path)
    databases = {}
    if access:
        for name in access.accounts:
            digest = hashlib.sha256(name.encode()).hexdigest()
            databases[name] = (
                PostgresDatabase(dsn, "account:" + name)
                if dsn
                else Database(path.parent / "accounts" / digest / "quorum.db")
            )
    locks = {name: asyncio.Lock() for name in databases} if access else {"local": asyncio.Lock()}

    def active_database(request: Request):
        return databases[request.state.account.name] if access else database

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        for user_database in databases.values():
            user_database.initialize()
        if not access and database.count_analyses() == 0:
            database.save_analysis(analyze_repository_bundle(DEMO_BUNDLE))
        yield

    application = FastAPI(
        title="Quorum Git Agent",
        version="0.2.0",
        description="Repository intelligence through REST and MCP.",
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.databases = databases
    if access:

        @application.middleware("http")
        async def authenticate(request: Request, call_next):
            if request.url.path == "/api/health":
                return await call_next(request)
            account = access.authenticate(request.headers.get("authorization", ""))
            if not account:
                return JSONResponse(
                    {"detail": "Individual access key required."},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": 'Basic realm="Quorum", charset="UTF-8"',
                        "Cache-Control": "no-store",
                    },
                )
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and request.headers.get("origin") != access.origin
            ):
                return JSONResponse({"detail": "Invalid request origin."}, status_code=403)
            request.state.account = account
            if request.method not in {"GET", "HEAD", "OPTIONS"} and not active_database(
                request
            ).take_budget("writes", 60):
                return JSONResponse(
                    {"detail": "Request budget reached."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[access.hostname] if access else ["localhost", "127.0.0.1", "[::1]"],
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
    async def overview(request: Request) -> dict[str, float | int]:
        return active_database(request).overview()

    @application.get("/api/analyses", tags=["analysis"])
    async def list_analyses(request: Request, limit: int = 20) -> list[dict]:
        return active_database(request).list_analyses(limit=max(1, min(limit, 100)))

    @application.get("/api/analyses/{analysis_id}", tags=["analysis"])
    async def get_analysis(analysis_id: str, request: Request) -> dict:
        analysis = active_database(request).get_analysis(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return analysis

    @application.post("/api/analyses/demo", status_code=201, tags=["analysis"])
    async def create_demo_analysis(request: Request) -> dict:
        return active_database(request).save_analysis(analyze_repository_bundle(DEMO_BUNDLE))

    @application.post("/api/analyses", status_code=201, tags=["analysis"])
    async def create_analysis(payload: AnalysisRequest, request: Request) -> dict:
        db = active_database(request)
        owner = request.state.account.name if access else "local"
        # Public users never inherit the operator's global private GitHub credential.
        token = request.state.account.github_token if access else github_token()
        async with locks[owner]:
            bundle = db.cached_bundle(payload.repository)
            if bundle is None:
                retry_after = db.github_retry_after()
                if retry_after:
                    raise HTTPException(
                        429,
                        "GitHub API cooldown is active.",
                        headers={"Retry-After": str(retry_after)},
                    )
                if not db.take_budget("github-analysis", 10):
                    raise HTTPException(
                        429, "Analysis request budget reached.", headers={"Retry-After": "60"}
                    )
                client = application.state.github_client_factory(token)
                try:
                    bundle = await client.fetch_repository_bundle(payload.repository)
                except GitHubClientError as error:
                    if error.retry_after:
                        db.pause_github(error.retry_after)
                        raise HTTPException(
                            429, str(error), headers={"Retry-After": str(error.retry_after)}
                        ) from error
                    raise HTTPException(status_code=422, detail=str(error)) from error
                db.cache_bundle(payload.repository, bundle)
                delays = [
                    state.get("retry_after", 0) for state in bundle.get("collection", {}).values()
                ]
                if delays and max(delays):
                    db.pause_github(max(delays))
            return db.save_analysis(analyze_repository_bundle(bundle))

    @application.get("/api/action-items", tags=["actions"])
    async def list_action_items(request: Request, limit: int = 30) -> list[dict]:
        return active_database(request).list_action_items(limit=max(1, min(limit, 100)))

    @application.post("/api/action-items", status_code=201, tags=["actions"])
    async def create_action_item(payload: ActionItemRequest, request: Request) -> dict:
        return active_database(request).save_action_item(
            repository=payload.repository,
            title=payload.title,
            priority=payload.priority,
        )

    return application


app = create_app()
