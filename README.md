# Quorum — GitHub Metadata Analyzer

Turn GitHub repository metadata into a repeatable maintenance report.


![Desktop interface](docs/desktop.png)

<img src="docs/mobile.png" width="320" alt="Mobile interface">

[Short interaction recording](docs/demo.gif)

## Implemented

- Fetch repository metadata, open issues, pull requests and workflow runs.
- Persist reports and prioritize suggested maintenance actions.
- Responsive dashboard, REST endpoints and MCP tools.

## Stack and architecture

Python, FastAPI, HTTPX, SQLite, GitHub REST API and MCP.

## Technical mechanisms and security

- A fixed api.github.com client is separate from the scoring rules and replaced by fixtures in tests.
- Repository references are validated and fetched lists are bounded. Scores are deterministic metadata heuristics; the tool does not inspect source-code correctness.

## Local setup

Python 3.12.14 (see `.python-version`). Activate the virtual environment before the remaining commands.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -c requirements-lock.txt -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## Configuration

Use [.env.example](.env.example) for supported configuration and keep secrets outside Git. See [configuration details](docs/TECHNICAL.md) for loading settings and optional services.

## Database and upgrades

The SQLite schema initializes on startup. Database/capture paths are configurable; keep persistent data outside temporary build directories.

## Verification

```bash
python -m pytest -q
python tests/check_contract.py
python tests/check_upgrade.py
python -m pip check
python -m ruff check .
```

Existing pytest, Ruff, OpenAPI and previous-version upgrade checks; no requests to arbitrary repositories are required for tests.

CI installs locked dependencies and runs the configured checks; documentation checks also validate local links/images. Python dependency auditing uses `pip-audit --disable-pip --no-deps --strict -r requirements-lock.txt`. A passing scanner only reports known advisories at the time of the run.

## Limits and next steps

- A report is not a security/code audit or evidence of production quality. API permissions, rate limits and truncated lists affect observations.
- Some optional API failures use empty fallback results. Expose missing-data provenance before interpreting absence as health; no exploit or incorrect score was proven here.
- Local tool without public multi-tenant authentication. Keep GitHub tokens outside version control.

## Further documentation

[Audit findings and follow-up](docs/AUDIT_2026_10.md) · [Technical reference](docs/TECHNICAL.md) · [Change history](CHANGELOG.md)

[API request/response example](docs/API_EXAMPLE.md)
