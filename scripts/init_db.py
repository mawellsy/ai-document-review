from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database() -> None:
    """Bring the configured database schema to the latest Alembic revision."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_database()
    print("Database schema upgraded to the latest migration.")
