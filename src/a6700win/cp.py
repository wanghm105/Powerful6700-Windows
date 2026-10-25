# -*- coding: utf-8 -*-
"""CP 单元读写（相机侧 RAM 里的色彩参数）。

协议：Senser 帧头 12 字节 '<IHHBBBB'，pFunc 0x40 (AdjustControl)，正文
    pack('<HH', 0x603, 0x40) + pack('<II', key, 1)            读
    pack('<HH', 0x603, 0x41) + pack('<II', key, 1) + data     写
读回复固定等于单元大小，并且要额外吃掉 0x200 的结束包，否则下一次读会错位。

只允许两个登记过的单元；写入只改 RAM，不碰 flash。关机时相机自己会把 RAM
写进 /setting/BACKUP.BIN，所以「写入成功」要在重启后再确认一次才叫持久。
"""
from __future__ import annotations

import os
import struct
import time
from contextlib import contextmanager

from . import patches, paths, windows_shim

CP_KEYS = {0x02A40001: 0x2000, 0x02A4000D: 0x7000}
ADJUST_READ = 0x40
ADJUST_WRITE = 0x41
SENSER_MIN = 0x200
SENSER_CHUNK = 0x8000
HEADER = 12
CHROMA_UNIT = 0x02A40001

# 两个服务会话之间必须留的冷却（秒）。实测紧接着开第二会话会让相机端点掉线，
# 间隔 60 秒就正常；取 50 秒留一点余量，可用环境变量覆盖以便现场调试。
SESSION_GAP = float(os.environ.get("POWERFUL6700_SESSION_GAP") or 50.0)


class CpError(RuntimeError):
    """CP 读写失败；调用方只报告，不自动重试。"""


class CpChannel:
    """在已认证的 Senser 通道上读/写 CP 单元。"""

    def __init__(self, target, channel):
        self.target = target
        self.channel = channel
        self.pending = bytearray()

    # ---------------------------------------------------------------- 底层
    def _end_packet(self):
        if self.pending:
            return
        try:
            data = self.target.device.read(self.target.endpoint_in, SENSER_MIN, timeout=1000)
        except Exception as exc:  # noqa: BLE001 - 超时是正常情况（有些固件不发空包）
            name = type(exc).__name__
            if name not in ("USBTimeoutError", "USBError"):
                raise
            if name == "USBError" and "timeout" not in str(exc).lower():
                raise
            return
        if data:
            self.pending.extend(data)

    def _read_nonempty(self, length):
        if self.pending:
            out = bytes(self.pending[:length])
            del self.pending[:length]
            return out
        while True:
            data = bytes(self.target.device.read(self.target.endpoint_in, length, timeout=10000))
            if data:
                return data

    def _send(self, body: bytes, timeout: int) -> tuple[int, int]:
        sequence = self.channel.sequence
        frame = struct.pack("<IHHBBBB", len(body), 0x40, sequence, 0, 0, 0, 0) + body
        sent = self.target.device.write(self.target.endpoint_out, frame, timeout=timeout)
        if sent != len(frame):
            raise CpError(f"写入不完整：{sent}/{len(frame)}；不要自动重试")
        head = self._read_nonempty(HEADER)
        if len(head) < HEADER:
            raise CpError("Senser 回复头不足 12 字节")
        declared, pfunc, seq, _a, _b, _c, code = struct.unpack_from("<IHHBBBB", head, 0)
        if seq != sequence or pfunc != 0x40:
            raise CpError(f"回复错位：seq={seq} pfunc=0x{pfunc:04x}（请求 seq={sequence}）")
        self.channel.sequence = sequence + 1
        return declared, code

    # ---------------------------------------------------------------- 读写
    def read_unit(self, key: int) -> bytes:
        if key not in CP_KEYS:
            raise CpError(f"拒绝读取未登记的 CP 单元 0x{key:08x}")
        size = CP_KEYS[key]
        body = struct.pack("<HH", 0x603, ADJUST_READ) + struct.pack("<II", key, 1)
        declared, code = self._send(body, timeout=10000)
        if code != 0:
            raise CpError(f"相机返回错误码 {code}")
        if declared != size:
            raise CpError(f"声明长度 {declared} 与单元大小 {size} 不符")
        data = bytearray()
        done = 0
        while done < declared:
            want = min(declared - done, SENSER_CHUNK)
            data += self._read_nonempty(want)
            done += want
            if want % SENSER_MIN == 0:
                self._end_packet()
        return bytes(data)

    def write_unit(self, key: int, data: bytes) -> None:
        if key not in CP_KEYS:
            raise CpError(f"拒绝写入未登记的 CP 单元 0x{key:08x}")
        if len(data) != CP_KEYS[key]:
            raise CpError(f"长度不符：{len(data)} != {CP_KEYS[key]}")
        body = struct.pack("<HH", 0x603, ADJUST_WRITE) + struct.pack("<II", key, 1) + data
        declared, code = self._send(body, timeout=30000)
        if declared:
            self._read_nonempty(declared)
            self._end_packet()
        if code != 0:
            raise CpError(f"相机拒绝写入，错误码 {code}")


@contextmanager
def session(progress=lambda message: None, timeout: float = 25.0):
    """认证进服务模式，交出一条 CpChannel；结束时一定发 STOP_SENSER。

    服务模式下相机不挂载存储卡、不能拍照，所以调用方要尽快做完并退出。

    两个会话之间必须留冷却时间：实测同一次插入里紧接着开第二会话（间隔几秒），
    认证能过但随后端点就掉（USBError Pipe error / No such device），写一半的
    /usr 文件会留在半截状态。间隔 60 秒再开就正常。所以这里自己等，不要求用户
    反复拔插线。
    """
    paths.ensure_vendor_on_path()
    from a6700_unlock.usb import legacy

    patches.install()
    _cooldown(progress)
    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = channel = None
    try:
        target, channel = legacy.run_authentication(
            None, 0x0336, timeout, True, progress=progress)
        yield CpChannel(target, channel)
    finally:
        if target is not None:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            except Exception:  # noqa: BLE001 - 退出失败只能提示拔插
                progress("退出服务模式失败，请拔插 USB 线让相机恢复。")
            try:
                legacy.close_target(target)
            except Exception:  # noqa: BLE001
                pass
        lock.__exit__(None, None, None)
        global _last_exit
        _last_exit = time.monotonic()


_last_exit = 0.0


def _cooldown(progress) -> None:
    """距上一次会话结束不足 SESSION_GAP 秒就先等一会儿。"""
    if not _last_exit:
        return
    remaining = SESSION_GAP - (time.monotonic() - _last_exit)
    if remaining <= 0:
        return
    progress(f"相机正在复位上一个会话，等待 {remaining:.0f} 秒再连…")
    deadline = time.monotonic() + remaining
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(left, 5.0))
