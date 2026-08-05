import hashlib
from io import BytesIO

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import settings

_CHUNK_SIZE = 64 * 1024


def _max_size_label() -> str:
    mb = settings.MAX_FILE_SIZE / (1024 * 1024)
    if mb == int(mb):
        return f"{int(mb)} MB"
    return f"{mb:.1f} MB"


async def _read_with_size_limit(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=(
                    "El archivo es demasiado grande. "
                    f"El límite es {_max_size_label()}."
                ),
            )
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

    if not content.startswith(b"%PDF"):
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
        text = "".join(page.extract_text() or "" for page in reader.pages).strip()
    except HTTPException:
        raise
    except (PdfReadError, Exception) as exc:
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
