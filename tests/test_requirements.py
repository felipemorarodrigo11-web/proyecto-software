"""Regresiones de los requisitos de la etapa 1."""

import asyncio
import hashlib
import multiprocessing
import tempfile
from threading import Event
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from filelock import FileLock
from pypdf import PdfWriter
from tinydb.storages import MemoryStorage

from app.core.config import settings
from app.main import app
from app.repositories.document_repo import DocumentRepository, DuplicateChecksumError
from app.routers.documents import get_repository
from tests.pdf_factory import pdf_with_text


@pytest.fixture
def repository():
    repo = DocumentRepository(storage=MemoryStorage)
    app.dependency_overrides[get_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()
    repo.close()


@pytest.fixture
async def client(repository):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_extracts_text_from_each_page_and_exact_checksum(client):
    content = pdf_with_text("Primera pagina", "Segunda pagina")
    response = await client.post("/documents/upload", files={"file": ("texto.PDF", content)})
    assert response.status_code == 201
    result = response.json()
    assert result["text"] == "Primera pagina\nSegunda pagina"
    assert result["checksum"] == hashlib.sha256(content).hexdigest()
    assert result["size"] == len(content)


@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_large_pdf_never_spools_to_disk(client, repository, monkeypatch, method):
    def forbid_disk(*args, **kwargs):
        pytest.fail("El PDF intentó crear un archivo temporal en disco")

    content = pdf_with_text("Solo memoria", padding=2 * 1024 * 1024)
    target = "/documents/upload"
    if method == "PUT":
        original = repository.create(record("original"))
        target = f"/documents/{original['id']}"
    monkeypatch.setattr(tempfile, "TemporaryFile", forbid_disk)
    response = await client.request(method, target, files={"file": ("grande.pdf", content)})
    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json()["text"] == "Solo memoria"


async def test_limit_is_exact_and_rejection_does_not_persist(client, repository, monkeypatch):
    content = pdf_with_text("Limite")
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", len(content))
    accepted = await client.post("/documents/upload", files={"file": ("ok.pdf", content)})
    rejected = await client.post("/documents/upload", files={"file": ("grande.pdf", content + b" ")})
    assert accepted.status_code == 201
    assert rejected.status_code == 413
    assert len(repository.get_all()) == 1


async def test_duplicate_with_different_name_is_rejected(client):
    content = pdf_with_text("Igual")
    assert (await client.post("/documents/upload", files={"file": ("uno.pdf", content)})).status_code == 201
    assert (await client.post("/documents/upload", files={"file": ("dos.pdf", content)})).status_code == 409


async def test_multiple_files_are_rejected_without_persistence(client, repository):
    content = pdf_with_text("Uno")
    response = await client.post("/documents/upload", files=[
        ("file", ("uno.pdf", content)), ("file", ("dos.pdf", content)),
    ])
    assert response.status_code == 400
    assert repository.get_all() == []


async def test_encrypted_pdf_is_rejected(client, repository):
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    writer.encrypt("clave")
    buffer = BytesIO()
    writer.write(buffer)
    response = await client.post("/documents/upload", files={"file": ("cifrado.pdf", buffer.getvalue())})
    assert response.status_code == 400
    assert "cifrado" in response.json()["detail"]
    assert repository.get_all() == []


def record(checksum):
    return {"filename": "test.pdf", "text": "Texto persistido", "checksum": checksum, "size": 12}


def insert_in_process(args):
    path, checksum = args
    repo = DocumentRepository(path)
    try:
        return repo.create_if_checksum_absent(record(checksum)) is not None
    finally:
        repo.close()


def test_concurrent_processes_cannot_duplicate_or_lose_records(tmp_path):
    path = str(tmp_path / "documents.json")
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        outcomes = list(pool.map(insert_in_process, [(path, "same")] * 12))
        distinct = list(pool.map(insert_in_process, [(path, f"unique-{n}") for n in range(12)]))
    repo = DocumentRepository(path)
    try:
        assert sum(outcomes) == 1
        assert all(distinct)
        assert len(repo.get_all()) == 13
    finally:
        repo.close()


def test_independent_instances_see_latest_state_and_survive_reopen(tmp_path):
    path = str(tmp_path / "documents.json")
    first, second = DocumentRepository(path), DocumentRepository(path)
    try:
        assert first.get_by_checksum("same") is None
        saved = second.create_if_checksum_absent(record("same"))
        assert first.create_if_checksum_absent(record("same")) is None
        updated = first.update_if_checksum_absent(saved["id"], record("changed"))
        assert second.get_by_id(saved["id"])["checksum"] == "changed"
        assert updated["created_at"] == saved["created_at"]
    finally:
        first.close()
        second.close()
    reopened = DocumentRepository(path)
    try:
        assert reopened.get_by_id(saved["id"])["text"] == "Texto persistido"
        assert reopened.delete(saved["id"])
        assert reopened.get_all() == []
    finally:
        reopened.close()


def test_public_create_also_prevents_duplicates(repository):
    repository.create(record("same"))
    with pytest.raises(DuplicateChecksumError):
        repository.create(record("same"))


@pytest.mark.parametrize("content", [b"", b"texto disfrazado", b"%PDF-1.4\ncorrupto"])
async def test_invalid_pdf_does_not_persist(client, repository, content):
    response = await client.post("/documents/upload", files={"file": ("archivo.pdf", content)})
    assert response.status_code == 400
    assert repository.get_all() == []


@pytest.mark.parametrize("content_type, body, expected", [
    ("application/json", b"{}", 415),
    ("multipart/form-data", b"", 400),
    ("multipart/form-data; boundary=test", b"--test--\r\n", 422),
    ("multipart/form-data; boundary=test", b"--test\r\n", 400),
    ("multipart/form-data; boundary=test", b"invalid", 400),
])
async def test_malformed_requests_are_rejected(client, repository, content_type, body, expected):
    response = await client.post("/documents/upload", content=body, headers={"Content-Type": content_type})
    assert response.status_code == expected
    assert repository.get_all() == []


def multipart_body(content, *, closing=True, name="file"):
    header = (
        f'--boundary\r\nContent-Disposition: form-data; name="{name}"; '
        'filename="archivo.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    ).encode()
    return header + content + (b"\r\n--boundary--\r\n" if closing else b"")


async def test_truncated_pdf_upload_does_not_persist(client, repository):
    response = await client.post(
        "/documents/upload", content=multipart_body(pdf_with_text("Hola"), closing=False),
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 400
    assert repository.get_all() == []


async def test_streaming_limits_stop_reading_without_content_length(client, repository, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)
    chunks_read = 0

    async def oversized_body():
        nonlocal chunks_read
        yield multipart_body(b"", closing=False)
        for _ in range(10):
            chunks_read += 1
            yield b"x" * 512
        yield b"\r\n--boundary--\r\n"

    response = await client.post(
        "/documents/upload", content=oversized_body(),
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 413
    assert chunks_read <= 3
    assert repository.get_all() == []


async def test_multipart_headers_and_boundaries_can_arrive_in_small_chunks(client):
    body = multipart_body(pdf_with_text("Fragmentado"))

    async def fragments():
        for start in range(0, len(body), 7):
            yield body[start:start + 7]

    response = await client.post(
        "/documents/upload", content=fragments(),
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 201
    assert response.json()["text"] == "Fragmentado"


async def test_oversized_upload_never_creates_a_temporary_file(client, repository, monkeypatch):
    def forbid_disk(*args, **kwargs):
        pytest.fail("Un PDF rechazado intentó persistirse temporalmente")

    monkeypatch.setattr(tempfile, "TemporaryFile", forbid_disk)
    response = await client.post(
        "/documents/upload", files={"file": ("grande.pdf", b"%PDF-" + b"x" * settings.MAX_FILE_SIZE)},
    )
    assert response.status_code == 413
    assert repository.get_all() == []


async def test_failed_update_leaves_original_intact(client):
    first = (await client.post("/documents/upload", files={"file": ("uno.pdf", pdf_with_text("Uno"))})).json()
    other = pdf_with_text("Dos")
    await client.post("/documents/upload", files={"file": ("dos.pdf", other)})
    url = f"/documents/{first['id']}"
    conflict = await client.put(url, files={"file": ("otro.pdf", other)})
    invalid = await client.put(url, files={"file": ("invalido.pdf", b"no pdf")})
    assert conflict.status_code == 409
    assert invalid.status_code == 400
    assert (await client.get(url)).json() == first
    same = await client.put(url, files={"file": ("renombrado.pdf", pdf_with_text("Uno"))})
    assert same.status_code == 200
    assert same.json()["checksum"] == first["checksum"]


async def test_parallel_requests_only_create_one_document(client, repository):
    content = pdf_with_text("Concurrente")
    results = await asyncio.gather(*(
        client.post("/documents/upload", files={"file": (f"{i}.pdf", content)})
        for i in range(12)
    ))
    assert sorted(response.status_code for response in results) == [201] + [409] * 11
    assert len(repository.get_all()) == 1


async def test_pdf_extraction_does_not_block_health(client, monkeypatch):
    from app.services import pdf_service

    started, release = Event(), Event()
    original = pdf_service._extract_document

    def slow_extraction(*args):
        started.set()
        assert release.wait(5), "La extracción bloqueó el bucle de solicitudes"
        return original(*args)

    monkeypatch.setattr(pdf_service, "_extract_document", slow_extraction)
    pending = asyncio.create_task(client.post(
        "/documents/upload", files={"file": ("lento.pdf", pdf_with_text("Lento"))},
    ))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        health = await asyncio.wait_for(client.get("/health"), timeout=1)
        assert health.status_code == 200
        assert not pending.done()
    finally:
        release.set()
        response = await pending
    assert response.status_code == 201


async def test_database_lock_timeout_returns_retryable_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_LOCK_TIMEOUT", 0.05)
    path = str(tmp_path / "busy.json")
    repo = DocumentRepository(path)
    app.dependency_overrides[get_repository] = lambda: repo
    try:
        with FileLock(path + ".lock"):
            response = await client.get("/documents/")
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "1"
        assert (await client.get("/documents/")).status_code == 200
    finally:
        repo.close()


def test_swagger_keeps_pdf_file_selector():
    schema = app.openapi()
    for path, method in [("/documents/upload", "post"), ("/documents/{doc_id}", "put")]:
        body = schema["paths"][path][method]["requestBody"]
        upload = body["content"]["multipart/form-data"]["schema"]
        assert upload["required"] == ["file"]
        assert upload["properties"]["file"]["format"] == "binary"


@pytest.mark.parametrize("values", [
    {"MAX_FILE_SIZE": 0}, {"MAX_FILE_SIZE": -1}, {"DB_PATH": ""}, {"DB_LOCK_TIMEOUT": 0},
])
def test_invalid_settings_fail_at_startup(values):
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
