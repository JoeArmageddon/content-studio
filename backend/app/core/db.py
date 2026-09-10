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

engine = create_engine(
    _database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

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


def init_db():
    from app.core import models  # noqa: F401 — registers tables on Base
    Base.metadata.create_all(bind=engine)
