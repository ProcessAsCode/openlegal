#!/bin/sh
# OpenLegal container startup:
#  1. Wait for Postgres to accept connections.
#  2. alembic upgrade head (idempotent).
#  3. Seed demo data if empty (skip with OPENLEGAL_SKIP_SEED=true).
#  4. exec the configured CMD (uvicorn).
set -e

echo "[entrypoint] waiting for database..."
python - <<'PYEOF'
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

url = os.environ.get(
    "OPENLEGAL_DB_URL",
    "postgresql+asyncpg://openlegal:openlegal@db:5432/openlegal",
)
engine = create_async_engine(url)

async def wait():
    for i in range(30):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print(f"[entrypoint] db up after ~{i}s")
            return
        except Exception as exc:
            if i == 29:
                print(f"[entrypoint] db never came up: {exc}", file=sys.stderr)
                sys.exit(1)
            await asyncio.sleep(1)

asyncio.run(wait())
PYEOF

echo "[entrypoint] running alembic upgrade head..."
alembic upgrade head

if [ "${OPENLEGAL_SKIP_SEED:-false}" = "true" ]; then
    echo "[entrypoint] OPENLEGAL_SKIP_SEED=true; not seeding"
else
    echo "[entrypoint] seeding demo data (if empty)..."
    python -m openlegal.cli seed || echo "[entrypoint] seed reported an issue but continuing"
fi

echo "[entrypoint] launching: $*"
exec "$@"
