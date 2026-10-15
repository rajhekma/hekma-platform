import json
import aiofiles
from pathlib import Path
from datetime import datetime
from typing import Any
import uuid

from api.storage.base import TokenMapping, PIIPolicy, AuditEntry


class JsonPersistenceMixin:
    def __init__(self, data_dir: Path = Path("./data"), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._persist_enabled = True
        self._load()

    def _get_path(self, name: str) -> Path:
        return self.data_dir / f"{name}.json"

    def _serialize(self, obj: Any) -> Any:
        if hasattr(obj, '__dataclass_fields__'):
            return {k: self._serialize(v) for k, v in obj.__dict__.items()}
        elif hasattr(obj, 'model_dump') and callable(obj.model_dump):
            return {k: self._serialize(v) for k, v in obj.model_dump().items()}
        elif hasattr(obj, 'dict') and callable(obj.dict):
            return {k: self._serialize(v) for k, v in obj.dict().items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize(v) for v in obj]
        elif isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, uuid.UUID):
            return str(obj)
        return obj

    def _deserialize_token(self, data: dict) -> TokenMapping:
        data['id'] = uuid.UUID(data['id'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('expires_at'):
            data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        if data.get('restored_at'):
            data['restored_at'] = datetime.fromisoformat(data['restored_at'])
        return TokenMapping(**data)

    def _deserialize_policy(self, data: dict) -> PIIPolicy:
        return PIIPolicy(**data)

    def _deserialize_audit(self, data: dict) -> AuditEntry:
        data['id'] = uuid.UUID(data['id'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return AuditEntry(**data)

    def _load(self):
        pass

    async def _persist(self, name: str, data: Any):
        if not self._persist_enabled:
            return
        path = self._get_path(name)
        async with aiofiles.open(path, 'w') as f:
            await f.write(json.dumps(self._serialize(data), indent=2))