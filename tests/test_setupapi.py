"""SetupAPI 解析层：不碰 libusb，可在无相机、无管理员时验证。"""
from __future__ import annotations

from a6700win.usb import setupapi


def test_parse_instance_id_reads_vid_and_pid():
    row = setupapi.parse_instance_id("USB\\VID_054C&PID_0E76\\A1B2C3")
    assert row == {"vid": 0x054C, "pid": 0x0E76}


def test_parse_instance_id_accepts_uppercase_and_lowercase():
    assert setupapi.parse_instance_id("usb\\vid_054c&pid_0336#x")["pid"] == 0x0336


def test_parse_instance_id_returns_empty_fields_for_unknown_ids():
    assert setupapi.parse_instance_id("") == {"vid": None, "pid": None}
    assert setupapi.parse_instance_id("HID\\VID_046D&PID_C52B")["pid"] == 0xC52B
    assert setupapi.parse_instance_id("ROOT\\LEGACY_X") == {"vid": None, "pid": None}


def test_service_normalisation_matches_winusb_family():
    assert setupapi.is_winusb_service("WinUSB")
    assert setupapi.is_winusb_service(" libusbK ")
    assert setupapi.is_winusb_service("libusb0")
    assert not setupapi.is_winusb_service("usbccgp")
    assert not setupapi.is_winusb_service("")


def test_driver_state_shape_is_self_consistent():
    """有无相机都必须返回同一形状，且字段之间自洽（相机插着时不能假设空结果）。"""
    state = setupapi.driver_state(0x0E76)
    assert state["pid"] == 0x0E76
    assert set(state) == {"pid", "present", "count", "services", "winusb", "rows"}
    assert state["present"] is (state["count"] > 0)
    assert isinstance(state["services"], list)
    assert isinstance(state["winusb"], bool)
    assert len(state["rows"]) == state["count"]
    if not state["present"]:
        assert state["services"] == []
        assert state["winusb"] is False
    for row in state["rows"]:
        assert row["pid"] == 0x0E76


def test_summary_never_raises():
    summary = setupapi.summary()
    assert isinstance(summary, dict)
    assert "available" in summary and "devices" in summary
