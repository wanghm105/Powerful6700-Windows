"""Windows 适配补丁：幂等、可枚举，且不放宽真正写到相机的字节校验。"""
from __future__ import annotations

import dataclasses

import pytest

from a6700win import patches
from a6700win.usb import setupapi


EXPECTED = {
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
    "controller.available_backups",
    "controller.restore_scope",
    "device_profile.inspect_sectors",
    "operations.inspect_sectors",
}


def test_install_is_idempotent():
    assert set(patches._PATCH_NAMES) == EXPECTED
    first = patches.install()
    second = patches.install()
    # 本用例可能在任何已安装补丁的用例之后运行，因此只断言"不会再装第二次"。
    assert set(first["applied"]) <= EXPECTED
    assert second["applied"] == []
    assert EXPECTED.issubset(set(second["already"]))


def test_install_replaces_behaviour_not_just_names():
    patches.install()
    from a6700_unlock.usb import legacy

    assert legacy.observed_sony_product_ids() == setupapi.present_pids()
    assert legacy.normal_mode_observed(0.1) is (setupapi.present_pids() in ([0x0E76], [0x047D]))


def test_libusb_resolver_points_at_installed_dll():
    path = patches.windows_auth.libusb_library_path()
    assert path.lower().endswith("libusb-1.0.dll")


def test_status_exposes_driver_and_payload_provenance():
    status = patches.status()
    assert status["platform"] == "win32"
    assert status["libusb"]["ok"] is True
    assert set(status) >= {"platform", "python", "installed", "paths", "libusb", "driver", "devices", "payload_source"}
    assert status["devices"]["available"] is True
    provenance = status["payload_source"]
    assert set(provenance) == {"expected", "actual", "matches", "checked"}
    assert provenance["checked"] is True
    # 上游清单里的 source_sha256 与仓库自带 transaction.c 不一致，属已知上游问题。
    assert provenance["matches"] is False


def test_payloads_verify_real_assets_and_reject_a_foreign_profile():
    from a6700_unlock.catalog import load_catalog
    from a6700_unlock.desktop import controller as controller_module
    from a6700_unlock.device_profile import load_device_profile

    profile = load_device_profile(load_catalog())
    patches.install()
    assets = controller_module.payloads(profile)
    assert set(assets) == {"reader", "writer"}
    assert len(assets["reader"]) == 26992
    assert len(assets["writer"]) == 27088

    broken = dataclasses.replace(profile, digest="0" * 64)
    with pytest.raises(Exception) as excinfo:
        controller_module.payloads(broken)
    assert "do not match" in str(excinfo.value)


def test_backup_listing_is_available_without_an_active_action():
    patches.install()
    from a6700_unlock.desktop import controller as controller_module

    class FakeService:
        class profile:
            digest = "abc"

        def list_backups(self):
            return [{"id": "good", "profile_sha256": "abc"},
                    {"id": "other", "profile_sha256": "zzz"}]

    holder = type("Holder", (), {})()
    holder.service = FakeService()
    holder.mode = "physical"
    holder.action = ""
    rows = controller_module.DesktopController._available_backups(holder)
    assert [row["id"] for row in rows] == ["good"]


def test_restore_scope_expands_to_every_available_feature():
    from a6700win import windows_shim

    seen = {}

    class FakeCatalog:
        available_features = ["ftp", "shutter", "exposure", "sound"]

    class FakeProfile:
        catalog = FakeCatalog()

    class FakeService:
        profile = FakeProfile()

    class Holder:
        action = "restore"
        service = FakeService()
        selected_features = {"sound"}

    def original(self, progress):
        seen["features"] = set(self.selected_features)

    holder = Holder()
    windows_shim.wrap_restore_scope(original)(holder, lambda _m: None)
    assert seen["features"] == {"ftp", "shutter", "exposure", "sound"}
    assert holder.selected_features == {"sound"}


def test_restore_can_be_reserved_without_a_selection():
    """相机全开时 selected_features 为空，恢复仍应能预约到备份校验这一步。"""
    from a6700win import windows_shim

    class FakeCatalog:
        available_features = ["ftp", "shutter"]

    class FakeProfile:
        catalog = FakeCatalog()

    class Holder:
        service = type("S", (), {"profile": FakeProfile()})()
        selected_features = set()

    seen = {}
    holder = Holder()

    def original(self, action, backup_id=None):
        seen["action"] = action
        seen["selection"] = set(self.selected_features)
        seen["backup"] = backup_id

    windows_shim.wrap_reserve(original)(holder, "restore", "backup-id")
    assert seen == dict(action="restore", selection={"ftp", "shutter"}, backup="backup-id")


def test_preimage_rejection_is_not_reported_as_readback_failure():
    """status=1 且零字节写入 → rejected，不是“独立回读失败”。"""
    wrapped = patches._wrap_session(lambda *_a, **_k: dict(
        status="verification-failed",
        write_attempted=True,
        native_result=dict(status=1, touched=0, error="preimage changed")))
    result = wrapped()
    assert result["status"] == "rejected"
    assert result["error"] == "preimage changed"


def test_payload_rejection_names_the_step_and_status():
    """相机拒绝载荷时，错误里要能看出是哪一步、状态码是多少。"""
    from a6700_unlock.device_protocol import DeviceError

    class Rejecting:
        def _command(self, command, payload):
            return b"\x04\x00\x00\x10"

    class Accepting:
        def _command(self, command, payload):
            return b"\0\0\0\0"

    with pytest.raises(DeviceError) as excinfo:
        patches._windows_backend_file(Rejecting(), 0x4007, 2, b"payload")
    message = str(excinfo.value)
    assert "载荷写入" in message
    assert "0x10000004" in message
    assert "04000010" in message

    assert patches._windows_backend_file(Accepting(), 0x4010, 0, b"") is None
