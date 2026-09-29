from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import uuid

from filelock import FileLock, Timeout
from tinydb import Query, TinyDB
from tinydb.storages import Storage

from app.core.config import settings


class DuplicateChecksumError(Exception):
    pass


class RepositoryBusyError(Exception):
    pass


class DocumentRepository:
    def __init__(self, db_path: str | None = None, *, storage: type[Storage] | None = None):
        self._lock = Lock()
        self._memory_db = TinyDB(storage=storage) if storage is not None else None
        self._path = Path(db_path or settings.DB_PATH).resolve()
        self._file_lock = FileLock(str(self._path) + ".lock", timeout=settings.DB_LOCK_TIMEOUT)

    @contextmanager
    def _transaction(self) -> Iterator[TinyDB]:
        """Serializa lecturas y escrituras y abre una vista fresca entre procesos.

        Abrir TinyDB dentro del bloqueo evita caches obsoletas de consultas e IDs.
        El archivo .lock contiene coordinación, nunca el PDF recibido.
        """
        with self._lock:
            if self._memory_db is not None:
                yield self._memory_db
                return
            try:
                with self._file_lock:
                    with TinyDB(self._path, encoding="utf-8", ensure_ascii=False) as db:
                        yield db
            except Timeout as exc:
                raise RepositoryBusyError("La base de datos está ocupada.") from exc

    def get_by_checksum(self, checksum: str) -> dict | None:
        with self._transaction() as db:
            return db.get(Query().checksum == checksum)

    def create_if_checksum_absent(self, data: dict) -> dict | None:
        with self._transaction() as db:
            if db.get(Query().checksum == data["checksum"]) is not None:
                return None
            record = {
                **data,
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            db.insert(record)
            return record

    def create(self, data: dict) -> dict:
        record = self.create_if_checksum_absent(data)
        if record is None:
            raise DuplicateChecksumError
        return record

    def update_if_checksum_absent(self, doc_id: str, data: dict) -> dict | None:
        with self._transaction() as db:
            current = db.get(Query().id == doc_id)
            if current is None:
                return None
            duplicate = db.get(Query().checksum == data["checksum"])
            if duplicate is not None and duplicate["id"] != doc_id:
                raise DuplicateChecksumError
            updated = {
                **current,
                **data,
                "id": current["id"],
                "created_at": current["created_at"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            db.update(updated, Query().id == doc_id)
            return updated

    def get_all(self) -> list[dict]:
        with self._transaction() as db:
            return db.all()

    def get_by_id(self, doc_id: str) -> dict | None:
        with self._transaction() as db:
            return db.get(Query().id == doc_id)

    def delete(self, doc_id: str) -> bool:
        with self._transaction() as db:
            return bool(db.remove(Query().id == doc_id))

    def close(self) -> None:
        with self._lock:
            if self._memory_db is not None:
                self._memory_db.close()
