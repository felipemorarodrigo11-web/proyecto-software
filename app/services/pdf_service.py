import hashlib
from io import BytesIO
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from app.core.config import settings

async def process_pdf_in_memory(file: UploadFile) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un documento PDF.",
        )

    content = await file.read()

    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="El archivo es demasiado grande. El límite es 5 MB.",
        )

    if not content.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un documento PDF.",
        )

    reader = PdfReader(BytesIO(content))
    text = "".join(page.extract_text() or "" for page in reader.pages).strip()

    checksum = hashlib.sha256(content).hexdigest()

    return {
        "filename": file.filename,
        "text": text,
        "checksum": checksum,
        "size": len(content),
    }