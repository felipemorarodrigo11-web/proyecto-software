"""Medición local de cargas ASGI; usa una base aislada, nunca DB_PATH."""

import argparse
import asyncio
import json
import math
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.repositories.document_repo import DocumentRepository
from app.routers.documents import get_repository
from tests.pdf_factory import pdf_with_text


async def measure(requests: int, concurrency: int, pages: int) -> dict:
    # Se excluye de las latencias la generación de archivos del cliente.
    documents = [
        pdf_with_text(*(f"Documento {n}, pagina {p}" for p in range(pages)))
        for n in range(requests)
    ]
    gate = asyncio.Semaphore(concurrency)
    with TemporaryDirectory(prefix="pdf-benchmark-") as folder:
        repo = DocumentRepository(str(Path(folder) / "benchmark.json"))
        previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_repository] = lambda: repo
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://benchmark") as client:
                await client.get("/health")

                async def upload(index, content):
                    async with gate:
                        started = perf_counter()
                        response = await client.post(
                            "/documents/upload", files={"file": (f"{index}.pdf", content)},
                        )
                        elapsed = perf_counter() - started
                        if response.status_code != 201:
                            raise RuntimeError(f"Carga {index}: {response.status_code} {response.text}")
                        return elapsed

                started = perf_counter()
                latencies = await asyncio.gather(*(upload(i, doc) for i, doc in enumerate(documents)))
                elapsed = perf_counter() - started
                persisted = len(repo.get_all())
                if persisted != requests:
                    raise RuntimeError(f"Se persistieron {persisted} documentos de {requests}")
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)
            repo.close()
    return {
        "transport": "ASGI local, sin red; TinyDB en disco",
        "requests": requests,
        "concurrency": concurrency,
        "pages_per_pdf": pages,
        "persisted": persisted,
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(requests / elapsed, 2),
        "p50_ms": round(median(latencies) * 1000, 2),
        "p95_ms": round(sorted(latencies)[math.ceil(0.95 * requests) - 1] * 1000, 2),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--pages", type=int, default=3)
    args = parser.parse_args()
    if min(args.requests, args.concurrency, args.pages) < 1:
        parser.error("Los parámetros deben ser mayores que cero")
    print(json.dumps(asyncio.run(measure(args.requests, args.concurrency, args.pages)), indent=2))
