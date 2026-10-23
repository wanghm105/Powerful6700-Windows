"""Windows 版 USB 认证流程：与上游 run_authentication 等价，但补齐 WinUSB 驱动准备。

上游 legacy.run_authentication 只在 macOS/Linux 上可用：
- libusb 路径解析没有 Windows 分支；
- 打开 Sony 设备前没有把 PID 绑定到 WinUSB；
- 进入服务模式后 0x0336 是新枚举的设备，需要第二次驱动准备。

本模块提供同名同签名的替代实现，由 a6700win.patches 注入到 legacy 模块。
所有 ProbeError 文案与上游保持一致（上游的重试逻辑依赖
"no Sony MSC device" 前缀），并且绝不向 stdout 打印任何内容。
"""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

from . import driver

SONY_VENDOR_ID = 0x054C
SERVICE_PID = 0x0336
MSC_PIDS = driver.MSC_PIDS


def _legacy():
    from a6700_unlock.usb import legacy

    return legacy


def libusb_library_path() -> str:
    """优先使用 libusb-package 自带的 libusb-1.0.dll。"""
    try:
        import libusb_package

        path = Path(libusb_package.get_library_path())
        if path.is_file():
            return str(path)
    except Exception:  # noqa: BLE001 - 缺包时继续尝试其它位置
        pass
    for candidate in (
        Path(sys.executable).parent / "libusb-1.0.dll",
        Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "libusb-1.0.dll",
    ):
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(
        "libusb-1.0.dll was not found. Reinstall this application, "
        "or install the libusb-package wheel with: pip install libusb-package"
    )


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _prepare(pid: int, progress, label: str) -> bool:
    """把 PID 绑定到 WinUSB，返回是否发生了驱动切换（即需要重新取设备句柄）。"""
    result = driver.ensure_pid(pid, progress)
    if result.get("driver_changed"):
        progress("%s 的 USB 驱动已切换为 WinUSB，等待设备重新枚举…" % label)
        return True
    return False


def _wait_service(legacy, initial_pid, service_pid, deadline, progress):
    """等 0x0336 出现：先用 SetupAPI，再绑 WinUSB，最后交给 libusb。

    服务模式是相机自己重新枚举出来的新设备。Windows 上它一开始没有任何驱动
    （设备管理器里 CM 状态 28 = 驱动未安装），此时 libusb 根本枚举不到它，
    legacy.wait_for_service_device() 会一直等到超时并报
    "Sony bulk product IDs seen: "（后面是空的）。所以必须先靠 SetupAPI 发现 PID，
    再跑一次 wdi-simple 绑定 WinUSB，之后 libusb 才看得到。
    """
    from . import setupapi

    target = int(service_pid or SERVICE_PID)
    while True:
        pids = setupapi.present_pids()
        if target in pids:
            break
        if time.monotonic() >= deadline:
            raise legacy.ProbeError(
                "service-mode device did not appear (expected 0x%04x); "
                "Sony bulk product IDs seen: %s"
                % (target, " ".join("0x%04x" % pid for pid in pids))
            )
        time.sleep(0.1)

    if not setupapi.driver_state(target)["winusb"]:
        progress("相机已进入服务模式（0x%04x），正在为它准备 WinUSB 驱动…" % target)
        try:
            driver.ensure_pid(target, progress)
        except driver.DriverError as exc:
            raise legacy.ProbeError(
                "服务模式设备 0x%04x 已出现，但没能为它安装 WinUSB 驱动：%s" % (target, exc)
            ) from exc

    try:
        return legacy.wait_for_service_device(initial_pid, target, max(5.0, _remaining(deadline)))
    except legacy.ProbeError as exc:
        raise legacy.ProbeError(
            "%s（0x%04x 已绑定 WinUSB，但 libusb 仍未枚举到它；可拔插 USB 后重试）" % (exc, target)
        ) from exc

def _recover_service_mode(legacy, initial_pid, service_pid, progress) -> bool:
    """相机上次失败后被留在服务模式（0x0336）时，先把它带回存储模式。

    真机上这很常见：一次失败的认证会让相机停在 0x0336，而且它没有驱动、
    libusb 看不到，于是下一次运行只会在寻找 MSC 相机这一步就报
    "no Sony MSC device found"。此时唯一能做的就是给 0x0336 装 WinUSB、
    发一次 STOP_SENSER，等它重新枚举回 0x0E76。
    """
    from . import setupapi

    target = int(service_pid or SERVICE_PID)
    pids = setupapi.present_pids()
    if target not in pids:
        return False
    if initial_pid and int(initial_pid) in pids:
        return False

    progress("相机仍停留在服务模式（0x%04x），正在尝试退出服务模式…" % target)
    if not setupapi.driver_state(target)["winusb"]:
        try:
            driver.ensure_pid(target, progress)
        except driver.DriverError as exc:
            raise legacy.ProbeError(
                "相机停留在服务模式（0x%04x），但无法为它安装 WinUSB 驱动：%s；"
                "请拔插 USB 数据线后再试。" % (target, exc)
            ) from exc

    device = legacy.wait_for_service_device(initial_pid, target, 8.0)
    opened = legacy.open_target(device)
    try:
        try:
            legacy.authenticate_target(opened)
        except Exception:
            pass
        legacy.vendor_request_out(opened.device, legacy.STOP_SENSER, strict=False)
    finally:
        legacy.close_target(opened)

    wait_until = time.monotonic() + 10.0
    while time.monotonic() < wait_until:
        if target not in setupapi.present_pids():
            progress("已退出服务模式，继续正常流程。")
            return True
        time.sleep(0.25)
    raise legacy.ProbeError(
        "相机仍停留在服务模式（0x%04x），自动退出未成功；请拔插 USB 数据线后再试。" % target
    )


def run_authentication(
    initial_pid,
    service_pid,
    timeout_seconds,
    read_product_info,
    progress=lambda message: None,
):
    """Windows 版两段式 Senser 认证：MSC 设备 → 服务模式设备。"""
    legacy = _legacy()
    deadline = time.monotonic() + float(timeout_seconds)

    progress("正在寻找唯一的 MSC 相机…")
    _recover_service_mode(legacy, initial_pid, service_pid, progress)
    while True:
        try:
            initial_device = legacy.choose_initial_device(initial_pid)
            break
        except legacy.ProbeError as exc:
            if not str(exc).startswith("no Sony MSC device") or time.monotonic() >= deadline:
                raise
            time.sleep(0.25)

    if _prepare(int(initial_device.idProduct), progress, "相机存储模式"):
        initial_device = legacy.choose_initial_device(initial_pid)

    initial_target = legacy.open_target(initial_device)
    try:
        progress("正在进行第一次 USB 认证…")
        legacy.authenticate_target(initial_target)
    finally:
        legacy.close_target(initial_target)

    progress("正在等待相机进入服务模式…")
    service_device = _wait_service(legacy, initial_pid, service_pid, deadline, progress)

    service_target = legacy.open_target(service_device)
    try:
        progress(
            "正在进行第二次 USB 认证（接口类别 0x%02x）…" % service_target.interface.bInterfaceClass
        )
        legacy.authenticate_target(service_target)
        channel = legacy.SenserChannel(service_target)
        if read_product_info:
            progress("正在确认相机服务响应…")
            code, _body = channel.send(0x10, struct.pack("<HH", 0, 0x001F) + b"\x00")
            if code != 1:
                raise legacy.ProbeError("ProductInfo response code was %d" % code)
        return service_target, channel
    except BaseException as original:
        try:
            legacy.vendor_request_out(service_target.device, legacy.STOP_SENSER, strict=True)
        except BaseException:  # noqa: BLE001 - 退出失败只做提示，不覆盖原始异常
            original.cleanup_warning = "退出服务模式未获确认，请拔插 USB"
            add_note = getattr(original, "add_note", None)
            if callable(add_note):
                add_note("退出服务模式未获确认，请拔插 USB")
        finally:
            legacy.close_target(service_target)
        raise


def observed_sony_product_ids():
    """用 SetupAPI 观察 Sony PID：不需要 libusb，未装 WinUSB 也能读到。"""
    from . import setupapi

    try:
        return setupapi.present_pids()
    except Exception:  # noqa: BLE001 - 枚举失败等价于“看不到设备”
        return []


def normal_mode_observed(timeout_seconds: float = 3.0) -> bool:
    from . import setupapi

    deadline = time.monotonic() + float(timeout_seconds)
    while True:
        try:
            pids = setupapi.present_pids()
        except Exception:  # noqa: BLE001
            return False
        if pids == [0x0E76]:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
