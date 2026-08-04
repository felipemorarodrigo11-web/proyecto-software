from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from app.services.pdf_service import process_pdf_in_memory
from app.repositories.document_repo import DocumentRepository

router = APIRouter(prefix="/documents", tags=["documents"])

def get_repository() -> DocumentRepository:
    return DocumentRepository()

@router.post("/upload", status_code=201)
async def upload_pdf(
    file: UploadFile = File(...),
    repo: DocumentRepository = Depends(get_repository)
):
    parsed_data = await process_pdf_in_memory(file)

    if repo.get_by_checksum(parsed_data["checksum"]):
        raise HTTPException(
            status_code=409,
            detail="El archivo ya existe en la base de datos.",
        )

    new_doc = repo.create(parsed_data)
    return new_doc

@router.get("/")
async def list_documents(repo: DocumentRepository = Depends(get_repository)):
    return repo.get_all()

@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    repo: DocumentRepository = Depends(get_repository)
):
    doc = repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return doc

@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    repo: DocumentRepository = Depends(get_repository)
):
    if not repo.delete(doc_id):
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return None