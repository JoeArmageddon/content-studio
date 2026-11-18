"""
SQLAlchemy engine/session setup.

Models live in app.core.models and must be imported before init_db() runs
so Base.metadata knows about them (same pattern as most FastAPI+SQLAlchemy
starters — see main.py's startup hook).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLAlchemy's bare "postgresql://" scheme defaults to the psycopg2 dialect,
# but we install psycopg3 (psycopg[binary], requirements.txt) — normalize
# so DATABASE_URL doesn't have to get the exact dialect suffix right in
# every place it's set (Supabase's own connection-string UI gives the bare
# scheme). Caught when first testing the Supabase connection live.
_database_url = settings.database_url
if _database_url.startswith("postgresql://") or _database_url.startswith("postgres://"):
    _database_url = "postgresql+psycopg://" + _database_url.split("://", 1)[1]

# Supabase's pooled connection (port 6543) is pgbouncer in transaction mode,
# which can't keep server-side prepared statements between queries — psycopg3
# auto-prepares repeated queries by default, which then fails intermittently
# with "prepared statement _pg3_0 already exists" (hit while authorizing
# channels). prepare_threshold=None turns auto-preparing off.
_connect_args = {"check_same_thread": False} if _is_sqlite else {"prepare_threshold": None}

engine = create_engine(_database_url, connect_args=_connect_args)

if _is_sqlite:
    # WAL mode lets readers and a writer proceed concurrently instead of
    # blocking on SQLite's default file lock — matters once 10 channels'
    # scheduled jobs can run close together (see scheduler.py's per-channel
    # offset, added the same milestone this was caught).
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns():
    """create_all() never alters existing tables, so columns added to a model
    after the table was first created (live stats etc.) are added here —
    idempotent, works on both Postgres and SQLite."""
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateColumn

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    ddl = CreateColumn(col).compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
                    print(f"[db] added column {table.name}.{col.name}")


def init_db():
    from app.core import models  # noqa: F401 — registers tables on Base
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
