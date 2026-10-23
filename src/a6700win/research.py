"""机身只读读取的连接编排：认证一次服务通道，读完文件，确保退出服务模式。

这一层只做两件事：拿通道、用通道读文件；任何写操作都不在这里出现。
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from . import dump, paths

SERVICE_PID = 0x0336
DEFAULT_TIMEOUT = 12.0


class ResearchError(RuntimeError):
    """连接或读取失败；消息直接面向用户。"""


class ServiceSession:
    """一次认证、可多次读取的服务通道会话；退出时一定尝试 STOP_SENSER。

    同时实现 UsbBackend 的最小只读子集（_file/_command），因此 dump 载荷协议
    可以直接复用；没有任何写路径。
    """

    def __init__(self, progress=lambda message: None, timeout_seconds: float = DEFAULT_TIMEOUT):
        self.progress = progress
        self.timeout_seconds = timeout_seconds
        self.legacy = None
        self.target = None
        self.channel = None
        self.cleanup_status = None
        self.cleanup_warning = None

    # -- 连接 ---------------------------------------------------------
    def __enter__(self):
        paths.ensure_vendor_on_path()
        from . import patches

        # 必须装补丁：legacy 的 libusb 解析与认证流程都靠它换成 Windows 实现。
        patches.install()
        from a6700_unlock.usb import legacy

        self.legacy = legacy
        from .usb import windows_auth

        self.progress("正在认证相机 USB 服务模式…")
        try:
            self.target, self.channel = windows_auth.run_authentication(
                None, SERVICE_PID, self.timeout_seconds, True, progress=self.progress
            )
        except Exception as exc:  # noqa: BLE001 - 统一成面向用户的消息
            self.cleanup_warning = getattr(exc, "cleanup_warning", None)
            raise ResearchError(f"USB 认证失败：{exc}") from exc
        return self

    def __exit__(self, *_exc_info):
        if self.target is not None:
            try:
                self.legacy.vendor_request_out(self.target.device, self.legacy.STOP_SENSER, strict=True)
                self.cleanup_status = "stop-sent"
            except Exception as exc:  # noqa: BLE001 - 退出失败只记录
                self.cleanup_status = "unconfirmed"
                self.cleanup_warning = f"无法确认退出服务模式，请拔插 USB：{exc}"
            finally:
                try:
                    self.legacy.close_target(self.target)
                except Exception:  # noqa: BLE001 - 释放失败不影响结果
                    pass
        return False

    # -- UsbBackend 只读子集 ------------------------------------------
    def _command(self, command: int, payload: bytes) -> bytes:
        code, body = self.channel.send(
            0x40, struct.pack("<HH", 0x1001, command) + payload
        )
        if code:
            raise dump.DumpError(f"USB 服务命令失败：0x{command:04x}, code={code}")
        return body

    def _file(self, command: int, ident: int, data: bytes) -> None:
        body = self._command(command, bytes([0, ident, 0]) + data)
        if len(body) != 4 or body != b"\0" * 4:
            raise dump.DumpError("文件写入或载荷执行失败，状态：" + body[:16].hex())

    # -- 读取 ---------------------------------------------------------
    def read(self, absolute_path: str):
        return dump.camera_file(self.channel, absolute_path)

    def stat(self, absolute_path: str) -> int:
        return dump.stat(self, absolute_path)

    def read_range(self, absolute_path: str, offset: int, length: int) -> dict:
        return dump.read_range(self, absolute_path, offset, length)

    def dump(self, absolute_path: str, output: Path, offset: int = 0, limit: int | None = None,
             chunk: int | None = None) -> dict:
        options = dict(progress=self.progress, offset=offset, limit=limit)
        if chunk:
            options["chunk"] = chunk
        return dump.dump(self, absolute_path, output, **options)


def read_file_to(
    absolute_path: str,
    output: Path,
    progress=lambda message: None,
    offset: int = 0,
    limit: int | None = None,
    chunk: int | None = None,
) -> dict:
    """认证之后把相机上的一个文件完整读回本机，并写好 .json 报告。"""
    with ServiceSession(progress) as session:
        report = session.dump(absolute_path, output, offset=offset, limit=limit, chunk=chunk)
        report["cleanup_status"] = session.cleanup_status
        if session.cleanup_warning:
            report["cleanup_warning"] = session.cleanup_warning
    Path(str(output) + ".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report

