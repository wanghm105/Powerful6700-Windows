"""Windows 驱动准备：把 Sony 相机 PID 绑定到 WinUSB（libwdi / wdi-simple）。

与上游 a7c2-fl23 的 Windows 方案一致：
- 用 libwdi 的 wdi-simple.exe 安装 WinUSB，参数固定为
  --vid 0x054C --pid 0x<pid> --type 0 --name <名称> --dest <目录> --log 0
- 安装需要管理员权限；未提权时通过 ShellExecuteExW runas 启动自身的
  --elevated-worker 子进程，把结果写入 status.json 后由父进程读取。
- 已经绑定 winusb / libusb0 / libusbk 的 PID 直接跳过，不重复安装。

A6700 的 PID：0x047D、0x0E76 为存储（MSC）模式，0x0336 为 Senser 服务模式。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from ctypes import wintypes
from pathlib import Path
from urllib.request import Request, urlopen

from .. import paths
from . import setupapi

VENDOR_ID = setupapi.SONY_VENDOR_ID
MSC_PIDS = (0x047D, 0x0E76)
SERVICE_PID = 0x0336
SUPPORTED_PIDS = (0x047D, 0x0E76, 0x0336)

PID_LABELS = {
    0x047D: "Sony A6700 - Storage",
    0x0E76: "Sony A6700 - Storage",
    0x0336: "Sony A6700 - Service",
}

PID_TITLES = {
    0x047D: "相机存储模式（MSC，0447 之后的备用 ID）",
    0x0E76: "相机存储模式（MSC）",
    0x0336: "相机服务模式（Senser）",
}

WDI_URL = "https://github.com/Timocop/libwdi-wdi-releases/releases/download/v1.0/x64.zip"
# 国内直连 GitHub 常被拦，下载按钮会按顺序重试这两个反代。
MIRRORS = ("https://ghfast.top/", "https://gh-proxy.com/")
WDI_EXE_NAME = "wdi-simple.exe"
CREATE_NO_WINDOW = 0x08000000
SEE_MASK_NOCLOSEPROCESS = 0x00000040


class DriverError(RuntimeError):
    """驱动准备失败，带可展示给用户的中文说明。"""


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - 非 Windows 或调用失败都按“未提权”处理
        return False


def supported(pid: int) -> bool:
    return pid in SUPPORTED_PIDS


def driver_arguments(executable: str | Path, pid: int, destination: str | Path) -> list[str]:
    """wdi-simple 的固定参数；越界 PID 直接拒绝，避免误绑其他设备。"""
    if not supported(pid):
        raise ValueError("Driver installation is limited to camera PIDs 0E76, 047D and 0336")
    return [
        str(executable),
        "--vid",
        "0x%04X" % VENDOR_ID,
        "--pid",
        "0x%04X" % pid,
        "--type",
        "0",
        "--name",
        PID_LABELS[pid],
        "--dest",
        str(destination),
        "--log",
        "0",
    ]


def bundled_wdi_dir() -> Path:
    # 随包附带的 libwdi 目录：冻结包是 _internal/third_party/libwdi，源码运行是仓库 third_party/libwdi。
    return paths.bundled_root() / "third_party" / "libwdi"


def wdi_bundled() -> bool:
    return (bundled_wdi_dir() / WDI_EXE_NAME).is_file()


def wdi_executable() -> Path:
    # 数据目录优先；还没铺开时先用随包副本，Windows 上不需要联网。
    local = paths.driver_dir() / WDI_EXE_NAME
    if local.is_file():
        return local
    bundled = bundled_wdi_dir() / WDI_EXE_NAME
    if bundled.is_file():
        return bundled
    return local


def wdi_available() -> bool:
    return wdi_executable().is_file()


def _copy_tree(source: Path, destination: Path) -> None:
    for item in source.rglob("*"):
        if item.is_file():
            target = destination / item.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def ensure_wdi(progress=lambda message: None) -> Path:
    # wdi-simple 需要同级的 amd64/ 载荷，所以整棵树铺到数据目录再调用。
    local = paths.driver_dir() / WDI_EXE_NAME
    if local.is_file():
        return local
    bundled = bundled_wdi_dir()
    if (bundled / WDI_EXE_NAME).is_file():
        progress("正在准备随包附带的驱动组件…")
        _copy_tree(bundled, paths.driver_dir())
    return local


def download_wdi(progress=lambda message: None) -> Path:
    # 离线优先：随包副本直接铺开，只有源码运行且没带组件时才联网。
    target = ensure_wdi(progress)
    if target.is_file():
        progress("驱动组件随包附带，已就绪，不需要联网。")
        return target
    folder = paths.driver_dir()
    archive = folder / "libwdi-x64.zip"
    data = b""
    errors = []
    for mirror in (None,) + MIRRORS:
        url = WDI_URL if mirror is None else mirror + WDI_URL
        progress("正在下载驱动安装组件（libwdi，约几 MB）…")
        try:
            request = Request(url, headers={"User-Agent": "Powerful6700Win"})
            with urlopen(request, timeout=120) as response:  # noqa: S310 - 固定 HTTPS 地址
                data = response.read()
        except Exception as exc:  # noqa: BLE001 - 逐个镜像重试
            errors.append("%s: %s" % (url, exc))
            continue
        if len(data) >= 10000:
            break
        errors.append("%s: 内容过短" % url)
        data = b""
    if len(data) < 10000:
        raise DriverError(
            "驱动组件下载失败（%s）。可以让对方把 third_party/libwdi 目录一起复制到程序的 _internal 下，"
            "或手工下载 %s 解压到数据目录的 driver 子目录。" % ("; ".join(errors[:2]) or "网络不可用", WDI_URL)
        )
    archive.write_bytes(data)
    progress("正在解压驱动安装组件…")
    try:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(folder)
    finally:
        archive.unlink(missing_ok=True)
    if not (folder / WDI_EXE_NAME).is_file():
        raise DriverError("驱动组件解压后未找到 wdi-simple.exe。")
    progress("驱动安装组件已就绪。")
    return folder / WDI_EXE_NAME

def scan() -> dict:
    """只读扫描：哪些相机 PID 在场、驱动是否已经就绪。"""
    state = setupapi.summary()
    devices = []
    for row in state.get("devices", []):
        pid = row["pid"]
        devices.append(
            dict(
                pid=pid,
                label=PID_LABELS.get(pid, "Sony USB 0x%04X" % pid),
                title=PID_TITLES.get(pid, "未知 Sony 设备"),
                service=row["service"],
                winusb=row["winusb"],
                supported=supported(pid),
            )
        )
    unmet = [row for row in devices if row["supported"] and not row["winusb"]]
    return dict(
        platform=sys.platform,
        architecture=os.environ.get("PROCESSOR_ARCHITECTURE", ""),
        admin=is_admin(),
        wdi=wdi_available(),
        wdi_bundled=wdi_bundled(),
        wdi_path=str(wdi_executable()),
        enumeration=state,
        devices=devices,
        driver_required=bool(unmet),
        note="" if state.get("available") else "SetupAPI 枚举不可用，无法判断驱动状态。",
    )


def _self_command(request_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--elevated-worker", str(request_path)]
    entry = paths.project_root() / "main.py"
    return [sys.executable, str(entry), "--elevated-worker", str(request_path)]


def _shell_execute_runas(command: list[str], working_directory: str) -> int:
    """以管理员身份启动子进程，返回进程句柄（SHELLEXECUTEINFOW.hProcess）。"""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = command[0]
    info.lpParameters = subprocess.list2cmdline(command[1:]) if len(command) > 1 else None
    info.lpDirectory = working_directory
    info.nShow = 1
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        raise DriverError("无法请求管理员权限（错误码 %d）。请右键以管理员身份运行本程序后重试。" % error)
    return int(info.hProcess or 0)


def _wait_process(handle: int, timeout_seconds: float, status_path: Path, progress) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    waited = 0.0
    while waited < timeout_seconds:
        code = kernel32.WaitForSingleObject(wintypes.HANDLE(handle), 500)
        if code == 0:
            break
        waited += 0.5
        if status_path.is_file():
            progress("驱动安装程序正在收尾…")
        elif waited in (2.0, 10.0, 30.0):
            progress("等待管理员授权完成驱动安装…")
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _read_status(status_path: Path) -> dict:
    if not status_path.is_file():
        raise DriverError("驱动安装没有返回结果，可能被取消了管理员授权。")
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DriverError("驱动安装结果无法解析：%s" % exc) from exc


def install(pids, progress=lambda message: None, timeout_seconds: float = 180.0) -> dict:
    """为给定 PID 安装 WinUSB；已就绪的 PID 会被跳过。"""
    wanted = []
    for pid in pids:
        if not supported(pid):
            raise DriverError("驱动安装只支持相机 PID 0x0E76、0x047D 与 0x0336。")
        state = setupapi.driver_state(pid)
        if state["present"] and state["winusb"]:
            progress("%s 的 USB 驱动已经就绪，跳过安装。" % PID_TITLES[pid])
            continue
        wanted.append(pid)
    if not wanted:
        return dict(driver_changed=False, pids=[], skipped=list(pids))

    executable = ensure_wdi(progress)
    if not executable.is_file():
        raise DriverError("缺少驱动安装组件 wdi-simple.exe，请重新解压安装包，或在“驱动准备”页点“下载驱动组件”。")

    job_dir = paths.driver_dir() / ("job-%s" % uuid.uuid4().hex[:12])
    job_dir.mkdir(parents=True, exist_ok=True)
    request_path = job_dir / "request.json"
    status_path = job_dir / "status.json"
    request_path.write_text(
        json.dumps(
            dict(
                pids=wanted,
                executable=str(executable),
                destination=str(paths.driver_dir()),
                status_path=str(status_path),
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if is_admin():
        progress("已具备管理员权限，直接安装驱动…")
        _run_wdi_request(request_path)
    else:
        progress("需要管理员授权以安装 USB 驱动，请在弹出的系统窗口点击“是”…")
        handle = _shell_execute_runas(_self_command(request_path), str(job_dir))
        _wait_process(handle, timeout_seconds, status_path, progress)

    status = _read_status(status_path)
    if not status.get("ok"):
        raise DriverError(status.get("error") or "驱动安装失败。")
    progress("驱动安装完成，正在确认绑定结果…")
    changed = False
    for pid in wanted:
        for _ in range(20):
            state = setupapi.driver_state(pid)
            if state["winusb"]:
                changed = True
                break
            time.sleep(0.5)
    return dict(driver_changed=changed, pids=wanted, results=status.get("results", []))


def _run_wdi_request(request_path: Path) -> dict:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    status_path = Path(request["status_path"])
    results = []
    ok = True
    error = ""
    try:
        for pid in request["pids"]:
            command = driver_arguments(request["executable"], int(pid), request["destination"])
            completed = subprocess.run(  # noqa: S603 - 参数由本模块构造
                command,
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=CREATE_NO_WINDOW,
            )
            results.append(
                dict(
                    pid=int(pid),
                    returncode=completed.returncode,
                    stdout=(completed.stdout or "")[-4000:],
                    stderr=(completed.stderr or "")[-2000:],
                )
            )
            if completed.returncode != 0:
                ok = False
                error = "安装 0x%04X 的驱动时返回 %d。请确认相机已连接，或重启后重试。" % (
                    int(pid),
                    completed.returncode,
                )
                break
    except Exception as exc:  # noqa: BLE001 - 失败要写入状态文件而不是只抛给子进程
        ok = False
        error = str(exc)
    payload = dict(ok=ok, error=error, results=results)
    status_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def run_elevated_worker(request_path: str) -> int:
    """--elevated-worker 入口：以管理员身份执行安装并把结果写入 status.json。"""
    payload = _run_wdi_request(Path(request_path))
    return 0 if payload.get("ok") else 1


def ensure_pid(pid: int, progress=lambda message: None) -> dict:
    """确保某个 PID 已绑定 WinUSB；已经就绪时不做任何写操作。"""
    if not supported(pid):
        return dict(driver_changed=False, pids=[], skipped=[pid])
    state = setupapi.driver_state(pid)
    if state["present"] and state["winusb"]:
        return dict(driver_changed=False, pids=[], skipped=[pid])
    if not wdi_available():
        raise DriverError(
            "尚未准备 USB 驱动组件。请打开“驱动准备”页下载一次，然后重新连接相机。"
        )
    return install([pid], progress)


def wait_for_pid(pid: int, timeout_seconds: float = 20.0, progress=lambda message: None) -> bool:
    """等待某个 PID 出现在 PnP 列表里（相机重新枚举需要一点时间）。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if setupapi.driver_state(pid)["present"]:
            return True
        time.sleep(0.25)
    return False
