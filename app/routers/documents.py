from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.repositories.document_repo import (
    DocumentRepository,
    DuplicateChecksumError,
)
from app.schemas.document import DocumentResponse
from app.services.pdf_service import process_pdf_in_memory

router = APIRouter(prefix="/documents", tags=["documents"])

_repo: DocumentRepository | None = None


def get_repository() -> DocumentRepository:
    global _repo
    if _repo is None:
        _repo = DocumentRepository()
    return _repo


def reset_repository() -> None:
    """Cierra y limpia el singleton (útil en tests o shutdown)."""
    global _repo
    if _repo is not None:
        _repo.close()
        _repo = None


@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    repo: DocumentRepository = Depends(get_repository),
):
    parsed_data = await process_pdf_in_memory(file)

    new_doc = repo.create_if_checksum_absent(parsed_data)
    if new_doc is None:
        raise HTTPException(
            status_code=409,
            detail="El archivo ya existe en la base de datos.",
        )

    return new_doc


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(repo: DocumentRepository = Depends(get_repository)):
    return repo.get_all()


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    repo: DocumentRepository = Depends(get_repository),
):
    doc = repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return doc


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: str,
    file: UploadFile = File(...),
    repo: DocumentRepository = Depends(get_repository),
):
    parsed_data = await process_pdf_in_memory(file)

    try:
        updated_doc = repo.update_if_checksum_absent(doc_id, parsed_data)
    except DuplicateChecksumError as exc:
        raise HTTPException(
            status_code=409,
            detail="El archivo ya existe en la base de datos.",
        ) from exc

    if updated_doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return updated_doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    repo: DocumentRepository = Depends(get_repository),
):
    if not repo.delete(doc_id):
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return None
