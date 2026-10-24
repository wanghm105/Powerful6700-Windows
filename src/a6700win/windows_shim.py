"""把上游包里只在 POSIX 上成立的调用换成 Windows 等价实现。

第三处（也是最后一道）Windows 封锁来自 operations.device_lock()：它直接
import fcntl，失败就抛 DeviceError("设备执行目前支持 macOS／Linux；Windows 尚未验证")，
所有真实设备操作（检查/解锁/关闭/备份/恢复）都会在看相机之前就被拦下。

除了锁，上游还有三处 POSIX 依赖会在 Windows 上直接抛错：
- operations.make_directory() / backup._ensure_directory()：先 mkdir，再
  os.open(目录, O_RDONLY) + os.fsync 把目录条目刷盘。Windows 上打开目录
  就是 PermissionError [Errno 13]。
- operations.save_json()：同样对父目录 fsync。
- planner.LocalImage：os.O_NONBLOCK 在 Windows 上不存在（AttributeError）。

这里保留上游的语义而不是简化掉：
- 锁仍是"机器级 host lock + 记录目录 device.lock"两把，非阻塞独占；拿不到就抛
  上游同一句「本机已有相机工具运行…」。Windows 用 msvcrt.locking（对文件首字节
  加锁，句柄一关就释放），等价于 flock 的 LOCK_EX|LOCK_NB。
- 保存仍用 O_EXCL 独占创建 + 文件 fsync，绝不覆盖已有记录；只是不再 fsync 目录
  （NTFS 的元数据日志保证目录条目，Windows 没有对目录 fsync 的等价调用）。
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

# 上游把 host 锁放在 ~/.local/state/sony-a6700-ftp/（macOS 用 ~/Library/Application
# Support）。那套跨工具互斥的对象是同样只跑 macOS/Linux 的研究向导；在 Windows 上
# 既不存在，且普通权限进程也建不出用户目录下的点目录（实测 PermissionError
# [WinError 5]），所以改放本程序的数据目录：提权与非提权进程看到的是同一个文件。


def _device_error(message: str) -> Exception:
    from a6700_unlock.device_protocol import DeviceError

    return DeviceError(message)


def host_lock_path() -> Path:
    from . import paths

    return paths.data_root() / "host.lock"


class OsProxy:
    """把某个 vendored 模块里的 os 换成本代理，按需改写常量与 open 标志。

    Windows 上还有两处 os 差异会悄悄坏事：
    - backup.py 用 os.open(..., O_WRONLY | O_CREAT | O_EXCL) 写 .a6700backup，
      没带 O_BINARY。Windows CRT 默认文本模式，会把写出的 0x0A 翻成 0x0D 0x0A，
      稀疏备份文件当场损坏。这里统一补上 O_BINARY（其他平台是 0，无副作用）。
    - planner.py 打开本地镜像用 O_NONBLOCK，Windows 没有这个常量。
    """

    def __init__(self, **overrides):
        object.__setattr__(self, "_overrides", overrides)

    def __getattr__(self, name):
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        return getattr(os, name)

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        flags |= getattr(os, "O_BINARY", 0)
        if dir_fd is None:
            return os.open(path, flags, mode)
        return os.open(path, flags, mode, dir_fd=dir_fd)


BINARY_OS = OsProxy()
PLANNER_OS = OsProxy(O_NONBLOCK=0)


def default_state_dir() -> Path:
    """上游 non-darwin 分支返回 ~/.local/state/a6700-unlock；改用本程序记录目录。"""
    from . import paths

    return paths.state_dir()


def make_directory(path) -> None:
    """递归建目录；不做目录 fsync（Windows 无等价操作）。"""
    missing = []
    cursor = Path(path)
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(parents=True, exist_ok=True)


def sync_file(path) -> None:
    """上游用来 fsync 父目录；Windows 上只能对文件本身尽力刷一次。"""
    target = Path(path)
    if not target.exists():
        return
    try:
        with open(target, "rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass


def save_json(path, data) -> None:
    """独占创建 + 文件 fsync；不覆盖已有记录，不 fsync 目录。"""
    target = Path(path)
    make_directory(target.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


@contextlib.contextmanager
def device_lock(directory):
    """两把非阻塞独占锁；语义与上游 fcntl.flock 版本一致。"""
    import msvcrt

    handles = []
    try:
        for path in (host_lock_path(), Path(directory) / "device.lock"):
            make_directory(Path(path).parent)
            handle = open(path, "a+b")
            handles.append(handle)
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise _device_error(
                    "本机已有相机工具运行，请等待其完成；更换记录目录不会绕过设备锁"
                ) from exc
        yield
    finally:
        for handle in reversed(handles):
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                handle.close()
            except OSError:
                pass


def wrap_run_reserved(original):
    """run_reserved() 抛异常时把控制器从 running 状态里放出来。

    上游 run_reserved() 只在正常返回时清 busy；设备出错（例如 USB 认证失败）时
    异常一路冒到界面，busy 永远为 True，界面就卡在「操作进行中」且按钮全灰。
    """

    def run_reserved(self, progress=lambda _message: None):
        try:
            return original(self, progress)
        except BaseException:
            with self.lock:
                self.busy = False
                self.action = ""
                self.backup_id = None
                self.result = None
                self.cancel.clear()
                self.phase = "home" if self.compatible else self._preparation_phase()
                self.revision += 1
            raise

    run_reserved._a6700win_wrapped = True
    return run_reserved

def wrap_reserve(original):
    """恢复不读勾选，但上游 reserve 会先因为“没勾功能”拒绝。

    只读检查后 selected_features 是“尚未开启的功能”；相机已经全开时这个集合是空的，
    于是 reserve('restore') 在检查备份之前就抛“请至少选择一个功能”。真正执行时
    wrap_restore_scope 又会把选择临时扩成全部已开放功能，所以这里预约前补上，
    让两侧语义一致。
    """

    def reserve(self, action, backup_id=None):
        if action == "restore" and not self.selected_features:
            try:
                available = set(self.service.profile.catalog.available_features)
            except Exception:  # noqa: BLE001 - 取不到就交给上游报它自己的错
                available = set()
            if available:
                self.selected_features = available
        return original(self, action, backup_id)

    reserve._a6700win_wrapped = True
    return reserve


def wrap_restore_scope(original):
    """让「恢复」始终整份写回备份，而不是只恢复勾选的功能。

    上游 run_reserved() 对 restore 也传 features=sorted(self.selected_features)，
    restore_plan() 因此只把勾选功能的字段改回备份值。界面上「恢复所选备份」指的是
    整份功能状态，勾选残留（例如上一次只关了快门声音）会让恢复变成 no-op 或半份
    恢复。这里在调用前把选择临时扩到全部已开放功能（restore_plan 的 'all' 语义），
    调用后原样还原，不改变用户的选择记忆。
    """

    def run_reserved(self, progress=lambda _message: None):
        saved = None
        if getattr(self, "action", "") == "restore":
            catalog = self.service.profile.catalog
            saved = set(self.selected_features)
            self.selected_features = set(catalog.available_features)
        try:
            return original(self, progress)
        finally:
            if saved is not None:
                self.selected_features = saved

    run_reserved._a6700win_restore_scope = True
    # 保留内层的包装标记，否则第二次 install() 会再套一层错误处理。
    run_reserved._a6700win_wrapped = getattr(original, "_a6700win_wrapped", False)
    return run_reserved
