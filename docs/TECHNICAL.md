# Quorum — анализ GitHub-репозиториев

Repository intelligence for engineering teams, available through a visual
dashboard, REST API and Model Context Protocol tools.

Quorum inspects a public GitHub repository, calculates a transparent health
score, triages open issues, highlights delivery risks and stores every report
in SQLite. An MCP-compatible host can use the
tools immediately.

## What it demonstrates

- Python 3.11 and FastAPI service design
- GitHub REST API integration with explicit errors and bounded pagination
- SQL persistence with migrations created on startup
- MCP tools built with the official Python SDK
- deterministic repository scoring and issue triage
- responsive dashboard with no frontend build step
- pytest, Ruff, Docker and GitHub Actions

## Architecture

```mermaid
flowchart LR
    UI[Dashboard] --> API[FastAPI REST API]
    HOST[MCP host] --> MCP[MCP server]
    API --> ENGINE[Analysis engine]
    MCP --> ENGINE
    ENGINE --> GH[GitHub REST API]
    ENGINE --> DB[(SQLite)]
```

## Quick start

```powershell
git clone https://github.com/memorim/quorum-github-analyzer.git
cd quorum-github-analyzer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\start.ps1
```

Open:

- dashboard: `http://127.0.0.1:8010`
- Swagger UI: `http://127.0.0.1:8010/docs`
- health check: `http://127.0.0.1:8010/api/health`

The dashboard starts with a seeded fictional repository report, so the
interface is useful before the first external API request.

## GitHub token

Public repositories can be analyzed without a token. To increase the API rate
limit, copy `.env.example` to `.env` and add a fine-grained token:

```dotenv
GITHUB_TOKEN=github_pat_your_token
```

The token is read only on the server and is never returned to the browser.

## MCP server

Run the stdio server:

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server
```

Example client configuration:

```json
{
  "mcpServers": {
    "quorum": {
      "command": "C:\\path\\to\\quorum-git-agent\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp_server"],
      "cwd": "C:\\path\\to\\quorum-git-agent"
    }
  }
}
```

Available tools:

- `analyze_repository`
- `list_recent_analyses`
- `get_repository_brief`
- `create_action_item`

## REST examples

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8010/api/analyses `
  -ContentType "application/json" `
  -Body '{"repository":"fastapi/fastapi"}'
```

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/analyses
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --cov=app
```

## Docker

```powershell
docker compose up --build
```

The SQLite database is stored in the `quorum-data` volume.

## Project structure

```text
app/
  analyzer.py       transparent scoring and issue triage
  database.py       SQLite repository
  github_client.py  async GitHub REST client
  main.py           FastAPI application
  mcp_server.py     MCP tool surface
  static/           dashboard
tests/              unit and API tests
```

## License

MIT

## Текущий режим работы
Оценка строится по открытым метаданным GitHub; анализ исходного кода не выполняется (`metrics.analysis_scope=github_metadata_only`). Выборки issues/PR ограничены 3×50 и 2×50 записями, а CI — последними 20 запусками. Issues endpoint также содержит PR, которые исключаются перед анализом. `metrics.collection` фиксирует ошибки и границы выборки. Данные загружаются последовательно, поэтому это не транзакционный снимок GitHub. Пропущенные необязательные данные не считаются доказательством отсутствия CI. Неизвестная дата push не превращается в фиктивные 999 дней простоя.

HTTPX использует фиксированный api.github.com и 15-секундный timeout. Location и Link URL не запрашиваются: страницы строятся из проверенного owner/name. Переезд репозитория требует ввода актуального имени. Повторных запросов при сбое и rate limit нет; ошибки не раскрывают токен или произвольный ответ сервера. Схема SQLite не менялась: новые признаки полноты сохраняются в существующем metrics_json, старые отчёты остаются прежними снимками. История и задачи общие, поэтому внешний доступ требует авторизации; Compose привязывает порт к loopback, штатный MCP поддерживает только stdio. Заголовки issues считаются недоверенными данными и экранируются панелью.
