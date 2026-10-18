"""
SQLite database setup using SQLModel.

The database lives at /data/db/app.sqlite so it shares the existing
Docker volume layout used by the rest of the app.

FTS5 virtual tables and triggers are created via raw SQL in
migrations/001_init.sql because SQLModel doesn't model FTS natively.
"""
from __future__ import annotations

import os
from pathlib import Path
from contextlib import contextmanager

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

DB_PATH = Path(os.getenv("APP_DB_PATH", "/data/db/app.sqlite"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# check_same_thread=False because FastAPI may hit the connection from
# different threads (background sync, request handlers).
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)

# expire_on_commit=False so SQLModel objects remain usable after the
# session closes — important for our auth flow which returns User
# objects from session_scope contexts.
_SessionFactory = sessionmaker(
    bind=engine, class_=Session, expire_on_commit=False, autoflush=False
)


@event.listens_for(engine, "connect")
def _enable_sqlite_pragmas(dbapi_conn, _):
    """WAL + foreign keys + reasonable sync for a single-host POC.

    Bound to THIS engine, not the global Engine class: a listener on Engine
    fires for every engine in the process, so an unrelated Postgres pool
    would be sent `PRAGMA` and fail.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def init_db() -> None:
    """Create all SQLModel tables and run raw-SQL migrations (FTS5)."""
    # Import the models module to register all SQLModel tables on metadata.
    import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _run_raw_migrations()


def _run_raw_migrations() -> None:
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    if not migrations_dir.exists():
        return
    with engine.begin() as conn:
        # Track applied migrations in a tiny table.
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS _migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        applied = {
            row[0]
            for row in conn.exec_driver_sql("SELECT name FROM _migrations").fetchall()
        }
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            if sql_file.name in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            for stmt in _split_sql(sql):
                if not stmt.strip():
                    continue
                try:
                    conn.exec_driver_sql(stmt)
                except Exception as e:
                    msg = str(e).lower()
                    # SQLite raises "duplicate column name" when an
                    # ADD COLUMN target already exists. That's a
                    # successful no-op for idempotency, not an error.
                    if "duplicate column" in msg or "already exists" in msg:
                        continue
                    raise
            conn.exec_driver_sql(
                "INSERT INTO _migrations(name) VALUES (?)", (sql_file.name,)
            )


def _split_sql(sql: str) -> list[str]:
    """Naive split on `;` that respects multi-line trigger bodies wrapped in BEGIN..END."""
    out, buf, in_trigger = [], [], False
    for line in sql.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("CREATE TRIGGER"):
            in_trigger = True
        buf.append(line)
        if in_trigger and stripped == "END;":
            out.append("\n".join(buf))
            buf = []
            in_trigger = False
        elif not in_trigger and line.rstrip().endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out


@contextmanager
def session_scope():
    """Context manager for one-shot DB sessions outside FastAPI deps."""
    s = _SessionFactory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    """FastAPI dependency."""
    s = _SessionFactory()
    try:
        yield s
    finally:
        s.close()


# Aliases used by the standalone service (api.py, ui_user/tenant.py).
get_session_dep = get_session


def get_session_ctx():
    return session_scope()
