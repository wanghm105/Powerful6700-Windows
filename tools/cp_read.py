"""只读读取 A6700 CP 单元（0x02a40001 / 0x02a4000d）。

协议来自 A7C2 的 cp_read：pFunc 0x40 (AdjustControl)，正文
    pack('<HH', 0x603, 0x40) + pack('<II', key, 1)
回复 payload 长度固定为单元大小（8192 / 28672）。CP 读需要额外吃掉
0x200 的结束包，否则后续读会错位（A7C2 的 _end_packet 逻辑）。

本工具只发 0x603/0x40（读），绝不发 0x41（写）。也绝不写 flash。
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import patches, paths, windows_shim  # noqa: E402

paths.ensure_vendor_on_path()

from a6700_unlock.usb import legacy  # noqa: E402

CP_KEYS = {0x02A40001: 0x2000, 0x02A4000D: 0x7000}
ADJUST_READ = 0x40
ADJUST_WRITE = 0x41
SENSER_MIN = 0x200
SENSER_CHUNK = 0x8000
HEADER = 12


def log(message):
    print(message, flush=True)


class CpReader:
    """Senser 通道上的 CP 单元读取（含结束包处理）。"""

    def __init__(self, target, channel):
        self.target = target
        self.channel = channel
        self.pending = bytearray()

    def _end_packet(self):
        if self.pending:
            return
        try:
            data = self.target.device.read(
                self.target.endpoint_in, SENSER_MIN, timeout=1000
            )
        except Exception as exc:  # 超时是正常情况（有些固件不发空包）
            if type(exc).__name__ not in ("USBTimeoutError", "USBError"):
                raise
            if type(exc).__name__ == "USBError" and "timeout" not in str(exc).lower():
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

    def read_unit(self, key):
        if key not in CP_KEYS:
            raise SystemExit(f"拒绝读取未登记的 CP 单元 0x{key:08x}")
        size = CP_KEYS[key]
        body = struct.pack("<HH", 0x603, ADJUST_READ) + struct.pack("<II", key, 1)
        sequence = self.channel.sequence
        frame = struct.pack("<IHHBBBB", len(body), 0x40, sequence, 0, 0, 0, 0) + body
        sent = self.target.device.write(self.target.endpoint_out, frame, timeout=10000)
        if sent != len(frame):
            raise SystemExit("写入不完整；不要自动重试")

        head = self._read_nonempty(HEADER)
        if len(head) < HEADER:
            raise SystemExit("Senser 回复头不足 12 字节")
        declared, pfunc, seq, _, _, _, code = struct.unpack_from("<IHHBBBB", head, 0)
        if seq != sequence or pfunc != 0x40:
            raise SystemExit(
                f"回复错位：seq={seq} pfunc=0x{pfunc:04x}（请求 seq={sequence}）"
            )
        if code != 0:
            raise SystemExit(f"相机返回错误码 {code}")
        if declared != size:
            raise SystemExit(f"声明长度 {declared} 与单元大小 {size} 不符")

        data = bytearray()
        done = 0
        chunk = SENSER_CHUNK
        while done < declared:
            want = min(declared - done, chunk)
            data += self._read_nonempty(want)
            done += want
            if want % SENSER_MIN == 0:
                self._end_packet()
            chunk = SENSER_CHUNK
        self.channel.sequence = sequence + 1
        return bytes(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读读取 A6700 CP 单元")
    parser.add_argument("--key", default="auto", help="0x02a40001 / 0x02a4000d / auto")
    parser.add_argument("--out", default=str(ROOT.parent / "firmware" / "cp"))
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)

    keys = [0x02A40001, 0x02A4000D]
    if args.key != "auto":
        keys = [int(args.key, 16)] if args.key.lower().startswith("0x") else [int(args.key)]

    patches.install()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = channel = None
    try:
        target, channel = legacy.run_authentication(
            None, 0x0336, args.timeout, True, progress=log
        )
        log(f"服务模式已就绪：interface={target.interface_number} "
            f"in=0x{target.endpoint_in:02x} out=0x{target.endpoint_out:02x}")
        reader = CpReader(target, channel)
        results = {}
        for key in keys:
            started = time.monotonic()
            data = reader.read_unit(key)
            path = out_dir / f"unit-{key:08x}.bin"
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            results[key] = (path, len(data), digest, time.monotonic() - started)
            log(f"0x{key:08x}: {len(data)} 字节 {time.monotonic()-started:.2f}s")
            log(f"  sha256 {digest}")
            log(f"  首 48 字节 {data[:48].hex()}")
            non_zero = sum(1 for b in data if b)
            log(f"  非零字节 {non_zero}/{len(data)}")
            log(f"  -> {path}")
        return 0
    finally:
        if target is not None:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
                log("已发送退出服务模式指令。")
            except Exception as exc:
                log(f"退出服务模式失败：{exc}；请拔插 USB")
            try:
                legacy.close_target(target)
            except Exception:
                pass
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    sys.exit(main())
