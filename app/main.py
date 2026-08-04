from fastapi import FastAPI
from app.routers import documents

app = FastAPI(title="Proyecto Desarrollo de Software 2026")

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(documents.router)