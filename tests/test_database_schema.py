from sqlalchemy import create_engine, inspect

from app.db.session import Base
import app.db.base  # noqa: F401


def test_expected_tables_are_created() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    tables = set(inspect(engine).get_table_names())
    assert {"documents", "extractions", "line_items", "reviews"}.issubset(tables)
