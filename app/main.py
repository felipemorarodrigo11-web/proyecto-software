from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(documents.router)
