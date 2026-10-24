r"""SetupAPI 层：只读枚举 USB\VID_054C&PID_xxxx 设备，不打开设备、不初始化 USB。

只依赖 ctypes，因此在没有 libusb、没有 WinUSB 驱动、也没有管理员权限时同样可用，
用来回答两个问题：
1. 现在插着哪些 Sony 相机 PID（判断存储模式 / 服务模式）；
2. 某个 PID 当前绑定的是哪个内核驱动（判断是否需要安装 WinUSB）。
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes

SONY_VENDOR_ID = 0x054C
DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004
SPDRP_DEVICEDESC = 0x00000000
SPDRP_SERVICE = 0x00000004
SPDRP_FRIENDLYNAME = 0x0000000C
CR_SUCCESS = 0
CR_NO_SUCH_DEVNODE = 0x0000000D
CM_PROB_FAILED_START = 10

WINUSB_SERVICES = frozenset({"winusb", "libusb0", "libusbk"})

_INSTANCE_PATTERN = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", re.IGNORECASE)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


def parse_instance_id(instance_id: str) -> dict:
    """从设备实例 ID 解析 vid/pid；非 USB 或不含 vid/pid 时返回空字段。"""
    row = {"vid": None, "pid": None}
    if not instance_id:
        return row
    match = _INSTANCE_PATTERN.search(instance_id)
    if match:
        row["vid"] = int(match.group(1), 16)
        row["pid"] = int(match.group(2), 16)
    return row


def normalize_service(name: str) -> str:
    return (name or "").strip().lower()


def is_winusb_service(name: str) -> bool:
    return normalize_service(name) in WINUSB_SERVICES


def _setupapi():
    api = ctypes.WinDLL("setupapi", use_last_error=True)
    api.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    api.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    api.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    api.SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
    api.SetupDiGetDeviceInstanceIdW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(SP_DEVINFO_DATA),
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.SetupDiGetDeviceRegistryPropertyW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(SP_DEVINFO_DATA),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    return api


def _cfgmgr():
    api = ctypes.WinDLL("cfgmgr32", use_last_error=True)
    api.CM_Get_DevNode_Status.argtypes = [
        ctypes.POINTER(wintypes.ULONG),
        ctypes.POINTER(wintypes.ULONG),
        wintypes.DWORD,
        wintypes.ULONG,
    ]
    return api


def _read_string(api, handle, info, property_id: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    needed = wintypes.DWORD(0)
    ok = api.SetupDiGetDeviceRegistryPropertyW(
        handle,
        ctypes.byref(info),
        property_id,
        None,
        ctypes.cast(buffer, ctypes.c_void_p),
        ctypes.sizeof(buffer),
        ctypes.byref(needed),
    )
    if not ok:
        return ""
    return buffer.value.strip()


def _node_status(cfgmgr, devinst: int) -> tuple[str, int]:
    status = wintypes.ULONG(0)
    problem = wintypes.ULONG(0)
    code = cfgmgr.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), devinst, 0)
    if code == CR_NO_SUCH_DEVNODE:
        return "Missing", 0
    if code != CR_SUCCESS:
        return "Unknown", 0
    return ("OK" if problem.value == 0 else "Error"), int(problem.value)


def devices(vendor: int = SONY_VENDOR_ID) -> list[dict]:
    """枚举当前在场的 Sony USB 设备（默认 VID 0x054C）。"""
    if not sys.platform.startswith("win"):
        raise OSError("SetupAPI 枚举仅在 Windows 上可用。")
    api = _setupapi()
    cfgmgr = _cfgmgr()
    handle = api.SetupDiGetClassDevsW(None, "USB", None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise OSError("SetupDiGetClassDevsW 失败。")
    rows: list[dict] = []
    try:
        index = 0
        while True:
            info = SP_DEVINFO_DATA()
            info.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not api.SetupDiEnumDeviceInfo(handle, index, ctypes.byref(info)):
                break
            index += 1
            buffer = ctypes.create_unicode_buffer(512)
            needed = wintypes.DWORD(0)
            if not api.SetupDiGetDeviceInstanceIdW(
                handle, ctypes.byref(info), buffer, ctypes.sizeof(buffer), ctypes.byref(needed)
            ):
                continue
            instance_id = buffer.value
            parsed = parse_instance_id(instance_id)
            if parsed["vid"] != vendor:
                continue
            status, problem = _node_status(cfgmgr, info.DevInst)
            rows.append(
                dict(
                    id=instance_id,
                    vid=parsed["vid"],
                    pid=parsed["pid"],
                    description=_read_string(api, handle, info, SPDRP_DEVICEDESC),
                    name=_read_string(api, handle, info, SPDRP_FRIENDLYNAME),
                    service=_read_string(api, handle, info, SPDRP_SERVICE),
                    status=status,
                    problem=problem,
                )
            )
    finally:
        api.SetupDiDestroyDeviceInfoList(handle)
    return rows


def present_pids(vendor: int = SONY_VENDOR_ID) -> list[int]:
    """在场 Sony 设备的 PID 列表（升序、去重）。"""
    pids = {row["pid"] for row in devices(vendor) if row.get("pid") is not None}
    return sorted(pids)


def rows_for_pid(pid: int, vendor: int = SONY_VENDOR_ID) -> list[dict]:
    return [row for row in devices(vendor) if row.get("pid") == pid]


def service_for_pid(pid: int, vendor: int = SONY_VENDOR_ID) -> str:
    """返回该 PID 的驱动服务名（小写）；出现多个实例时返回第一个非空值。"""
    for row in rows_for_pid(pid, vendor):
        service = normalize_service(row.get("service"))
        if service:
            return service
    return ""


def driver_state(pid: int, vendor: int = SONY_VENDOR_ID) -> dict:
    rows = rows_for_pid(pid, vendor)
    services = sorted({normalize_service(row.get("service")) for row in rows if row.get("service")})
    bound = [name for name in services if is_winusb_service(name)]
    return dict(
        pid=pid,
        present=bool(rows),
        count=len(rows),
        services=services,
        winusb=bool(bound),
        rows=rows,
    )


def summary() -> dict:
    """给 GUI/自检用的紧凑状态：哪些 Sony PID 在场、各自驱动绑定情况。"""
    try:
        pids = present_pids()
    except Exception as exc:  # noqa: BLE001 - 枚举失败要作为数据返回而不是抛出
        return dict(available=False, error=str(exc), pids=[], devices=[])
    return dict(
        available=True,
        error="",
        pids=pids,
        devices=[
            # 复合设备（父节点 + 接口节点）必须按“任意节点已绑定”判定，
            # 否则驱动页会一直说没绑定，而 install() 又认为已经就绪。
            dict(pid=pid, service=service_for_pid(pid),
                 services=driver_state(pid)["services"],
                 winusb=driver_state(pid)["winusb"])
            for pid in pids
        ],
    )
