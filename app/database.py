from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def overview(self) -> dict[str, int | float]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS analyses, COALESCE(ROUND(AVG(score),1),0) AS average_score, "
                "(SELECT COUNT(*) FROM action_items WHERE status='open') AS open_actions "
                "FROM analyses"
            ).fetchone()
        return dict(row)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    repository_url TEXT,
                    score INTEGER NOT NULL,
                    verdict TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    risks_json TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    triaged_issues_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS action_items (
                    id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    title TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        analysis_id = uuid4().hex[:12]
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses (
                    id, repository, repository_url, score, verdict, summary,
                    metrics_json, risks_json, actions_json, triaged_issues_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    analysis["repository"],
                    analysis.get("repository_url"),
                    analysis["score"],
                    analysis["verdict"],
                    analysis["summary"],
                    json.dumps(analysis["metrics"], ensure_ascii=False),
                    json.dumps(analysis["risks"], ensure_ascii=False),
                    json.dumps(analysis["actions"], ensure_ascii=False),
                    json.dumps(analysis["triaged_issues"], ensure_ascii=False),
                    created_at,
                ),
            )
        return self.get_analysis(analysis_id) or {}

    def count_analyses(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM analyses").fetchone()
        return int(row["count"])

    def list_analyses(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._analysis_from_row(row) for row in rows]

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analyses WHERE id = ?",
                (analysis_id,),
            ).fetchone()
        return self._analysis_from_row(row) if row else None

    def save_action_item(self, repository: str, title: str, priority: str) -> dict[str, str]:
        item = {
            "id": uuid4().hex[:12],
            "repository": repository,
            "title": title,
            "priority": priority,
            "status": "open",
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO action_items (id, repository, title, priority, status, created_at)
                VALUES (:id, :repository, :title, :priority, :status, :created_at)
                """,
                item,
            )
        return item

    def list_action_items(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM action_items ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _analysis_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "repository": row["repository"],
            "repository_url": row["repository_url"],
            "score": row["score"],
            "verdict": row["verdict"],
            "summary": row["summary"],
            "metrics": json.loads(row["metrics_json"]),
            "risks": json.loads(row["risks_json"]),
            "actions": json.loads(row["actions_json"]),
            "triaged_issues": json.loads(row["triaged_issues_json"]),
            "created_at": row["created_at"],
        }
