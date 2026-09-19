from __future__ import annotations

import hashlib
import io
import json
import math
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
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None

    # Normalize numpy/pandas scalar values before JSON encoding.
    # Missing/non-finite evidence must remain missing (JSON null), never zero.
    if hasattr(value, "item"):
        try:
            scalar = value.item()
            if scalar is not value:
                return _jsonable(scalar)
        except (ValueError, TypeError):
            pass

    # pandas.NA / NaT do not have a stable truth value.
    cls = value.__class__
    if cls.__module__.startswith("pandas") and cls.__name__ in {"NAType", "NaTType"}:
        return None

    try:
        missing = value != value
        # numpy.bool_ and similar scalar booleans are not isinstance(..., bool).
        # Convert only scalar truth values; arrays/Series are deliberately ignored.
        if not hasattr(missing, "__len__"):
            try:
                if bool(missing):
                    return None
            except (TypeError, ValueError):
                pass
    except (TypeError, ValueError):
        pass

    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict(orient="records"))
        except TypeError:
            return _jsonable(value.to_dict())
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

    def restore_backup(self, data: bytes) -> dict[str, int]:
        """Verify and restore a SIS history ZIP without overwriting conflicting history."""
        if not data:
            raise SnapshotError("backup file is empty")

        restored_days = 0
        skipped_days = 0
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = zf.namelist()
            if "BACKUP_INDEX.json" not in names:
                raise SnapshotError("invalid backup: BACKUP_INDEX.json missing")
            if any(
                name.startswith("/") or ".." in Path(name).parts
                for name in names
            ):
                raise SnapshotError("invalid backup path")

            try:
                index = json.loads(zf.read("BACKUP_INDEX.json"))
            except Exception as exc:
                raise SnapshotError("invalid backup index") from exc
            if (
                index.get("export_type") != "SIS_DAILY_HISTORY_BACKUP"
                or index.get("schema_version") != SNAPSHOT_SCHEMA_VERSION
            ):
                raise SnapshotError("unsupported SIS history backup")

            day_names = sorted(
                {
                    parts[0]
                    for name in names
                    if name != "BACKUP_INDEX.json"
                    for parts in [Path(name).parts]
                    if len(parts) == 2 and parts[1] == "manifest.json"
                }
            )
            staged: dict[str, dict[str, bytes]] = {}
            for td in day_names:
                _normalize_trading_date(td)
                manifest_name = f"{td}/manifest.json"
                try:
                    manifest = json.loads(zf.read(manifest_name))
                except Exception as exc:
                    raise SnapshotError(f"invalid manifest for {td}") from exc
                if (
                    manifest.get("trading_date") != td
                    or not isinstance(manifest.get("revisions"), list)
                    or not manifest.get("effective_revision")
                ):
                    raise SnapshotError(f"corrupt manifest for {td}")

                files = {manifest_name: zf.read(manifest_name)}
                revisions = manifest["revisions"]
                seen_revs = set()
                effective_count = 0
                for item in revisions:
                    rev = item.get("revision")
                    if not isinstance(rev, int) or rev < 1 or rev in seen_revs:
                        raise SnapshotError(f"invalid revision manifest for {td}")
                    seen_revs.add(rev)
                    if item.get("status") == "EFFECTIVE":
                        effective_count += 1
                    rev_name = f"{td}/revision_{rev:03d}.json"
                    if rev_name not in names:
                        raise SnapshotError(f"missing revision file for {td} R{rev}")
                    try:
                        payload = json.loads(zf.read(rev_name))
                    except Exception as exc:
                        raise SnapshotError(f"invalid revision file for {td} R{rev}") from exc
                    expected = payload.get("content_hash")
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
                    if (
                        payload.get("trading_date") != td
                        or payload.get("revision") != rev
                        or payload.get("snapshot_id") != item.get("snapshot_id")
                        or expected != item.get("content_hash")
                        or _hash_payload(check) != expected
                    ):
                        raise SnapshotError(f"snapshot integrity mismatch for {td} R{rev}")
                    files[rev_name] = zf.read(rev_name)

                if effective_count != 1:
                    raise SnapshotError(f"invalid effective revision state for {td}")
                effective = manifest["effective_revision"]
                if effective not in seen_revs:
                    raise SnapshotError(f"effective revision missing for {td}")
                staged[td] = files

            for td, files in staged.items():
                target_manifest = self._manifest_path(td)
                if target_manifest.exists():
                    current = self._load_manifest(td)
                    incoming = json.loads(files[f"{td}/manifest.json"])
                    current_hashes = {
                        x.get("content_hash") for x in current.get("revisions", [])
                    }
                    incoming_hashes = {
                        x.get("content_hash") for x in incoming.get("revisions", [])
                    }
                    if current_hashes == incoming_hashes:
                        skipped_days += 1
                        continue
                    raise SnapshotError(
                        f"restore conflict for {td}; existing history was not overwritten"
                    )

                day_dir = self._day_dir(td)
                day_dir.mkdir(parents=True, exist_ok=False)
                try:
                    for name, raw in files.items():
                        target = self.root / name
                        target.write_bytes(raw)
                    # Re-read through normal integrity path before accepting restore.
                    self.load_effective(td)
                except Exception:
                    for p in sorted(day_dir.glob("*"), reverse=True):
                        if p.is_file():
                            p.unlink()
                    day_dir.rmdir()
                    raise
                restored_days += 1

        return {"restored_days": restored_days, "skipped_days": skipped_days}

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
