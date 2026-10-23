"""驱动准备层：参数拼装与 PID 白名单必须逐字稳定。"""
from __future__ import annotations

import pytest

from a6700win.usb import driver


def test_driver_arguments_exact():
    args = driver.driver_arguments("wdi-simple.exe", 0x0336, "C:/tmp/drv")
    assert args == [
        "wdi-simple.exe",
        "--vid",
        "0x054C",
        "--pid",
        "0x0336",
        "--type",
        "0",
        "--name",
        "Sony A6700 - Service",
        "--dest",
        "C:/tmp/drv",
        "--log",
        "0",
    ]


def test_driver_arguments_rejects_foreign_pid():
    with pytest.raises(ValueError) as excinfo:
        driver.driver_arguments("wdi-simple.exe", 0x0E8A, "C:/tmp/drv")
    assert str(excinfo.value) == "Driver installation is limited to camera PIDs 0E76, 047D and 0336"


def test_supported_pid_whitelist():
    assert driver.supported(0x047D)
    assert driver.supported(0x0E76)
    assert driver.supported(0x0336)
    assert not driver.supported(0x0E8A)
    assert not driver.supported(0x047E)


def test_scan_report_shape():
    """只报告真实枚举到的接口：没相机就是空列表，有相机就必须落在白名单 PID 上。"""
    report = driver.scan()
    assert report["platform"] == "win32"
    assert set(report) >= {"platform", "architecture", "admin", "wdi", "wdi_path", "devices", "driver_required"}
    assert isinstance(report["devices"], list)
    for row in report["devices"]:
        # 扫描会列出所有在场的 Sony 设备（含 HID 0x096F 这类非工具目标），
        # 用 supported 标记它是否属于本工具的三个 PID。
        assert isinstance(row["pid"], int)
        assert row["supported"] is (row["pid"] in driver.SUPPORTED_PIDS)
        assert isinstance(row["winusb"], bool)
        assert isinstance(row["service"], str)
    assert report["driver_required"] is any(
        row["supported"] and not row["winusb"] for row in report["devices"]
    )
    assert set(driver.PID_LABELS) == set(driver.SUPPORTED_PIDS)


def test_ensure_pid_explains_missing_component():
    if driver.wdi_available():
        pytest.skip("本机已下载驱动组件")
    if driver.setupapi.service_for_pid(0x0E76) and driver.setupapi.is_winusb_service(
        driver.setupapi.service_for_pid(0x0E76)
    ):
        pytest.skip("该 PID 已绑定 WinUSB")
    with pytest.raises(driver.DriverError) as excinfo:
        driver.ensure_pid(0x0E76, lambda message: None)
    assert "驱动准备" in str(excinfo.value)
