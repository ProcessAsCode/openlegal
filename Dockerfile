FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && apt-get clean \
 && find /var/lib/apt/lists -mindepth 1 -delete

# pyproject.toml + src must be present for the src-layout editable install.
# Layer order: dependencies-defining files first; alembic/uapf/docker after
# so they can change without invalidating the (slow) pip layer.
COPY pyproject.toml /app/
COPY src            /app/src
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY alembic.ini          /app/alembic.ini
COPY alembic              /app/alembic
COPY uapf-packages        /app/uapf-packages
COPY seed                 /app/seed
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "openlegal.main:app", "--host", "0.0.0.0", "--port", "8002"]
