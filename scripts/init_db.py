from app.db.session import Base, engine
import app.db.base  # noqa: F401  Ensures models are registered with SQLAlchemy metadata.


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database schema created.")
