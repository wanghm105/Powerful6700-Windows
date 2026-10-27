"""Windows 适配补丁：幂等、可枚举，且不放宽真正写到相机的字节校验。"""
from __future__ import annotations

import dataclasses

import pytest

from a6700win import dump, patches


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    # 阶梯里的等待在测试里必须跳过，否则每个失败用例都要真等四秒多。
    monkeypatch.setattr(patches, "_sleep", lambda seconds: None)
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

def test_config_write_clears_temp_first_and_retries_once():
    """0x10000004：会话里第一条配置写入前先主动清一遍，被拒就无条件重试一次。"""
    from a6700win import dump

    events = []

    class Backend:
        channel = object()

        def __init__(self):
            self.answers = [b"\x04\x00\x00\x10", b"\0\0\0\0"]

        def _command(self, command, payload):
            events.append(("command", command))
            return self.answers.pop(0)

        def progress(self, message):
            events.append(("progress", message))

    cleaned = []
    original = dump.remove
    dump.remove = lambda channel, path: cleaned.append(path) or False  # 什么都没删到
    try:
        assert patches._windows_backend_file(Backend(), 0x4010, 0, b"") is None
    finally:
        dump.remove = original

    # 主动清一次 + 被拒后重试前再清一次，各两条路径
    assert cleaned == list(patches._stale_paths()) * 2
    assert [value for kind, value in events if kind == "command"] == [0x4010, 0x4010]
    assert any(kind == "progress" and "写入成功" in message for kind, message in events)


def test_config_write_names_the_dirty_session_after_two_rejections():
    """清两遍还是被拒 → 文案要说「会话没恢复干净」并提醒相机可能重复重启变砖。"""
    from a6700_unlock.device_protocol import DeviceError

    class Backend:
        channel = None

        def __init__(self):
            self.count = 0

        def _command(self, command, payload):
            self.count += 1
            return b"\x04\x00\x00\x10"

        def progress(self, message):
            pass

    backend = Backend()
    with pytest.raises(DeviceError) as excinfo:
        patches._windows_backend_file(backend, 0x4010, 0, b"")
    assert backend.count == 9, "被拒之后要把三种可能都试一遍，不能直接报错"
    message = str(excinfo.value)
    assert "能想到的办法都试过了" in message
    assert "变砖" in message



def test_stale_paths_include_libjit_so():
    """残留名单必须包含 libJit.so：/tmp/jiritsu 断电不消失，遗留的它会被固件重放。"""
    assert "/tmp/jiritsu/libJit.so" in patches._stale_paths()


class _ChannelBackend:
    channel = object()

def test_removing_libjit_remounts_the_partition_at_once(monkeypatch):
    """删掉 libJit.so 会让 Jiritsu 卸载 nflasha6：必须当场重挂，否则后面的写入必被拒。"""
    messages = []
    mounts = []

    monkeypatch.setattr(dump, "remove", lambda channel, path: path.endswith("libJit.so"))
    monkeypatch.setattr(patches, "_remount_jiritsu",
                        lambda channel: mounts.append(channel) or "成功")
    removed = patches._clear_stale_temp(_ChannelBackend(), messages.append)
    assert removed == ["/tmp/jiritsu/libJit.so"]
    assert mounts == [_ChannelBackend.channel]
    assert any("临时目录重新挂上：成功" in message for message in messages)


def test_failed_remount_is_reported_but_not_fatal(monkeypatch):
    messages = []
    monkeypatch.setattr(dump, "remove", lambda channel, path: path.endswith("libJit.so"))
    monkeypatch.setattr(patches, "_remount_jiritsu", lambda channel: "返回码 130（分区还没挂上）")
    removed = patches._clear_stale_temp(_ChannelBackend(), messages.append)
    assert removed == ["/tmp/jiritsu/libJit.so"]
    assert any("没挂上也不要紧" in message for message in messages)


def test_absent_libjit_does_not_remount(monkeypatch):
    """文件本来不在就别多发命令：健康相机上多一条 0x4002 也没必要。"""
    mounts = []
    monkeypatch.setattr(dump, "remove", lambda channel, path: path.endswith("tmmc.dat"))
    monkeypatch.setattr(patches, "_remount_jiritsu",
                        lambda channel: mounts.append(channel) or "成功")
    patches._clear_stale_temp(_ChannelBackend(), lambda message: None)
    assert mounts == []


def test_stale_temp_failure_is_reported(monkeypatch):
    """清理命令被拒要写进日志：以前异常被静默吞掉，日志里看不出删没删掉。"""
    messages = []

    def boom(channel, path):
        raise RuntimeError("Jiritsu 状态 0x10000004")

    monkeypatch.setattr(dump, "remove", boom)
    assert patches._clear_stale_temp(_ChannelBackend(), messages.append) == []
    assert any("清理临时文件失败" in message and "0x10000004" in message
               for message in messages)


def test_stale_temp_absence_is_reported(monkeypatch):
    """文件本来不在也要说一句：三种情况必须能从日志里分辨出来。"""
    messages = []
    monkeypatch.setattr(dump, "remove", lambda channel, path: False)
    assert patches._clear_stale_temp(_ChannelBackend(), messages.append) == []
    assert any("没有上次会话留下的临时文件" in message for message in messages)


def test_stale_temp_reports_what_was_removed(monkeypatch):
    messages = []
    monkeypatch.setattr(dump, "remove", lambda channel, path: path.endswith("tmmc.dat"))
    assert patches._clear_stale_temp(_ChannelBackend(), messages.append) == [
        "/tmp/jiritsu/tmmc.dat"]
    assert any("已清掉" in message and "tmmc.dat" in message for message in messages)


def test_probe_file_service_reports_success(monkeypatch):
    from a6700win import dump

    monkeypatch.setattr(dump, "camera_file", lambda channel, path, missing=False: bytes(16))
    text = patches._probe_file_service(object())
    assert "成功 16 字节" in text
    assert patches._PROBE_PATH in text


def test_probe_file_service_reports_missing_file(monkeypatch):
    from a6700win import dump

    monkeypatch.setattr(dump, "camera_file", lambda channel, path, missing=False: None)
    text = patches._probe_file_service(object())
    assert "0x10000006" in text


def test_probe_file_service_without_channel_says_so():
    assert "没有相机服务通道" in patches._probe_file_service(None)


def test_small_body_accepted_then_full_config_goes_through():
    """第 4 种：只写 1 个字节能过，说明相机要的是小正文，补完整配置后继续。"""
    class Backend:
        channel = None

        def __init__(self):
            self.answers = [b"\x04\x00\x00\x10"] * 5 + [b"\0" * 4, b"\0" * 4]
            self.count = 0

        def _command(self, command, payload):
            self.count += 1
            return self.answers.pop(0)

        def progress(self, message):
            pass

    backend = Backend()
    assert patches._windows_backend_file(backend, 0x4010, 0, b"config") is None
    assert backend.count == 7, "前五次全被拒，第六次 1 字节成功，第七次完整配置成功"


def test_long_wait_rescues_the_write():
    """第 6 种：多等 8 秒，有些机器把临时区挂得慢。"""
    class Backend:
        channel = None

        def __init__(self):
            self.answers = [b"\x04\x00\x00\x10"] * 8 + [b"\0" * 4]
            self.count = 0

        def _command(self, command, payload):
            self.count += 1
            return self.answers.pop(0)

        def progress(self, message):
            pass

    backend = Backend()
    assert patches._windows_backend_file(backend, 0x4010, 0, b"config") is None
    assert backend.count == 9


def test_inspect_temp_paths_reports_each_path(monkeypatch):
    """第 5 种：只读地把三个临时路径逐个定位一遍，被拒的写清是哪一个。"""
    from a6700win import dump

    seen = []

    def fake_select(channel, path, missing=False):
        seen.append(path)
        if path.endswith("tmmc.dat"):
            raise RuntimeError("Jiritsu 状态 0x10000004")

    monkeypatch.setattr(dump, "select", fake_select)
    text = patches._inspect_temp_paths(object())
    assert seen == list(patches._stale_paths())
    assert "tmmc.dat：Jiritsu 状态 0x10000004" in text
    assert "libJit.so：定位没被拒" in text
    assert "没有相机服务通道" in patches._inspect_temp_paths(None)

def test_error_message_is_numbered_lines_and_readable():
    # 错误正文要按层编号换行：挤成一大段没人读得下去（probe3 的现场截图）。
    from a6700_unlock.device_protocol import DeviceError

    class Backend:
        channel = None

        def _command(self, command, payload):
            return bytes([4, 0, 0, 16])

        def progress(self, message):
            pass

    with pytest.raises(DeviceError) as excinfo:
        patches._windows_backend_file(Backend(), 0x4010, 0, b"")
    message = str(excinfo.value)
    lines = message.split(chr(10))
    assert len(lines) >= 14
    numbered = [line for line in lines if line[:1].isdigit()]
    assert numbered and numbered[0].startswith("1. ")
    assert message.count("临时文件操作被拒") == 1
    assert "把这一页和日志一起发给我" in message


def test_version_text_reads_the_documented_layout():
    """0x400D 回 4 字节：大版本、次版本、保留、0x10（FX30 6.00 → 06 00 00 10）。"""
    assert patches._version_text(b"\x02\x00\x00\x10") == "固件版本 2.00（原始字节 02000010）"


def test_version_text_flags_the_status_code_lookalike():
    # 0x10000004 与「4.00」是同一串字节，得提醒一句，别把被拒读成版本。
    text = patches._version_text(b"\x04\x00\x00\x10")
    assert "4.00" in text and "0x10000004" in text


class _Senser:
    """最小相机通道替身：send(pf, payload) → (响应码, 正文)。"""

    def __init__(self, answer=bytes(4), code=0):
        self.answer = answer
        self.code = code
        self.sent = []

    def send(self, pf, payload):
        self.sent.append((pf, payload))
        return self.code, self.answer


def test_version_probe_reads_0x400d_and_names_the_version():
    channel = _Senser(b"\x02\x00\x00\x10")
    text = patches._probe_version(channel)
    assert "固件版本 2.00" in text
    assert channel.sent == [(0x40, b"\x01\x10\r@")], "category 0x1001 / command 0x400D"


def test_version_probe_says_so_without_a_channel():
    assert "没有相机服务通道" in patches._probe_version(None)


def test_version_probe_reports_a_rejected_command():
    assert "返回码 5" in patches._probe_version(_Senser(bytes(4), code=5))


def test_version_is_read_before_the_first_temp_clear(monkeypatch):
    from a6700win import dump

    order = []

    class Backend:
        channel = _Senser(b"\x02\x00\x00\x10")

        def _command(self, command, payload):
            return bytes(4)

        def progress(self, message):
            order.append(message)

    monkeypatch.setattr(dump, "remove",
                        lambda channel, path: order.append("remove") or False)
    assert patches._windows_backend_file(Backend(), 0x4010, 0, b"") is None
    assert order[0].startswith("先只读地问一句相机固件版本")
    assert "固件版本 2.00" in order[0]
    assert order.index("remove") > 0


def test_mount_rescues_the_write(monkeypatch):
    """第 5 种：重挂 nflasha6 分区（0x4002）之后再写一次。"""

    class Backend:
        channel = _Senser(b"\x02\x00\x00\x10")

        def __init__(self):
            self.count = 0
            self.messages = []

        def _command(self, command, payload):
            self.count += 1
            if self.count < 8:
                return bytes([4, 0, 0, 16])
            return bytes(4)

        def progress(self, message):
            self.messages.append(message)

    monkeypatch.setattr(patches, "_probe_file_service",
                        lambda channel: "读 /setting/BACKUP.BIN 失败：Jiritsu 状态 0x10000004")
    monkeypatch.setattr(patches, "_remount_jiritsu",
                        lambda channel: "成功")
    backend = Backend()
    assert patches._windows_backend_file(backend, 0x4010, 0, b"") is None
    assert any("重新挂上后写入成功" in message for message in backend.messages)


def test_mount_rejection_reaches_the_final_message(monkeypatch):
    from a6700_unlock.device_protocol import DeviceError

    class Backend:
        channel = _Senser(b"\x02\x00\x00\x10")

        def _command(self, command, payload):
            return bytes([4, 0, 0, 16])

        def progress(self, message):
            pass

    monkeypatch.setattr(patches, "_probe_file_service",
                        lambda channel: "读 /setting/BACKUP.BIN 失败：Jiritsu 状态 0x10000004")
    monkeypatch.setattr(patches, "_remount_jiritsu",
                        lambda channel: "返回码 130（130 表示分区还没挂上）")
    with pytest.raises(DeviceError) as excinfo:
        patches._windows_backend_file(Backend(), 0x4010, 0, b"")
    assert "重挂 /tmp/jiritsu 分区 —— 返回码 130" in str(excinfo.value)


def test_stale_temp_remounts_once_before_giving_up(monkeypatch):
    from a6700win import dump

    calls = []

    def flaky(channel, path):
        calls.append(path)
        if len(calls) == 1:
            raise RuntimeError("Jiritsu 状态 0x10000004")
        return True

    messages = []
    monkeypatch.setattr(dump, "remove", flaky)
    monkeypatch.setattr(patches, "_remount_jiritsu",
                        lambda channel: "成功")
    removed = patches._clear_stale_temp(_ChannelBackend(), messages.append)
    # 重挂成功之后，剩下两条也应该继续删掉（只重挂一次，不反复折腾分区）
    assert calls.count(patches._stale_paths()[0]) == 2
    assert removed == list(patches._stale_paths())
    assert any("先把相机的临时目录重新挂上" in message for message in messages)
