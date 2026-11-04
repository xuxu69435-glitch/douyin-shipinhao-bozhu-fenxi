"""SQLite persistence owned by the local sidecar."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_session_factory(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "analyst.sqlite3"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False}, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine
