"""只读检查里「配置写入被拒」的自愈路径：清掉 /tmp/jiritsu 残留后再试一次。"""
from __future__ import annotations

import struct

import pytest

from a6700win import dump, patches, paths

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


def test_config_write_recovers_after_clearing_stale_temp():
    channel = _Channel()
    backend = _Backend([b"\x04\x00\x00\x10", b"\0" * 4], channel=channel)
    assert patches._windows_backend_file(backend, 0x4010, 0, b"config") is None
    # 两次配置写入：第一次被拒，清理后重试成功。
    assert backend.commands == [0x4010, 0x4010]
    # 清理动作走了 Jiritsu 的删除命令（cmd=18）：每个文件先 select 再 remove。
    assert len(channel.sent) == 2 * len(dump.TEMP_PATHS)
    commands = [struct.unpack_from("<H", body, 2)[0] for _, body in channel.sent]
    assert commands[1::2] == [dump.CMD_REMOVE] * len(dump.TEMP_PATHS)
    assert [body[4:] for _, body in channel.sent][1::2] == [b"\0\xff"] * len(dump.TEMP_PATHS)
    assert any("临时文件" in message for message in backend.messages)


def test_config_write_fails_with_recovery_hint_when_no_channel():
    backend = _Backend([b"\x04\x00\x00\x10"], channel=None)
    with pytest.raises(DeviceError) as info:
        patches._windows_backend_file(backend, 0x4010, 0, b"config")
    text = str(info.value)
    assert "配置写入（SET_FILE2）" in text
    assert "0x10000004" in text
    assert "取出电池" in text


def test_payload_write_does_not_retry():
    backend = _Backend([b"\x04\x00\x00\x10"], channel=_Channel())
    with pytest.raises(DeviceError) as info:
        patches._windows_backend_file(backend, 0x4007, 2, b"elf")
    assert "载荷写入（SET_FILE）" in str(info.value)
    assert backend.commands == [0x4007]
