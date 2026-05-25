FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

COPY criba.yml .
COPY alembic.ini .
COPY alembic/ alembic/

CMD ["celery", "-A", "criba.celery_app", "worker", "-l", "info"]
