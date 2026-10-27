"""只读检查里「配置写入被拒」的自愈路径：清掉 /tmp/jiritsu 残留后再试一次。"""
from __future__ import annotations

import struct

import pytest

from a6700win import dump, patches, paths


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    # 阶梯里的等待在测试里必须跳过，否则每个失败用例都要真等四秒多。
    monkeypatch.setattr(patches, "_sleep", lambda seconds: None)

paths.ensure_vendor_on_path()

from a6700_unlock.device_protocol import DeviceError  # noqa: E402


class _Channel:
    """Jiritsu 命令只要一个成功响应；内容这里不关心。"""

    def __init__(self):
        self.sent = []

    def send(self, pfunc, body):
        self.sent.append((pfunc, body))
        return 0, struct.pack("<I", 0)


class _Backend:
    def __init__(self, replies, channel=None):
        self.replies = list(replies)
        self.channel = channel
        self.messages = []
        self.commands = []

    def _command(self, command, payload):
        self.commands.append(command)
        if not self.replies:
            raise AssertionError("命令次数超出预期")
        return self.replies.pop(0)

    def progress(self, message):
        self.messages.append(message)


def _file_commands(channel):
    """只数文件命令；0x400D（读固件版本）与 0x4002（重挂分区）这类会话级命令不算。"""
    rows = []
    for pfunc, body in channel.sent:
        command = struct.unpack_from("<H", body, 2)[0]
        if command in (patches._VERSION_COMMAND, patches._MOUNT_COMMAND):
            continue
        rows.append((pfunc, body))
    return rows


def _service_commands(channel):
    """会话级的非文件命令：0x400D 读版本、0x4002 重挂分区。"""
    rows = []
    for _, body in channel.sent:
        command = struct.unpack_from("<H", body, 2)[0]
        if command in (patches._VERSION_COMMAND, patches._MOUNT_COMMAND):
            rows.append(command)
    return rows


def test_config_write_recovers_after_clearing_stale_temp():
    channel = _Channel()
    backend = _Backend([b"\x04\x00\x00\x10", b"\0" * 4], channel=channel)
    assert patches._windows_backend_file(backend, 0x4010, 0, b"config") is None
    # 两次配置写入：第一次被拒，清理后重试成功。
    assert backend.commands == [0x4010, 0x4010]
    # 清了两遍：写前主动一遍，被拒后重试前再一遍；每遍每个文件先 select 再 remove。
    sent = _file_commands(channel)
    assert len(sent) == 4 * len(patches._stale_paths())
    commands = [struct.unpack_from("<H", body, 2)[0] for _, body in sent]
    # 两条路径各 select+remove = 3 条路径 × 2 × 2 遍；删掉 libJit.so 后还要重挂一次。
    assert _service_commands(channel).count(patches._MOUNT_COMMAND) == 2
    assert commands[1::2] == [dump.CMD_REMOVE] * (2 * len(patches._stale_paths()))
    assert [body[4:] for _, body in sent][1::2] == [b"\0\xff"] * (2 * len(patches._stale_paths()))
    assert any("临时文件" in message for message in backend.messages)


def test_config_write_fails_with_recovery_hint_when_no_channel():
    backend = _Backend([bytes([4, 0, 0, 16])] * 9, channel=None)
    with pytest.raises(DeviceError) as info:
        patches._windows_backend_file(backend, 0x4010, 0, b"config")
    text = str(info.value)
    assert "配置写入（SET_FILE2）" in text
    assert "0x10000004" in text
    assert "取出电池" in text
    # 没有服务通道时清不掉东西，但重试照样要发一次，文案要说清这次会话没恢复干净。
    assert backend.commands == [0x4010] * 9
    assert "能想到的办法都试过了" in text


def test_first_config_write_clears_stale_temp_before_it_is_sent():
    """健康会话也要在第一条配置写入之前清一遍：残留正是它被拒的原因。"""
    channel = _Channel()
    backend = _Backend([b"\0" * 4], channel=channel)
    assert patches._windows_backend_file(backend, 0x4010, 0, b"config") is None
    assert len(_file_commands(channel)) == 2 * len(patches._stale_paths())
    assert backend.commands == [0x4010]
    assert any("临时文件" in message for message in backend.messages)


def test_second_config_write_in_the_same_session_does_not_clear_again():
    """清理是每会话一次；载荷会话里有多次 0x4010 时不必每次都清。"""
    channel = _Channel()
    backend = _Backend([b"\0" * 4, b"\0" * 4], channel=channel)
    assert patches._windows_backend_file(backend, 0x4010, 0, b"first") is None
    sent_after_first = len(channel.sent)
    assert patches._windows_backend_file(backend, 0x4010, 0, b"second") is None
    assert len(channel.sent) == sent_after_first
    assert backend.commands == [0x4010, 0x4010]


def test_payload_write_does_not_retry():
    backend = _Backend([b"\x04\x00\x00\x10"], channel=_Channel())
    with pytest.raises(DeviceError) as info:
        patches._windows_backend_file(backend, 0x4007, 2, b"elf")
    assert "载荷写入（SET_FILE）" in str(info.value)
    assert backend.commands == [0x4007]
