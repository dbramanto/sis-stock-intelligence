from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BACKEND_FILESYSTEM = "filesystem"
BACKEND_CLOUD = "cloud"


class StorageUnavailable(RuntimeError):
    pass


def storage_backend() -> str:
    """Return active persistence backend.

    Local/default mode uses filesystem. Cloud mode is activated explicitly with
    SIS_STORAGE_BACKEND=cloud and requires an external adapter implementation.
    """
    raw = os.environ.get("SIS_STORAGE_BACKEND", "").strip().lower()
    if not raw:
        return BACKEND_FILESYSTEM
    if raw not in {BACKEND_FILESYSTEM, BACKEND_CLOUD}:
        raise StorageUnavailable(f"UNSUPPORTED_STORAGE_BACKEND:{raw}")
    return raw


def _cloud_configured() -> bool:
    return bool(os.environ.get("SIS_CLOUD_STORAGE_URL", "").strip() and os.environ.get("SIS_CLOUD_STORAGE_TOKEN", "").strip())


def ensure_backend_ready() -> None:
    backend = storage_backend()
    if backend == BACKEND_CLOUD and not _cloud_configured():
        raise StorageUnavailable("CLOUD_STORAGE_NOT_CONFIGURED")


class JsonStore:
    """Minimal persistence abstraction for JSON documents.

    Filesystem mode is production for local SIS. Cloud mode is intentionally
    fail-closed until an external durable provider is configured and wired.
    """

    def __init__(self, root: str | Path):
        ensure_backend_ready()
        self.backend = storage_backend()
        self.root = Path(root)

    def _path(self, namespace: str, key: str) -> Path:
        if not key or "/" in key or "\\" in key or ".." in key:
            raise ValueError("INVALID_STORAGE_KEY")
        path = self.root / namespace / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, namespace: str, key: str, payload: dict[str, Any], *, overwrite: bool = True) -> None:
        if self.backend == BACKEND_CLOUD:
            raise StorageUnavailable("CLOUD_STORAGE_ADAPTER_NOT_WIRED")
        path = self._path(namespace, key)
        if path.exists() and not overwrite:
            raise FileExistsError(str(path))
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def get(self, namespace: str, key: str) -> dict[str, Any]:
        if self.backend == BACKEND_CLOUD:
            raise StorageUnavailable("CLOUD_STORAGE_ADAPTER_NOT_WIRED")
        return json.loads(self._path(namespace, key).read_text(encoding="utf-8"))

    def exists(self, namespace: str, key: str) -> bool:
        if self.backend == BACKEND_CLOUD:
            raise StorageUnavailable("CLOUD_STORAGE_ADAPTER_NOT_WIRED")
        return self._path(namespace, key).is_file()

    def list(self, namespace: str) -> list[dict[str, Any]]:
        if self.backend == BACKEND_CLOUD:
            raise StorageUnavailable("CLOUD_STORAGE_ADAPTER_NOT_WIRED")
        root = self.root / namespace
        if not root.exists():
            return []
        out = []
        for path in sorted(root.glob("*.json"), reverse=True):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out
