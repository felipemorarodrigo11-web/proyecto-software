from tinydb import TinyDB, Query
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from app.core.config import settings

class DocumentRepository:
    def __init__(self, db_path: str = None):
        path = db_path or settings.DB_PATH
        self.db = TinyDB(path)
        self.Doc = Query()

    def get_by_checksum(self, checksum: str) -> Optional[dict]:
        results = self.db.search(self.Doc.checksum == checksum)
        return results[0] if results else None

    def create(self, data: dict) -> dict:
        doc_id = str(uuid.uuid4())
        record = {
            "id": doc_id,
            **data,
            "created_at": datetime.now(timezone.utc).isoformat()
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