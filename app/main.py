from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.repositories.document_repo import RepositoryBusyError
from app.routers import documents
from app.routers.documents import reset_repository


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    reset_repository()


app = FastAPI(
    title="Proyecto Desarrollo de Software 2026",
    lifespan=lifespan,
)


@app.exception_handler(RepositoryBusyError)
async def repository_busy(_request, _exc):
    return JSONResponse(
        status_code=503,
        content={"detail": "La base de datos está ocupada. Reintentá la operación."},
        headers={"Retry-After": "1"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(documents.router)
