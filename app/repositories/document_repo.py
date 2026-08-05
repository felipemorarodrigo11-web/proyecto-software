from datetime import datetime, timezone
from threading import Lock
from typing import List, Optional
import uuid

from tinydb import Query, TinyDB
from tinydb.storages import Storage

from app.core.config import settings


class DocumentRepository:
    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        storage: Optional[type[Storage]] = None,
    ):
        if storage is not None:
            self.db = TinyDB(storage=storage)
        else:
            path = db_path or settings.DB_PATH
            self.db = TinyDB(path)
        self.Doc = Query()
        self._lock = Lock()

    def get_by_checksum(self, checksum: str) -> Optional[dict]:
        results = self.db.search(self.Doc.checksum == checksum)
        return results[0] if results else None

    def create_if_checksum_absent(self, data: dict) -> Optional[dict]:
        """Inserta el documento solo si el checksum no existe. Evita duplicados concurrentes."""
        with self._lock:
            if self.get_by_checksum(data["checksum"]):
                return None
            return self.create(data)

    def create(self, data: dict) -> dict:
        doc_id = str(uuid.uuid4())
        record = {
            "id": doc_id,
            **data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.insert(record)
        return record

    def get_all(self) -> List[dict]:
        return self.db.all()

    def get_by_id(self, doc_id: str) -> Optional[dict]:
        results = self.db.search(self.Doc.id == doc_id)
        return results[0] if results else None

    def delete(self, doc_id: str) -> bool:
        removed = self.db.remove(self.Doc.id == doc_id)
        return len(removed) > 0

    def close(self) -> None:
        self.db.close()
