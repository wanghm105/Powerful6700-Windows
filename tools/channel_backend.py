"""把 legacy.SenserChannel 包成 a6700win.flash 需要的 backend 形状。"""
from __future__ import annotations

import struct


class ChannelBackend:
    """flash 模块要的是 _command(command, payload) / _file(command, ident, data)。"""

    def __init__(self, channel):
        self.channel = channel

    def _command(self, command, payload):
        code, body = self.channel.send(0x40, struct.pack("<HH", 0x1001, command) + payload)
        if code != 0:
            raise RuntimeError(f"USB 服务命令失败：0x{command:04x}, code={code}")
        return body

    def _file(self, command, ident, data):
        body = self._command(command, bytes([0, ident, 0]) + data)
        if len(body) != 4 or body != b"\0" * 4:
            raise RuntimeError("文件写入或载荷执行失败，状态：" + body[:16].hex())
