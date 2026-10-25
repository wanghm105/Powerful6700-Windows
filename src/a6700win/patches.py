"""把上游 a6700_unlock 的运行期行为改造成 Windows 版本。

上游包（third_party/a6700_unlock，GPL-3.0）本身只支持 macOS/Linux：设备层没有
Windows 的 libusb 解析分支，doctor 直接判定"Windows 适配尚未完成"，因此
DesktopController 的启动检查在 Windows 上永远不通过。

这里不打补丁文件、不 fork 包，而是在进程启动时替换少量模块属性：
- legacy.libusb_library_path   → libusb-package 自带的 libusb-1.0.dll
- legacy.get_libusb_backend    → Windows 上强制 fresh（驱动切换后需要新上下文）
- legacy.run_authentication    → a6700win.usb.windows_auth.run_authentication
- legacy.observed_sony_product_ids / normal_mode_observed → SetupAPI 版本
- doctor.diagnose 与 preparation.diagnose → Windows 版启动检查
- operations.device_lock / make_directory / save_json、backup 的同名助手
  → a6700win.windows_shim（上游用 fcntl 与目录 fsync，Windows 上不可用）
- device_profile.inspect_sectors / operations.inspect_sectors
  → a6700win.guards（结构守卫里有 9 个扇区是 ext2 inode 元数据，
    相机开机自己会刷新时间戳，只放行这 12 字节）
- DesktopController.run_reserved → 出错时释放 busy，界面不再卡在"操作进行中"

用法：在构造 DesktopController 之前调用 install()。
"""

from __future__ import annotations

import ctypes
import sys

from . import guards, paths, windows_shim
from .usb import driver, setupapi, windows_auth

_installed = False

# 供自检与 GUI 展示的补丁清单（顺序即安装顺序）。
_PATCH_NAMES = (
    "legacy.libusb_library_path",
    "legacy.get_libusb_backend",
    "legacy.run_authentication",
    "legacy.observed_sony_product_ids",
    "legacy.normal_mode_observed",
    "doctor.diagnose",
    "preparation.diagnose",
    "a6700_unlock.usb.backend.payloads",
    "a6700_unlock.doctor.payloads",
    "a6700_unlock.desktop.controller.payloads",
    "operations.device_lock",
    "operations.host_lock_path",
    "operations.make_directory",
    "operations.save_json",
    "operations.default_state_dir",
    "backup._ensure_directory",
    "backup._sync_file",
    "planner.os.O_NONBLOCK",
    "backup.os.O_BINARY",
    "controller.run_reserved",
    "controller.reserve",
    "operations._execute_session",
    "operations._restore_session",
    "usb.backend.UsbBackend._file",
    "device_profile.inspect_sectors",
    "operations.inspect_sectors",
    "controller.available_backups",
    "controller.restore_scope",
)


def _windows_get_libusb_backend(original):
    def get_libusb_backend(*, fresh: bool = False):
        # PyUSB 1.2.1 会把 context 永久缓存；驱动切换/重新枚举后必须重建。
        return original(fresh=True)

    return get_libusb_backend


def _windows_diagnose(original):
    def diagnose(profile):
        payload = original(profile)
        checks = payload.get("checks", [])
        for item in checks:
            identifier = item.get("id")
            if identifier == "platform":
                item.update(
                    ok=True,
                    detail=sys.platform,
                    remediation="当前设备连接层为 Windows（WinUSB + libusb）实现。",
                )
            elif identifier == "libusb":
                item.update(**_libusb_status())
        payload["checks"] = checks
        payload["ready"] = all(bool(item.get("ok")) for item in checks)
        payload["device_access"] = True
        return payload

    return diagnose


def _libusb_status() -> dict:
    try:
        path = windows_auth.libusb_library_path()
    except Exception as exc:  # noqa: BLE001
        return dict(ok=False, detail=str(exc), remediation="重新安装本程序以恢复 libusb-1.0.dll。")
    try:
        library = ctypes.CDLL(path)
        for symbol in ("libusb_init", "libusb_exit", "libusb_get_device_list", "libusb_open"):
            getattr(library, symbol)
    except (OSError, AttributeError) as exc:
        return dict(
            ok=False,
            detail="%s：%s" % (path, exc),
            remediation="libusb-1.0.dll 无法加载，请重新安装本程序。",
        )
    return dict(ok=True, detail=str(path), remediation="")


# --------------------------------------------------------------- 载荷校验
_source_provenance: dict = {}


def source_provenance() -> dict:
    """上游 transaction.c 的指纹核对结果（只作溯源记录，不作为封锁条件）。"""
    return dict(_source_provenance)


def _vendor_file(*parts: str):
    from importlib.resources import files

    node = files("a6700_unlock")
    for part in parts:
        node = node.joinpath(part)
    return node


def windows_payloads(profile):
    """与上游 payloads() 等价，但把源码文本指纹降级为溯源信息。

    真正送到相机的 reader/writer 载荷与 profile 摘要仍然逐字节严格校验：
    上游发布的 manifest.json 声明了一个与其自身 transaction.c 不一致的
    source_sha256（见 docs/UPSTREAM-NOTES.md），若把该行当硬性条件，
    Windows 上的启动检查会永久失败，而风险并没有降低——载荷本身早已校验。
    """
    import hashlib
    import json

    from a6700_unlock.device_protocol import DeviceError

    root = _vendor_file("data", "native")
    try:
        manifest = json.loads(root.joinpath("manifest.json").read_text())
    except (OSError, ValueError) as exc:
        raise DeviceError("Native payload manifest is unreadable: %s" % exc) from exc
    if manifest.get("profile_sha256") != profile.digest:
        raise DeviceError("Native payload/profile versions do not match")

    try:
        source = _vendor_file("native", "transaction.c").read_bytes()
    except OSError:
        source = b""
    actual = hashlib.sha256(source).hexdigest() if source else ""
    expected = str(manifest.get("source_sha256") or "")
    _source_provenance.clear()
    _source_provenance.update(expected=expected, actual=actual, matches=actual == expected,
                              checked=bool(source))

    result = {}
    for name in ("reader", "writer"):
        try:
            data = root.joinpath(name + ".elf").read_bytes()
        except OSError as exc:
            raise DeviceError("Packaged %s payload is missing: %s" % (name, exc)) from exc
        entry = manifest.get("payloads", {}).get(name) or {}
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise DeviceError("Packaged %s payload hash mismatch" % name)
        if int(entry.get("bytes") or 0) not in (0, len(data)):
            raise DeviceError("Packaged %s payload size mismatch" % name)
        result[name] = data
    return result


def _windows_write_status(result):
    """status=1（preimage 变化、touched=0）应当算“写前校验拒绝”，不是“回读失败”。

    上游的 rejected 分支要求回读结果等于 before，而 status=1 本身就意味着设备内容
    已经不等于 before，那个分支永远走不到。零字节写入被标成 verification-failed，
    界面会提示“不要盲目重试”，用户以为可能已经写了一半。
    """
    if not isinstance(result, dict):
        return result
    native = result.get("native_result") or {}
    if (result.get("status") == "verification-failed"
            and native.get("status")
            and not native.get("touched")):
        result["status"] = "rejected"
        result["error"] = native.get("error") or "写前校验未通过，相机内没有执行修改"
    return result


def _wrap_session(original):
    def session(*args, **kwargs):
        return _windows_write_status(original(*args, **kwargs))

    session._a6700win_wrapped = True
    return session


# 0x4010 = SET_FILE2（配置），0x4007 = SET_FILE（载荷），0x4008 = EXECUTE。
_FILE_STEPS = {0x4010: "配置写入（SET_FILE2）", 0x4007: "载荷写入（SET_FILE）"}


# 相机对临时文件操作返回的状态字（小端 u32）。0x10000004 是 2026-10-25 真机
# 见过的一次：读请求的配置/载荷暂存被拒，界面只看到「状态：04000010」。
_KNOWN_STATUS = {
    0x10000004: "，相机侧含义是临时文件操作被拒（通常是上一次会话没有干净结束）",
    0x10000006: "，相机侧含义是文件不存在",
}


def _status_text(body: bytes) -> str:
    if len(body) < 4:
        return "相机返回了不完整的状态（%s）" % body[:16].hex()
    value = int.from_bytes(body[:4], "little")
    known = _KNOWN_STATUS.get(value, "")
    return "状态 0x%08X%s（原始字节 %s）" % (value, known, body[:16].hex())


def _windows_backend_file(self, command, ident, data):
    """上游把三种失败写成同一句“文件写入或载荷执行失败”，界面看不出卡在哪一步。

    这里保留同样的校验，只把步骤、命令号和相机状态写清楚；错误发生在固件写入之前，
    相机里没有动任何功能字段，文案也直接告诉用户下一步该做什么。
    """
    from a6700_unlock.device_protocol import DeviceError

    body = self._command(command, bytes([0, ident, 0]) + data)
    if len(body) == 4 and body == b"\0" * 4:
        return None
    step = _FILE_STEPS.get(command, "文件写入 0x%04X" % command)
    raise DeviceError(
        "相机拒绝了%s（file_id=%d），%s；这次没有写入任何功能字段。"
        "恢复办法：拔掉数据线 → 相机正常关机 → 取出电池约 1 分钟 → 装回开机 →"
        "重新连 MSC 线，然后再检查一次。" % (step, ident, _status_text(body)))


_windows_backend_file._a6700win_wrapped = True


def _windows_available_backups(self):
    """物理模式下也列出本机功能状态备份。

    上游把桌面端的备份列表藏了起来（controller.py 的 "The desktop backup UI is
    hidden." 注释）：physical 模式下只要当前动作不是 backup/restore 就返回空列表。
    但 reserve('restore', backup_id) 在设置 self.action *之前* 就按这份列表校验
    backup_id，于是桌面端永远无法选择备份——先有鸡先有蛋。本移植在界面上明确提供
    备份/恢复，且备份目录是本程序自己的 .data\backups，枚举代价可以忽略。
    """
    try:
        rows = self.service.list_backups()
    except (OSError, ValueError):
        return []
    digest = self.service.profile.digest
    return [row for row in rows if row.get('profile_sha256') == digest]


_windows_available_backups._a6700win_wrapped = True


def install() -> dict:
    """安装全部补丁；可重复调用。返回补丁清单供自检展示。"""
    global _installed
    paths.ensure_vendor_on_path()
    from a6700_unlock import doctor, preparation
    from a6700_unlock.desktop import controller as controller_module
    from a6700_unlock.usb import backend, legacy

    applied = []
    if not _installed or legacy.libusb_library_path is not windows_auth.libusb_library_path:
        legacy.libusb_library_path = windows_auth.libusb_library_path
        applied.append("legacy.libusb_library_path")

    if not getattr(legacy, "_a6700win_wrapped_backend", False):
        legacy._a6700win_original_backend = legacy.get_libusb_backend
        legacy.get_libusb_backend = _windows_get_libusb_backend(legacy.get_libusb_backend)
        legacy._a6700win_wrapped_backend = True
        applied.append("legacy.get_libusb_backend")

    for name, replacement in (
        ("run_authentication", windows_auth.run_authentication),
        ("observed_sony_product_ids", windows_auth.observed_sony_product_ids),
        ("normal_mode_observed", windows_auth.normal_mode_observed),
    ):
        if getattr(legacy, name) is not replacement:
            setattr(legacy, name, replacement)
            applied.append("legacy." + name)

    if not getattr(doctor, "_a6700win_wrapped_diagnose", False):
        original_doctor = doctor.diagnose
        doctor._a6700win_original_diagnose = original_doctor
        patched_diagnose = _windows_diagnose(original_doctor)
        doctor.diagnose = patched_diagnose
        preparation.diagnose = patched_diagnose
        doctor._a6700win_wrapped_diagnose = True
        preparation._a6700win_wrapped_diagnose = True
        applied.append("doctor.diagnose")
        applied.append("preparation.diagnose")

    # payloads 在 doctor / backend / controller 三处各自绑定，必须逐个替换。
    for module in (backend, doctor, controller_module):
        if getattr(module, "payloads", None) is not windows_payloads:
            if not hasattr(module, "_a6700win_original_payloads"):
                module._a6700win_original_payloads = module.payloads
            module.payloads = windows_payloads
            applied.append(module.__name__ + ".payloads")

    # --- POSIX → Windows 兼容层（设备锁、目录落盘、planner 的 O_NONBLOCK） ---
    from a6700_unlock import backup as backup_module, operations, planner

    if operations.device_lock is not windows_shim.device_lock:
        operations.device_lock = windows_shim.device_lock
        applied.append("operations.device_lock")

    if operations.host_lock_path is not windows_shim.host_lock_path:
        operations.host_lock_path = windows_shim.host_lock_path
        applied.append("operations.host_lock_path")

    if operations.make_directory is not windows_shim.make_directory:
        operations.make_directory = windows_shim.make_directory
        applied.append("operations.make_directory")

    if operations.save_json is not windows_shim.save_json:
        operations.save_json = windows_shim.save_json
        applied.append("operations.save_json")

    if operations.default_state_dir is not windows_shim.default_state_dir:
        operations.default_state_dir = windows_shim.default_state_dir
        applied.append("operations.default_state_dir")

    if backup_module._ensure_directory is not windows_shim.make_directory:
        backup_module._ensure_directory = windows_shim.make_directory
        applied.append("backup._ensure_directory")

    if backup_module._sync_file is not windows_shim.sync_file:
        backup_module._sync_file = windows_shim.sync_file
        applied.append("backup._sync_file")

    # planner.LocalImage 用 os.O_NONBLOCK 打开本地固件镜像；Windows 没有该常量，
    # 换成带 O_NONBLOCK=0 的 os 代理，行为等价于普通阻塞只读打开。
    if planner.os is not windows_shim.PLANNER_OS:
        planner.os = windows_shim.PLANNER_OS
        applied.append("planner.os.O_NONBLOCK")

    # backup.py 写 .a6700backup 时没带 O_BINARY，Windows 文本模式会改写 0x0A，
    # 稀疏备份文件会直接损坏。
    if backup_module.os is not windows_shim.BINARY_OS:
        backup_module.os = windows_shim.BINARY_OS
        applied.append("backup.os.O_BINARY")

    applied.extend(guards.install())

    controller_class = controller_module.DesktopController
    if not getattr(controller_class.run_reserved, "_a6700win_wrapped", False):
        controller_class._a6700win_original_run_reserved = controller_class.run_reserved
        controller_class.run_reserved = windows_shim.wrap_run_reserved(
            controller_class.run_reserved)
        applied.append("controller.run_reserved")

    if not getattr(controller_class.run_reserved, "_a6700win_restore_scope", False):
        controller_class.run_reserved = windows_shim.wrap_restore_scope(
            controller_class.run_reserved)
        applied.append("controller.restore_scope")

    if not getattr(controller_class._available_backups, "_a6700win_wrapped", False):
        controller_class._a6700win_original_available_backups = controller_class._available_backups
        controller_class._available_backups = _windows_available_backups
        applied.append("controller.available_backups")

    # 恢复不读勾选；相机全开时 selected_features 为空，上游 reserve 会在看备份之前拒绝。
    if not getattr(controller_class.reserve, "_a6700win_wrapped", False):
        controller_class.reserve = windows_shim.wrap_reserve(controller_class.reserve)
        applied.append("controller.reserve")

    # status=1（写前校验拒绝、零字节写入）不能报成“独立回读失败”。
    for name in ("_execute_session", "_restore_session"):
        current = getattr(operations, name)
        if not getattr(current, "_a6700win_wrapped", False):
            setattr(operations, name, _wrap_session(current))
            applied.append("operations." + name)

    # 相机拒绝配置/载荷时要说清是哪一步、状态码是多少。
    if not getattr(backend.UsbBackend._file, "_a6700win_wrapped", False):
        backend.UsbBackend._file = _windows_backend_file
        applied.append("usb.backend.UsbBackend._file")

    _installed = True
    already = [name for name in _PATCH_NAMES if name not in applied]
    return dict(applied=applied, already=already, libusb=_libusb_status(), driver=driver.scan())


def _refresh_provenance() -> None:
    """status() 也要能看到载荷溯源信息，无需先跑一次真实检查。"""
    if _source_provenance:
        return
    try:
        from a6700_unlock.catalog import load_catalog
        from a6700_unlock.device_profile import load_device_profile

        windows_payloads(load_device_profile(load_catalog()))
    except Exception:  # noqa: BLE001 - 诊断信息缺失不应让 status() 失败
        pass


def status() -> dict:
    """不触发任何写操作的当前状态，给 GUI 与自检用。"""
    paths.ensure_vendor_on_path()
    _refresh_provenance()
    return dict(
        platform=sys.platform,
        python=sys.version.split()[0],
        installed=_installed,
        paths=paths.describe(),
        libusb=_libusb_status(),
        driver=driver.scan(),
        devices=setupapi.summary(),
        payload_source=source_provenance(),
    )
