import tempfile
import uuid
from pathlib import Path

_store_dir = Path(tempfile.mkdtemp(prefix="plotter-studio-files-"))
_registry: dict[str, dict] = {}


def store_file(data: bytes, filename: str, content_type: str) -> str:
    file_id = uuid.uuid4().hex
    dest = _store_dir / file_id
    dest.write_bytes(data)
    _registry[file_id] = {
        "path": dest,
        "filename": filename,
        "content_type": content_type,
    }
    return file_id


def get_file(file_id: str) -> tuple[Path, str, str] | None:
    entry = _registry.get(file_id)
    if entry is None:
        return None
    return entry["path"], entry["filename"], entry["content_type"]
