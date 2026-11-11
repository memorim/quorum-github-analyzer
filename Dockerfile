FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    QUORUM_DATABASE_PATH=/data/quorum.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY requirements-lock.txt ./
COPY app ./app

RUN python -m pip install --no-cache-dir -c requirements-lock.txt .
RUN groupadd --system quorum && useradd --system --gid quorum --create-home quorum \
    && mkdir -p /data && chown quorum:quorum /data
USER quorum

EXPOSE 8010

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8010}"]

