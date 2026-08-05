from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter
from tinydb.storages import MemoryStorage

from app.main import app
from app.repositories.document_repo import DocumentRepository
from app.routers.documents import get_repository
from app.services.pdf_service import process_pdf_in_memory


@pytest.fixture(autouse=True)
def override_repo_dependency():
    test_repo = DocumentRepository(storage=MemoryStorage)
    app.dependency_overrides[get_repository] = lambda: test_repo
    yield test_repo
    app.dependency_overrides.clear()
    test_repo.close()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def small_valid_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    buffer = BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def second_valid_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    buffer = BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.read()


@pytest.mark.asyncio
class TestPdfService:
    async def test_process_pdf_with_none_filename_raises_400(self):
        upload = MagicMock()
        upload.filename = None
        upload.read = AsyncMock(return_value=b"")

        with pytest.raises(HTTPException) as exc_info:
            await process_pdf_in_memory(upload)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "El archivo debe ser un documento PDF."


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_returns_200_and_ok(self, client):
        async with client as ac:
            response = await ac.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
class TestUploadAndCRUDEndpoints:
    async def test_upload_txt_file_returns_400(self, client):
        async with client as ac:
            response = await ac.post(
                "/documents/upload",
                files={"file": ("documento.txt", b"contenido de prueba", "text/plain")},
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "El archivo debe ser un documento PDF."

    async def test_upload_pdf_exceeding_limit_returns_413(self, client):
        oversized = b"%PDF" + b"x" * (5 * 1024 * 1024 + 1)
        async with client as ac:
            response = await ac.post(
                "/documents/upload",
                files={"file": ("grande.pdf", oversized, "application/pdf")},
            )
        assert response.status_code == 413
        assert "demasiado grande" in response.json()["detail"]
        assert "5 MB" in response.json()["detail"]

    async def test_upload_corrupt_pdf_returns_400(self, client):
        async with client as ac:
            response = await ac.post(
                "/documents/upload",
                files={
                    "file": (
                        "corrupto.pdf",
                        b"%PDF-1.4\nesto no es un pdf valido",
                        "application/pdf",
                    )
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "El archivo PDF es inválido o está corrupto."

    async def test_upload_valid_pdf_returns_201(self, client, small_valid_pdf):
        async with client as ac:
            response = await ac.post(
                "/documents/upload",
                files={"file": ("documento.pdf", small_valid_pdf, "application/pdf")},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "documento.pdf"
        assert "checksum" in data
        assert "id" in data
        assert "created_at" in data

    async def test_upload_duplicate_pdf_returns_409(self, client, small_valid_pdf):
        async with client as ac:
            await ac.post(
                "/documents/upload",
                files={"file": ("documento.pdf", small_valid_pdf, "application/pdf")},
            )
            response = await ac.post(
                "/documents/upload",
                files={"file": ("documento.pdf", small_valid_pdf, "application/pdf")},
            )
        assert response.status_code == 409
        assert response.json()["detail"] == "El archivo ya existe en la base de datos."

    async def test_update_document_replaces_pdf(
        self,
        client,
        small_valid_pdf,
        second_valid_pdf,
    ):
        async with client as ac:
            upload_res = await ac.post(
                "/documents/upload",
                files={"file": ("original.pdf", small_valid_pdf, "application/pdf")},
            )
            original = upload_res.json()

            update_res = await ac.put(
                f"/documents/{original['id']}",
                files={"file": ("actualizado.pdf", second_valid_pdf, "application/pdf")},
            )

        assert update_res.status_code == 200
        updated = update_res.json()
        assert updated["id"] == original["id"]
        assert updated["created_at"] == original["created_at"]
        assert updated["filename"] == "actualizado.pdf"
        assert updated["checksum"] != original["checksum"]
        assert updated["updated_at"] is not None

    async def test_update_with_duplicate_pdf_returns_409(
        self,
        client,
        small_valid_pdf,
        second_valid_pdf,
    ):
        async with client as ac:
            first = await ac.post(
                "/documents/upload",
                files={"file": ("primero.pdf", small_valid_pdf, "application/pdf")},
            )
            await ac.post(
                "/documents/upload",
                files={"file": ("segundo.pdf", second_valid_pdf, "application/pdf")},
            )
            response = await ac.put(
                f"/documents/{first.json()['id']}",
                files={"file": ("duplicado.pdf", second_valid_pdf, "application/pdf")},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == "El archivo ya existe en la base de datos."

    async def test_update_missing_document_returns_404(self, client, small_valid_pdf):
        async with client as ac:
            response = await ac.put(
                "/documents/id-inexistente",
                files={"file": ("documento.pdf", small_valid_pdf, "application/pdf")},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Documento no encontrado."

    async def test_crud_operations(self, client, second_valid_pdf):
        async with client as ac:
            upload_res = await ac.post(
                "/documents/upload",
                files={"file": ("documento2.pdf", second_valid_pdf, "application/pdf")},
            )
            assert upload_res.status_code == 201
            doc_id = upload_res.json()["id"]

            list_res = await ac.get("/documents/")
            assert list_res.status_code == 200
            assert len(list_res.json()) == 1

            get_res = await ac.get(f"/documents/{doc_id}")
            assert get_res.status_code == 200
            assert get_res.json()["id"] == doc_id

            del_res = await ac.delete(f"/documents/{doc_id}")
            assert del_res.status_code == 204

            get_after_del = await ac.get(f"/documents/{doc_id}")
            assert get_after_del.status_code == 404
