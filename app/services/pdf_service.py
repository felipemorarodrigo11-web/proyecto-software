import hashlib
from io import BytesIO

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.upload_service import file_too_large

_CHUNK_SIZE = 64 * 1024


async def _read_with_size_limit(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.MAX_FILE_SIZE:
            raise file_too_large()
        chunks.append(chunk)

    return b"".join(chunks)


async def process_pdf_in_memory(file: UploadFile) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un documento PDF.",
        )

    content = await _read_with_size_limit(file)

    return await run_in_threadpool(_extract_document, filename, content)


def _extract_document(filename: str, content: bytes) -> dict:
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un documento PDF.",
        )

    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise HTTPException(
                status_code=400,
                detail="El PDF está cifrado y no se puede procesar.",
            )
        text = "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    except HTTPException:
        raise
    except (PyPdfError, ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise HTTPException(
            status_code=400,
            detail="El archivo PDF es inválido o está corrupto.",
        ) from exc

    checksum = hashlib.sha256(content).hexdigest()

    return {
        "filename": filename,
        "text": text,
        "checksum": checksum,
        "size": len(content),
    }
