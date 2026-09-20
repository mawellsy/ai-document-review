from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"synthetic-image-content"


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        upload_dir=tmp_path / "uploads",
        max_upload_mb=1,
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_upload_get_and_list_document(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/documents",
        files={"file": ("invoice.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 201
    uploaded = response.json()
    assert uploaded["original_filename"] == "invoice.png"
    assert uploaded["content_type"] == "image/png"
    assert uploaded["file_size_bytes"] == len(PNG_BYTES)
    assert uploaded["processing_status"] == "uploaded"

    stored_files = list((tmp_path / "uploads").iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].name == f'{uploaded["id"]}.png'

    get_response = client.get(f'/documents/{uploaded["id"]}')
    assert get_response.status_code == 200
    assert get_response.json()["id"] == uploaded["id"]

    list_response = client.get("/documents")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [uploaded["id"]]


def test_client_path_is_removed_from_original_filename(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("../../private/invoice.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 201
    assert response.json()["original_filename"] == "invoice.png"


def test_rejects_unsupported_file(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"not an invoice", "text/plain")},
    )

    assert response.status_code == 415


def test_rejects_extension_content_mismatch(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("invoice.pdf", PNG_BYTES, "application/pdf")},
    )

    assert response.status_code == 415
    assert "extension" in response.json()["detail"].lower()


def test_rejects_file_over_size_limit(client: TestClient) -> None:
    oversized_png = b"\x89PNG\r\n\x1a\n" + b"x" * (1024 * 1024)

    response = client.post(
        "/documents",
        files={"file": ("large.png", oversized_png, "image/png")},
    )

    assert response.status_code == 413


def test_missing_document_returns_404(client: TestClient) -> None:
    response = client.get("/documents/does-not-exist")

    assert response.status_code == 404


def test_rejects_empty_file(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 415
    assert "empty" in response.json()["detail"].lower()


def test_rejects_mime_content_mismatch(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("invoice.png", PNG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 415
    assert "content type" in response.json()["detail"].lower()
