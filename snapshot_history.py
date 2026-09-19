from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

SNAPSHOT_SCHEMA_VERSION = "1.0"


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotRef:
    trading_date: str
    revision: int
    snapshot_id: str
    status: str
    content_hash: str
    created_at: str
    source: str
    gate_state: str


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict(orient="records")
        except TypeError:
            return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _normalize_trading_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except Exception as exc:
        raise SnapshotError("trading_date must be YYYY-MM-DD or date") from exc


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                _jsonable(payload),
                f,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class SnapshotStore:
    """Daily immutable snapshot store.

    One logical snapshot per trading day. Re-input on the same trading day creates
    a revision only when content differs; the previous revision is preserved.
    Wall-clock time is audit metadata and never the history identity.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _day_dir(self, trading_date: str) -> Path:
        return self.root / trading_date

    def _manifest_path(self, trading_date: str) -> Path:
        return self._day_dir(trading_date) / "manifest.json"

    def _load_manifest(self, trading_date: str) -> dict[str, Any]:
        p = self._manifest_path(trading_date)
        if not p.exists():
            return {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "trading_date": trading_date,
                "effective_revision": None,
                "revisions": [],
            }
        with p.open("r", encoding="utf-8") as f:
            m = json.load(f)
        if m.get("trading_date") != trading_date or not isinstance(m.get("revisions"), list):
            raise SnapshotError(f"corrupt manifest for {trading_date}")
        return m

    def save_daily_snapshot(
        self,
        *,
        trading_date: str | date | datetime,
        raw_batches: Sequence[str],
        normalized_batches: Sequence[Any],
        merged_stage1: Any,
        validation: Mapping[str, Any],
        source: str = "MANUAL_STOCKBIT",
        created_at: datetime | None = None,
    ) -> SnapshotRef:
        td = _normalize_trading_date(trading_date)
        if len(raw_batches) != 3 or len(normalized_batches) != 3:
            raise SnapshotError("exactly 3 raw and 3 normalized batches are required")

        gate_state = str(validation.get("gate_state", "")).upper()
        if gate_state not in {"PASS", "REVIEW"}:
            raise SnapshotError("only usable PASS/REVIEW imports may create snapshots")

        evidence = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "trading_date": td,
            "source": source,
            "raw_batches": list(raw_batches),
            "normalized_batches": _jsonable(list(normalized_batches)),
            "merged_stage1": _jsonable(merged_stage1),
            "validation": _jsonable(validation),
        }
        content_hash = _hash_payload(evidence)
        manifest = self._load_manifest(td)

        for item in manifest["revisions"]:
            if item.get("content_hash") == content_hash:
                return SnapshotRef(
                    **{k: item[k] for k in SnapshotRef.__dataclass_fields__}
                )

        revision = len(manifest["revisions"]) + 1
        created = (created_at or datetime.now().astimezone()).isoformat()
        snapshot_id = f"DAILY-{td.replace('-', '')}-R{revision}"
        ref = SnapshotRef(
            td,
            revision,
            snapshot_id,
            "EFFECTIVE",
            content_hash,
            created,
            source,
            gate_state,
        )

        payload = dict(evidence)
        payload.update(
            {
                "snapshot_id": snapshot_id,
                "revision": revision,
                "created_at": created,
                "content_hash": content_hash,
            }
        )
        rev_path = self._day_dir(td) / f"revision_{revision:03d}.json"
        _atomic_write_json(rev_path, payload)

        for item in manifest["revisions"]:
            if item.get("status") == "EFFECTIVE":
                item["status"] = "SUPERSEDED"
        manifest["revisions"].append(asdict(ref))
        manifest["effective_revision"] = revision
        _atomic_write_json(self._manifest_path(td), manifest)
        return ref

    def list_daily(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for day in sorted(
            (p for p in self.root.iterdir() if p.is_dir()),
            reverse=True,
        ):
            try:
                m = self._load_manifest(day.name)
                rev = m.get("effective_revision")
                if not rev:
                    continue
                item = next(x for x in m["revisions"] if x["revision"] == rev)
                rows.append(dict(item))
            except Exception:
                rows.append({"trading_date": day.name, "status": "CORRUPT"})
        return rows

    def export_backup(self) -> bytes:
        """Export the complete temporary history as a portable ZIP backup."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            files = sorted(p for p in self.root.rglob("*") if p.is_file())
            for path in files:
                zf.write(path, path.relative_to(self.root).as_posix())
            index = {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "export_type": "SIS_DAILY_HISTORY_BACKUP",
                "daily_snapshots": self.list_daily(),
            }
            zf.writestr(
                "BACKUP_INDEX.json",
                json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2),
            )
        return buffer.getvalue()

    def load_effective(self, trading_date: str | date | datetime) -> dict[str, Any]:
        td = _normalize_trading_date(trading_date)
        m = self._load_manifest(td)
        rev = m.get("effective_revision")
        if not rev:
            raise SnapshotError(f"no snapshot for {td}")

        p = self._day_dir(td) / f"revision_{int(rev):03d}.json"
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        expected = payload.pop("content_hash")
        check = {
            k: payload[k]
            for k in (
                "schema_version",
                "trading_date",
                "source",
                "raw_batches",
                "normalized_batches",
                "merged_stage1",
                "validation",
            )
        }
        actual = _hash_payload(check)
        payload["content_hash"] = expected
        if actual != expected:
            raise SnapshotError(f"snapshot integrity mismatch for {td}")
        return payload
