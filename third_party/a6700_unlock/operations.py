"""Shared device workflow: preflight -> journal -> write -> independent read."""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

from .backup import Backup, create_backup, default_backup_dir, restore_plan
from .device_profile import inspect_sectors
from .device_protocol import DeviceError


def default_state_dir():
    return (Path.home() / "Library/Application Support/a6700-unlock" if sys.platform == "darwin"
            else Path.home() / ".local/state/a6700-unlock")


def make_directory(path):
    """Persist newly created directory entries before relying on the journal."""
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


def save_json(path, data):
    """Exclusive, durable files; no accidental input/report overwrites."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    # A successful file fsync is insufficient if its new directory entry has
    # not reached storage. If directory syncing is unsupported, stop pre-write.
    parent_fd = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def record_warning(result, message):
    previous = result.get("record_warning")
    result["record_warning"] = (previous + "；" if previous else "") + message


def host_lock_path():
    # Shared with the existing research wizards, independent of report paths.
    base = (Path.home() / "Library/Application Support" if sys.platform == "darwin"
            else Path.home() / ".local/state")
    return base / "sony-a6700-ftp/.assistant.lock"


@contextlib.contextmanager
def device_lock(directory):
    try:
        import fcntl
    except ImportError as exc:
        raise DeviceError("设备执行目前支持 macOS／Linux；Windows 尚未验证") from exc
    # Keep the previous per-directory lock as well, for concurrent dev2 clients.
    # Never unlink either file: existing handles must retain the same inode.
    with contextlib.ExitStack() as stack:
        for path in (host_lock_path(), Path(directory) / "device.lock"):
            make_directory(path.parent)
            lock = stack.enter_context(path.open("a+"))
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeviceError("本机已有相机工具运行，请等待其完成；更换记录目录不会绕过设备锁") from exc
        yield


def execute(profile, backend, action, state_dir=None, progress=lambda message: None, dry_run=False, features=None, manage_backend=True):
    if action not in ("inspect", "unlock", "close"):
        raise DeviceError("未知设备操作；当前支持检查、解锁、关闭、功能状态备份与恢复")
    directory = Path(state_dir) if state_dir else default_state_dir()
    with device_lock(directory):
        return _execute_session(profile, backend, action, directory, progress, dry_run, features, manage_backend)


def execute_backup(profile, backend, backup_dir=None, state_dir=None,
                   progress=lambda message: None, dry_run=False, manage_backend=True):
    """Read the sparse feature-state window and save a local archive."""
    directory = Path(state_dir) if state_dir else default_state_dir()
    target = Path(backup_dir) if backup_dir is not None else default_backup_dir()
    if not dry_run:
        # Fail before opening the device if the destination is unusable.
        make_directory(target)
    with device_lock(directory):
        return _backup_session(profile, backend, target, directory, progress, dry_run, manage_backend)


def execute_restore(profile, backend, backup: Backup, state_dir=None,
                    progress=lambda message: None, dry_run=False, features=None, manage_backend=True):
    """Write only catalog-owned bytes from a validated sparse backup."""
    if not isinstance(backup, Backup):
        raise DeviceError("请选择一个已验证的本机功能状态备份")
    directory = Path(state_dir) if state_dir else default_state_dir()
    with device_lock(directory):
        return _restore_session(profile, backend, backup, directory, progress, dry_run, features, manage_backend)


def _backup_session(profile, backend, backup_directory, directory, progress, dry_run=False, manage_backend=True):
    result = dict(action="backup", backup_kind="sparse-feature-state",
                  device_access=False, write_attempted=False, verified=False,
                  full_backup=False, profile_sha256=profile.digest, cleanup_warning=None)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:10]
    run_dir = directory / "runs" / run_id
    make_directory(run_dir)
    result["run_directory"] = str(run_dir)
    try:
        result["device_access"] = True
        with (backend if manage_backend else contextlib.nullcontext()):
            progress(f"正在读取功能状态备份范围（{len(profile.entries)} 个固定扇区，"
                     "不是整盘镜像）…")
            sectors = backend.read(uuid.uuid4().bytes)
            plan, _ = inspect_sectors(profile, sectors, "inspect")
            save_json(run_dir / "plan.json", plan)
            result["plan"] = plan
            if not plan["compatible"]:
                result["status"] = "blocked"
                result["error"] = "内容或布局不匹配，未创建备份"
                progress("内容或布局不匹配，已停止；没有创建备份文件。")
            elif dry_run:
                result["status"] = "dry-run"
                progress("备份预检完成：目标可读取且兼容；未创建备份文件。")
            else:
                progress("正在写入本机功能状态备份…")
                info = create_backup(profile, sectors, plan, backup_directory)
                result.update(status="backup-completed", verified=True,
                              backup=dict(info),
                              backup_path=info["path"], backup_sha256=info["sha256"],
                              backup_id=info["id"], features=plan["features"])
                result["backup"].pop("manifest", None)
                progress("功能状态备份已保存：" + info["path"] +
                         "（稀疏，不是整机镜像）")
    except KeyboardInterrupt:
        result["status"] = "cancelled"
        result["error"] = "操作已取消，没有创建设备写入"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    finally:
        result["cleanup_warning"] = getattr(backend, "cleanup_warning", None)
        result["cleanup_status"] = getattr(backend, "cleanup_status", None)
        try:
            save_json(run_dir / "result.json", result)
        except OSError as exc:
            record_warning(result, "无法保存最终报告：" + str(exc))
    return result


def _restore_session(profile, backend, backup, directory, progress, dry_run=False, features=None, manage_backend=True):
    result = dict(action="restore", backup_kind="sparse-feature-state",
                  backup_id=backup.id, backup_path=str(backup.path),
                  backup_sha256=backup.archive_sha256, device_access=False,
                  write_attempted=False, verified=False, full_backup=False,
                  profile_sha256=profile.digest, cleanup_warning=None)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:10]
    run_dir = directory / "runs" / run_id
    make_directory(run_dir)
    result["run_directory"] = str(run_dir)
    try:
        result["device_access"] = True
        with (backend if manage_backend else contextlib.nullcontext()):
            progress("正在读取当前功能状态，准备从备份恢复…")
            before = backend.read(uuid.uuid4().bytes)
            plan, after = restore_plan(profile, backup, before, features)
            save_json(run_dir / "plan.json", plan)
            result["plan"] = plan
            if not plan["compatible"]:
                result["status"] = "blocked"
                result["error"] = "备份与当前设备内容不匹配，未执行写入"
                progress("结构守卫或非管理字段不一致，已停止；没有发送写入器。")
            elif dry_run:
                result["status"] = "dry-run"
                progress(f"恢复预检完成：预计写回 {plan['changed_bytes']} 字节／"
                         f"{plan['changed_sectors']} 个扇区；未写入。")
            elif not plan["changed_indices"]:
                result.update(status="no-op", verified=True,
                              final_features=plan["features"])
                progress("当前状态已与备份一致，无需恢复。")
            else:
                save_json(run_dir / "preimages.json", dict(
                    profile_sha256=profile.digest, full_backup=False,
                    backup_id=backup.id, backup_sha256=backup.archive_sha256,
                    sectors=[s.hex() for s in before]))
                save_json(run_dir / "targets.json", dict(
                    profile_sha256=profile.digest, backup_id=backup.id,
                    changed_indices=plan["changed_indices"],
                    sectors=[s.hex() for s in after]))
                save_json(run_dir / "restore-source.json", dict(
                    backup_id=backup.id, backup_path=str(backup.path),
                    backup_sha256=backup.archive_sha256,
                    backup_created_at=backup.created_at,
                    tool_version=backup.manifest.get("tool_version")))
                nonce = uuid.uuid4().bytes
                save_json(run_dir / "write-intent.json", dict(
                    nonce=nonce.hex(), action="restore", backup_id=backup.id,
                    backup_sha256=backup.archive_sha256, profile_sha256=profile.digest,
                    changed_indices=plan["changed_indices"]))
                result["write_attempted"] = True
                progress(f"正在从备份恢复：{plan['changed_sectors']} 个扇区；"
                         "相机内会再次校验写前内容和固定掩码。")
                native = backend.write(before, after, nonce)
                result["native_result"] = {k: v for k, v in native.items() if k != "sectors"}
                try:
                    save_json(run_dir / "native-result.json", result["native_result"])
                except OSError as exc:
                    record_warning(result, "无法保存相机执行结果：" + str(exc))
                progress("正在独立回读恢复目标…")
                observed = backend.read(uuid.uuid4().bytes)
                expected = before if native["status"] else after
                matches = observed == expected
                if native["status"]:
                    result["status"] = ("rolled-back" if native.get("rolled_back") and matches
                                        else "rejected" if not native.get("touched") and matches
                                        else "verification-failed" if not native.get("touched")
                                        else "recovery-required")
                    result["error"] = native.get("error") or "相机内执行失败"
                elif not matches:
                    result.update(status="verification-failed",
                                  error="独立回读与备份不一致；请保留操作记录，不要盲目重试")
                else:
                    final, _ = inspect_sectors(profile, observed, "inspect")
                    result["verified"] = final["compatible"] and observed == after
                    result["final_features"] = final["features"]
                    result["status"] = "restored" if result["verified"] else "verification-failed"
                    if result["verified"]:
                        result["restart_required"] = True
                        progress("备份恢复及独立回读通过。请正常退出后关机重开，再确认相机实际功能。")
    except KeyboardInterrupt:
        result["status"] = "uncertain" if result["write_attempted"] else "cancelled"
        result["error"] = ("用户中断；已发送的恢复写入不会被自动重发，请保留操作记录"
                           if result["write_attempted"] else "操作已取消，没有发送写入器")
    except Exception as exc:
        result["status"] = "uncertain" if result["write_attempted"] else "error"
        result["error"] = str(exc)
    finally:
        result["cleanup_warning"] = getattr(backend, "cleanup_warning", None)
        result["cleanup_status"] = getattr(backend, "cleanup_status", None)
        try:
            save_json(run_dir / "result.json", result)
        except OSError as exc:
            record_warning(result, "无法保存最终报告：" + str(exc))
    return result


def _execute_session(profile, backend, action, directory, progress, dry_run=False, features=None, manage_backend=True):
    """Shared transaction; physical caller must hold device_lock.

    The desktop simulator calls this with an in-memory backend and a private
    temporary directory. It never acquires the physical-device lock.
    """
    result = dict(action=action, device_access=False, write_attempted=False, verified=False,
                  full_backup=False, profile_sha256=profile.digest, cleanup_warning=None)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:10]
    run_dir = directory / "runs" / run_id
    make_directory(run_dir)
    result["run_directory"] = str(run_dir)
    try:
        result["device_access"] = True
        with (backend if manage_backend else contextlib.nullcontext()):
            progress("正在读取补丁目标和结构守卫…")
            before = backend.read(uuid.uuid4().bytes)
            plan, after = inspect_sectors(profile, before, action, features)
            save_json(run_dir / "plan.json", plan)
            result["plan"] = plan
            if not plan["compatible"]:
                result["status"] = "blocked"
                progress("内容或布局不匹配，已停止；没有写入功能目标。")
            elif action == "inspect" or dry_run:
                result["status"] = "inspected" if action == "inspect" else "dry-run"
                progress(f"检查完成：预计修改 {plan['changed_bytes']} 字节／{plan['changed_sectors']} 个扇区。")
            elif not plan["changed_indices"]:
                result.update(status="no-op", verified=True)
                progress("已处于目标状态，无需重复写入。")
            else:
                # Save only the sparse operation window, NOT a full backup.
                save_json(run_dir / "preimages.json", dict(profile_sha256=profile.digest,
                          full_backup=False, sectors=[s.hex() for s in before]))
                save_json(run_dir / "targets.json", dict(profile_sha256=profile.digest,
                          changed_indices=plan["changed_indices"], sectors=[s.hex() for s in after]))
                # This durable marker precedes sending the writer. Any lost
                # reply after it is ambiguous; never resend automatically.
                nonce = uuid.uuid4().bytes
                save_json(run_dir / "write-intent.json", dict(nonce=nonce.hex(), action=action,
                          profile_sha256=profile.digest, changed_indices=plan["changed_indices"]))
                result["write_attempted"] = True
                progress(f"正在执行所选功能{'解锁' if action == 'unlock' else '关闭'}："
                         f"{plan['changed_sectors']} 个扇区；相机内会再次校验写前内容。")
                native = backend.write(before, after, nonce)
                result["native_result"] = {k: v for k, v in native.items() if k != "sectors"}
                # After a writer has run, a local reporting failure must
                # never prevent the independent device verification.
                try:
                    save_json(run_dir / "native-result.json", result["native_result"])
                except OSError as exc:
                    record_warning(result, "无法保存相机执行结果：" + str(exc))
                progress("正在独立回读修改目标…")
                observed = backend.read(uuid.uuid4().bytes)
                expected = before if native["status"] else after
                matches = observed == expected
                if native["status"]:
                    result["status"] = ("rolled-back" if native.get("rolled_back") and matches
                                        else "rejected" if not native.get("touched") and matches
                                        else "verification-failed" if not native.get("touched")
                                        else "recovery-required")
                    result["error"] = native.get("error") or "相机内执行失败"
                elif not matches:
                    result.update(status="verification-failed", error="独立回读与目标不一致；请保留操作记录，不要盲目重试")
                else:
                    final, _ = inspect_sectors(profile, observed, "inspect")
                    result["verified"] = final["compatible"] and observed == after
                    result["final_features"] = final["features"]
                    result["status"] = "completed" if result["verified"] else "verification-failed"
                    if result["verified"]:
                        result["restart_required"] = True
                        progress("写入及独立回读通过。请正常退出后关机重开，再确认相机实际功能。")
    except KeyboardInterrupt:
        result["status"] = "uncertain" if result["write_attempted"] else "cancelled"
        result["error"] = ("用户中断；已发送的相机写入不会被自动重发，请保留操作记录"
                           if result["write_attempted"] else "操作已取消，没有发送功能写入器")
    except Exception as exc:
        result["status"] = "uncertain" if result["write_attempted"] else "error"
        result["error"] = str(exc)
    finally:
        result["cleanup_warning"] = getattr(backend, "cleanup_warning", None)
        result["cleanup_status"] = getattr(backend, "cleanup_status", None)
        try:
            save_json(run_dir / "result.json", result)
        except OSError as exc:
            record_warning(result, "无法保存最终报告：" + str(exc))
    return result
