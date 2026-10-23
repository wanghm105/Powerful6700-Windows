"""Sparse feature-state backup archives.

A backup contains the fixed, known sectors that the device profile reads for
preflight: the catalog-owned fields plus their read-only layout guards.  It is
deliberately *not* a disk, partition or firmware image.  Restore can therefore
only write back the catalog-owned bytes; unknown addresses are never accepted.

The archive is a small ZIP container with a strict, hash-checked manifest.  It
contains no ProductInfo, serial number, host path, firmware blob or key.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import uuid
import zipfile

from . import __version__
from .device_protocol import DeviceError


SCHEMA_VERSION = 1
KIND = "a6700-sparse-feature-state"
SUFFIX = ".a6700backup"
SECTOR_SIZE = 512
ARCHIVE_NAMES = frozenset({"manifest.json", "sectors.bin", "README.txt"})
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
SCOPE_NOTE = ("只包含本工具读取的固定功能扇区与结构守卫；"
              "不是整盘、分区或固件镜像，不能用于救砖。")


def default_backup_dir() -> Path:
    return Path.home() / "Documents" / "A6700 Backups"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_directory(path: Path):
    missing = []
    cursor = Path(path)
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            if not directory.is_dir():
                raise
        fd = os.open(directory.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _sync_file(path: Path):
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _feature_rows(plan):
    return [dict(id=row["id"], name=row["name"], state=row["state"])
            for row in plan.get("features", [])]


def _manifest(profile, sectors, plan, created_at):
    return dict(
        schema_version=SCHEMA_VERSION,
        kind=KIND,
        scope="sparse-feature-state-not-full-disk",
        note=SCOPE_NOTE,
        created_at=created_at,
        tool_version=__version__,
        catalog_id=profile.catalog.data["catalog_id"],
        catalog_sha256=profile.catalog.digest,
        profile_id=profile.data["profile_id"],
        profile_sha256=profile.digest,
        model=profile.catalog.data["model"],
        firmware=profile.catalog.data["firmware"],
        sector_size=SECTOR_SIZE,
        entry_count=len(profile.entries),
        total_bytes=len(profile.entries) * SECTOR_SIZE,
        payload_sha256=_sha256(b"".join(sectors)),
        bundle_state=plan.get("bundle_state", "unknown"),
        features=_feature_rows(plan),
        sectors=[dict(index=row["index"],
                      device=row["device"],
                      device_offset=row["device_offset"],
                      role=row["role"],
                      sha256=_sha256(sector))
                 for row, sector in zip(profile.entries, sectors)],
    )


def _readme(manifest):
    devices = {}
    for row in manifest["sectors"]:
        devices.setdefault(row["device"], 0)
        devices[row["device"]] += 1
    lines = [
        "A6700 功能状态备份（稀疏）",
        "",
        f"格式版本：{manifest['schema_version']}",
        f"创建时间：{manifest['created_at']}",
        f"工具版本：{manifest['tool_version']}",
        f"机型／固件：{manifest['model']} / {manifest['firmware']}",
        f"扇区：{manifest['entry_count']} 个，共 {manifest['total_bytes']} 字节",
        "设备视图：" + "，".join(f"device {key}: {value} 个扇区"
                                 for key, value in sorted(devices.items())),
        f"备份时状态：{manifest['bundle_state']}",
        "",
        "包含内容：",
        "  manifest.json  备份身份、字段状态、逐扇区哈希",
        "  sectors.bin    512 字节扇区原始数据，按 manifest 顺序排列",
        "  README.txt     本说明",
        "",
        "边界：",
        "  1. 这不是整盘、分区或固件镜像，不能用于救砖，也不能恢复未由本工具管理的设置。",
        "  2. 恢复工具只写回清单内的功能字段；结构守卫或非管理字段不一致时会停止。",
        "  3. 备份与恢复均要求同一机型／固件、同一适配版本；跨版本不会放行。",
        "  4. 文件不含相机序列号、ProductInfo、密钥或主机路径，可自行复制保存。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _archive_bytes(manifest, sectors):
    payload = b"".join(sectors)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in (("manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
                           ("sectors.bin", payload),
                           ("README.txt", _readme(manifest))):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o600 & 0xFFFF) << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def _new_path(directory, created_at):
    stamp = created_at.replace("-", "").replace(":", "")
    return Path(directory) / f"A6700-state-{stamp}-{uuid.uuid4().hex[:8]}{SUFFIX}"


def _write_new(path: Path, data: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    _sync_file(path)


def create_backup(profile, sectors, plan, directory=None, now: datetime | None = None) -> dict:
    """Write a new sparse backup archive and return its public description.

    The caller must already have read ``sectors`` from a compatible device and
    must hold the device lock.  Existing files are never overwritten.
    """
    if len(sectors) != len(profile.entries) or any(len(s) != SECTOR_SIZE for s in sectors):
        raise ValueError("Incomplete sparse capture cannot become a backup")
    if not plan.get("compatible"):
        raise ValueError("Incompatible content cannot become a backup")
    created = now or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created_at = created.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = _manifest(profile, sectors, plan, created_at)
    data = _archive_bytes(manifest, sectors)
    target_directory = Path(directory) if directory is not None else default_backup_dir()
    _ensure_directory(target_directory)
    for _attempt in range(4):
        path = _new_path(target_directory, created_at)
        try:
            _write_new(path, data)
            break
        except FileExistsError:
            continue
    else:
        raise OSError("无法创建唯一的备份文件名")
    return dict(id=path.name, name=path.name, path=str(path), sha256=_sha256(data),
                created_at=created_at, size=len(data), sector_count=len(sectors),
                total_bytes=len(sectors) * SECTOR_SIZE, features=_feature_rows(plan),
                bundle_state=plan.get("bundle_state", "unknown"), manifest=manifest)


@dataclass(frozen=True)
class Backup:
    path: Path
    archive_sha256: str
    manifest: dict
    sectors: tuple[bytes, ...]

    @property
    def id(self) -> str:
        return self.path.name

    @property
    def created_at(self) -> str:
        return self.manifest["created_at"]

    @property
    def features(self):
        return [dict(row) for row in self.manifest.get("features", [])]


def _manifest_from_archive(path: Path) -> dict:
    """Read and structure-check a manifest without trusting the payload."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise DeviceError("无法读取备份文件：" + str(exc)) from exc
    if not path.is_file() or path.is_symlink():
        raise DeviceError("备份必须是普通文件，不接受符号链接或设备文件")
    if info.st_size > MAX_ARCHIVE_BYTES:
        raise DeviceError("备份文件过大，不是本工具生成的稀疏功能状态备份")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(ARCHIVE_NAMES) or set(names) != ARCHIVE_NAMES:
                raise DeviceError("备份容器结构不完整或包含未知文件")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise DeviceError("备份清单过大")
            raw = archive.read("manifest.json")
    except DeviceError:
        raise
    except Exception as exc:
        raise DeviceError("备份文件已损坏或不是本工具生成的格式") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeviceError("备份清单不是有效的 UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise DeviceError("备份清单格式无效")
    required = {"schema_version", "kind", "scope", "created_at", "tool_version",
                "catalog_id", "catalog_sha256", "profile_id", "profile_sha256",
                "model", "firmware", "sector_size", "entry_count", "total_bytes",
                "payload_sha256", "bundle_state", "features", "sectors"}
    if not required.issubset(manifest):
        raise DeviceError("备份清单缺少必要字段")
    if (manifest["schema_version"] != SCHEMA_VERSION or manifest["kind"] != KIND
            or manifest["scope"] != "sparse-feature-state-not-full-disk"):
        raise DeviceError("不支持的备份格式版本")
    if manifest["sector_size"] != SECTOR_SIZE:
        raise DeviceError("备份扇区大小与当前适配不一致")
    if type(manifest["entry_count"]) is not int or manifest["entry_count"] < 1:
        raise DeviceError("备份扇区数量无效")
    if type(manifest["total_bytes"]) is not int or manifest["total_bytes"] != manifest["entry_count"] * SECTOR_SIZE:
        raise DeviceError("备份数据长度无效")
    if not isinstance(manifest["sectors"], list) or len(manifest["sectors"]) != manifest["entry_count"]:
        raise DeviceError("备份扇区清单与数量不一致")
    features = manifest["features"]
    if not isinstance(features, list) or any(
            not isinstance(row, dict) or any(key not in row for key in ("id", "name", "state"))
            for row in features):
        raise DeviceError("备份功能状态清单格式无效")
    return manifest


def load_backup(path, profile) -> Backup:
    """Validate every layer of an archive against the current device profile."""
    path = Path(path)
    manifest = _manifest_from_archive(path)
    if manifest["profile_sha256"] != profile.digest:
        raise DeviceError("备份与当前设备适配版本不一致，已停止")
    if manifest["catalog_sha256"] != profile.catalog.digest:
        raise DeviceError("备份与当前功能清单版本不一致，已停止")
    if manifest["profile_id"] != profile.data.get("profile_id"):
        raise DeviceError("备份的设备适配标识不一致，已停止")
    if manifest["entry_count"] != len(profile.entries):
        raise DeviceError("备份扇区数量与当前适配不一致，已停止")
    if manifest["total_bytes"] != len(profile.entries) * SECTOR_SIZE:
        raise DeviceError("备份数据长度与当前适配不一致，已停止")
    info = path.lstat()
    if info.st_size > MAX_ARCHIVE_BYTES:
        raise DeviceError("备份文件过大")
    raw_archive = path.read_bytes()
    try:
        with zipfile.ZipFile(io.BytesIO(raw_archive)) as archive:
            payload = archive.read("sectors.bin")
    except DeviceError:
        raise
    except Exception as exc:
        raise DeviceError("备份数据无法读取") from exc
    expected_size = len(profile.entries) * SECTOR_SIZE
    if len(payload) != expected_size or _sha256(payload) != manifest["payload_sha256"]:
        raise DeviceError("备份数据哈希不一致，文件可能已损坏或被修改")
    sectors = tuple(payload[at:at + SECTOR_SIZE] for at in range(0, len(payload), SECTOR_SIZE))
    for row, sector in zip(manifest["sectors"], sectors):
        if not isinstance(row, dict) or "sha256" not in row:
            raise DeviceError("备份逐扇区清单格式无效")
        if row["sha256"] != _sha256(sector):
            raise DeviceError("备份逐扇区哈希不一致")
    for expected, row, sector in zip(profile.entries, manifest["sectors"], sectors):
        if (row.get("index") != expected["index"] or row.get("device") != expected["device"]
                or row.get("device_offset") != expected["device_offset"]
                or row.get("role") != expected["role"]):
            raise DeviceError("备份扇区映射与当前适配不一致，已停止")
    plan, _ = _inspect_backup(profile, sectors)
    if not plan["compatible"]:
        raise DeviceError("备份内容包含未知字段或结构不匹配，不能用于恢复")
    return Backup(path=path, archive_sha256=_sha256(raw_archive), manifest=manifest,
                  sectors=sectors)


def _inspect_backup(profile, sectors):
    from .device_profile import inspect_sectors
    return inspect_sectors(profile, list(sectors), "inspect")


def restore_plan(profile, backup: Backup, current, features=None) -> tuple[dict, list[bytes]]:
    """Build a restore plan for all or a selected subset of features.

    Both the current device window and the backup must already pass the same
    compatibility checks as a normal preflight.  Unselected feature fields are
    left exactly as they are on the device; selected fields take the backup
    value.  The native writer repeats the byte-mask check.
    """
    from .device_profile import _feature_selection, inspect_sectors

    if len(current) != len(profile.entries) or any(len(s) != SECTOR_SIZE for s in current):
        raise ValueError("Incomplete sparse capture")
    mode, requested = _feature_selection(profile.catalog, features)
    if mode == "missing":
        raise ValueError("恢复操作不接受 missing 选择模式")
    current_plan, _ = inspect_sectors(profile, list(current), "inspect")
    backup_plan, _ = inspect_sectors(profile, list(backup.sectors), "inspect")

    def restore_issues(plan):
        result = []
        for issue in plan.get("issues", []):
            issue = dict(issue)
            if issue.get("kind") == "sector-guard-mismatch":
                issue["kind"] = "guard-mismatch" if issue.get("role") == "guard" else "unmanaged-bytes"
            result.append(issue)
        return result

    issues = restore_issues(current_plan) + restore_issues(backup_plan)
    selected_set = set(requested)
    current_states = {row["id"]: row["state"] for row in current_plan.get("features", [])}
    for feature in profile.catalog.data["features"]:
        if feature["id"] not in selected_set:
            continue
        for required in feature.get("requires", []):
            if required not in selected_set and current_states.get(required) != "enabled":
                issues.append(dict(kind="feature-requirement", feature=feature["id"],
                                   requires=required, required_state=current_states.get(required)))
    after = [bytearray(s) for s in current]
    index_by_file = {(row["image"], row["file_offset"]): row["index"]
                     for row in profile.entries if row["role"] == "target"}
    if not issues:
        for edit in profile.catalog.edits:
            if edit.feature not in selected_set:
                continue
            value = bytes(backup.sectors[index_by_file[(edit.image, at // 512 * 512)]][at % 512]
                          for at in range(edit.offset, edit.end))
            for at, byte in zip(range(edit.offset, edit.end), value):
                after[index_by_file[(edit.image, at // 512 * 512)]][at % 512] = byte
    expected_plan = None
    if not issues:
        expected_plan, _ = inspect_sectors(profile, [bytes(s) for s in after], "inspect")
        issues.extend(restore_issues(expected_plan))
    compatible = not issues
    if not compatible:
        after = [bytearray(s) for s in current]
    changed_indices = [index for index, (a, b) in enumerate(zip(current, after)) if a != b]
    feature_rows = (expected_plan["features"] if expected_plan is not None
                    else backup_plan["features"])
    feature_rows = [dict(row, selected=row["id"] in selected_set) for row in feature_rows]
    plan = dict(kind="restore", profile_id=profile.data["profile_id"],
                profile_sha256=profile.digest, catalog_sha256=profile.catalog.digest,
                model=profile.catalog.data["model"], firmware=profile.catalog.data["firmware"],
                backup_id=backup.id, backup_sha256=backup.archive_sha256,
                backup_created_at=backup.created_at, compatible=compatible, issues=issues,
                features=feature_rows, selected_features=[row["id"] for row in feature_rows
                                                          if row["id"] in selected_set],
                selection_mode=mode,
                bundle_state=(expected_plan["bundle_state"] if expected_plan is not None
                              else backup.manifest.get("bundle_state", "unknown")),
                status="blocked" if not compatible else "ready" if changed_indices else "no-op",
                read_sectors=len(current), read_bytes=len(current) * SECTOR_SIZE,
                changed_indices=changed_indices, changed_sectors=len(changed_indices),
                changed_bytes=sum(sum(a != b for a, b in zip(current[i], after[i]))
                                  for i in changed_indices),
                full_backup=False)
    return plan, after


def list_backups(directory=None) -> list[dict]:
    """List valid archives newest first; corrupt files are not offered."""
    directory = Path(directory) if directory is not None else default_backup_dir()
    try:
        entries = list(directory.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return []
    result = []
    for path in entries:
        if path.suffix != SUFFIX or path.is_symlink() or not path.is_file():
            continue
        try:
            manifest = _manifest_from_archive(path)
            size = path.stat().st_size
        except (DeviceError, OSError, ValueError):
            continue
        result.append(dict(id=path.name, name=path.name, path=str(path),
                           created_at=manifest.get("created_at", ""), size=size,
                           profile_id=manifest.get("profile_id", ""),
                           profile_sha256=manifest.get("profile_sha256", ""),
                           catalog_sha256=manifest.get("catalog_sha256", ""),
                           model=manifest.get("model", ""),
                           firmware=manifest.get("firmware", ""),
                           sector_count=manifest.get("entry_count", 0),
                           total_bytes=manifest.get("total_bytes", 0),
                           bundle_state=manifest.get("bundle_state", "unknown"),
                           features=[dict(row) for row in manifest.get("features", [])
                                     if isinstance(row, dict)]))
    result.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
    return result


def find_backup(directory, identifier) -> Path:
    if not isinstance(identifier, str) or not identifier or Path(identifier).name != identifier:
        raise DeviceError("请选择一个本机功能状态备份")
    path = Path(directory) / identifier
    if path.suffix != SUFFIX or path.is_symlink() or not path.is_file():
        raise DeviceError("所选备份不存在或不是本工具生成的文件")
    return path
