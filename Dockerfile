FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QUORUM_DATABASE_PATH=/data/quorum.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY requirements-lock.txt ./
COPY app ./app

RUN python -m pip install --no-cache-dir -c requirements-lock.txt .

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

