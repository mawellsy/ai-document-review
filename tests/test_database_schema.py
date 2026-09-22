from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import app.db.base  # noqa: F401
from app.core.config import get_settings
from app.db.session import Base, build_engine


EXPECTED_TABLES = {"documents", "extractions", "line_items", "reviews"}


def test_expected_tables_are_created_from_metadata() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_sqlite_engine_enables_foreign_keys() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


def test_alembic_upgrade_creates_current_schema(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migration-test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "testing")
    get_settings.cache_clear()

    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))

    try:
        command.upgrade(config, "head")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        assert EXPECTED_TABLES.issubset(tables)
        assert "alembic_version" in tables

        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        assert revision == "0001_initial_schema"

        command.downgrade(config, "base")
        remaining_tables = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES.isdisjoint(remaining_tables)
    finally:
        get_settings.cache_clear()
