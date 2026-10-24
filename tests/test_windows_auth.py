"""Windows 认证前置检查：驱动补绑与「找不到相机」的说明。

这两个函数解决的是同一类投诉：相机明明连着，只读检查却停在
「USB 认证失败（正在寻找唯一的 MSC 相机…）」。
"""
from __future__ import annotations

import pytest

from a6700win.usb import driver, setupapi, windows_auth


class FakeLegacy:
    class ProbeError(RuntimeError):
        pass


def test_prepare_storage_driver_binds_unbound_camera(monkeypatch):
    bound = []
    monkeypatch.setattr(
        setupapi, "driver_state",
        lambda pid, vendor=None: dict(present=(pid == 0x0E76), winusb=False))
    monkeypatch.setattr(
        driver, "ensure_pid",
        lambda pid, progress: bound.append(pid) or dict(driver_changed=True))

    windows_auth.prepare_storage_driver(FakeLegacy, lambda _message: None)

    assert bound == [0x0E76]


def test_prepare_storage_driver_skips_bound_camera(monkeypatch):
    bound = []
    monkeypatch.setattr(
        setupapi, "driver_state",
        lambda pid, vendor=None: dict(present=True, winusb=True))
    monkeypatch.setattr(driver, "ensure_pid",
                        lambda pid, progress: bound.append(pid))

    windows_auth.prepare_storage_driver(FakeLegacy, lambda _message: None)

    assert bound == []


def test_prepare_storage_driver_reports_driver_failure(monkeypatch):
    monkeypatch.setattr(
        setupapi, "driver_state",
        lambda pid, vendor=None: dict(present=(pid == 0x0E76), winusb=False))

    def refuse(_pid, _progress):
        raise driver.DriverError("用户取消了管理员授权")

    monkeypatch.setattr(driver, "ensure_pid", refuse)

    with pytest.raises(FakeLegacy.ProbeError) as excinfo:
        windows_auth.prepare_storage_driver(FakeLegacy, lambda _message: None)

    message = str(excinfo.value)
    assert "0x0E76" in message
    assert "驱动准备" in message


def test_observed_devices_hint_names_wrong_mode(monkeypatch):
    monkeypatch.setattr(setupapi, "devices",
                        lambda vendor=None: [dict(pid=0x0EA6, service="winusb")])
    monkeypatch.setattr(setupapi, "service_for_pid",
                        lambda pid, vendor=None: "winusb")

    hint = windows_auth.observed_devices_hint()

    assert "0x0EA6" in hint
    assert "不是存储模式" in hint
    assert "winusb" in hint


def test_observed_devices_hint_when_nothing_connected(monkeypatch):
    monkeypatch.setattr(setupapi, "devices", lambda vendor=None: [])

    assert "没有看到任何索尼 USB 设备" in windows_auth.observed_devices_hint()
