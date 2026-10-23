"""向 A6700 CP 单元写入（RAM，掉电即恢复）并回读校验。

协议来自 A7C2 的 cp_write：pFunc 0x40 (AdjustControl)，正文
    pack('<HH', 0x603, 0x41) + pack('<II', key, 1) + data
data 必须正好是单元大小（0x02a40001 → 8192，0x02a4000d → 28672）。

安全约束：
- 只允许这两个单元；只允许整块写入；
- 写入前必须已有同名的 .orig 备份（第一次运行会自动读一份）；
- 写完立刻回读，比对不一致则报告；
- 不写 flash，断电/关机即恢复出厂状态。
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp_read import CpReader, CP_KEYS, HEADER  # noqa: E402

ADJUST_WRITE = 0x41


class CpWriter(CpReader):
    def write_unit(self, key, data):
        if key not in CP_KEYS:
            raise SystemExit(f"拒绝写入未登记的 CP 单元 0x{key:08x}")
        if len(data) != CP_KEYS[key]:
            raise SystemExit(f"长度不符：{len(data)} != {CP_KEYS[key]}")
        body = struct.pack("<HH", 0x603, ADJUST_WRITE) + struct.pack("<II", key, 1) + data
        sequence = self.channel.sequence
        frame = struct.pack("<IHHBBBB", len(body), 0x40, sequence, 0, 0, 0, 0) + body
        sent = self.target.device.write(self.target.endpoint_out, frame, timeout=30000)
        if sent != len(frame):
            raise SystemExit(f"写入不完整：{sent}/{len(frame)}；不要自动重试")
        head = self._read_nonempty(HEADER)
        declared, pfunc, seq, _, _, _, code = struct.unpack_from("<IHHBBBB", head, 0)
        if seq != sequence or pfunc != 0x40:
            raise SystemExit(f"回复错位：seq={seq} pfunc=0x{pfunc:04x}")
        tail = self._read_nonempty(declared) if declared else b""
        if declared:
            self._end_packet()
        self.channel.sequence = sequence + 1
        if code != 0:
            raise SystemExit(f"相机拒绝写入，错误码 {code}")
        return tail


def main(argv=None):
    parser = argparse.ArgumentParser(description="写入 A6700 CP 单元（RAM）")
    parser.add_argument("--key", required=True, help="0x02a40001 / 0x02a4000d")
    parser.add_argument("--file", required=True, help="要写入的整块单元文件")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-service", action="store_true",
                        help="写入后不发送 STOP，保持服务模式，方便立即观察屏幕变化")
    args = parser.parse_args(argv)

    key = int(args.key, 16)
    data = Path(args.file).read_bytes()
    if key not in CP_KEYS:
        raise SystemExit("不支持的 CP 单元")
    if len(data) != CP_KEYS[key]:
        raise SystemExit(f"文件长度 {len(data)} 与单元大小 {CP_KEYS[key]} 不符")
    print(f"目标单元 0x{key:08x}  长度 {len(data)}  sha256 {hashlib.sha256(data).hexdigest()}")
    if args.dry_run:
        print("dry-run：未接触相机。")
        return 0

    backup = Path(str(args.file) + ".orig")
    patches.install()
    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = channel = None
    try:
        target, channel = legacy.run_authentication(None, 0x0336, args.timeout, True, progress=print)
        reader = CpReader(target, channel)
        writer = CpWriter(target, channel)
        current = reader.read_unit(key)
        if not backup.exists():
            backup.write_bytes(current)
            print(f"已保存写入前备份：{backup}")
        else:
            print(f"已有写入前备份：{backup}")
        if current == data:
            print("当前内容与目标一致，无需写入。")
            return 0
        started = time.monotonic()
        writer.write_unit(key, data)
        print(f"写入完成 {time.monotonic()-started:.2f}s，开始回读校验…")
        after = reader.read_unit(key)
        if after == data:
            print("回读一致 ✅")
            return 0
        diff = sum(1 for a, b in zip(after, data) if a != b)
        print(f"回读不一致 ❌ 差异字节 {diff}")
        print(f"  回读 sha256 {hashlib.sha256(after).hexdigest()}")
        return 2
    finally:
        if target is not None:
            if args.keep_service:
                print("保持服务模式（未发送 STOP）；观察完请拔插 USB 让相机恢复。")
            else:
                try:
                    legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
                    print("已发送退出服务模式指令。")
                except Exception as exc:
                    print(f"退出服务模式失败：{exc}；请拔插 USB")
            try:
                legacy.close_target(target)
            except Exception:
                pass
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    sys.exit(main())
