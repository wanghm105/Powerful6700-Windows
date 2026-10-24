"""一次会话内同时写入 CC/NC 色度（bank 6/4）与外观 profile 参数（参数 40..49）。

用法：
  python tools/cc_apply_all.py --cc 0.70 --cn 0.85 --param 42=54 --confirm yes-write
  python tools/cc_apply_all.py --restore --confirm yes-write
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402

UNIT = 0x02A40001
CHROMA_BASE = 0x1250
CHROMA_STRIDE = 64
PARAM_BASE = 0x1200
BANK_CC = 6
BANK_CN = 4
FACTORY = ROOT.parent / "firmware" / "cp" / "unit-02a40001.backup-def.bin"


def scaled(factory: bytes, bank: int, factor: float, tint: float = 1.0) -> bytes:
    """等比缩放 24 个 int16；tint 只作用于每个分组的第 7 个值（v6，蓝通道基座）。

    tint > 1 → 蓝通道保留更多（偏冷）；tint < 1 → 蓝通道压得更多（偏暖）。
    """
    off = CHROMA_BASE + bank * CHROMA_STRIDE
    values = list(struct.unpack_from("<24h", factory, off))
    out = []
    for index, value in enumerate(values):
        scale = factor * (tint if index % 8 == 6 else 1.0)
        out.append(max(-32768, min(32767, int(round(value * scale)))))
    body = struct.pack("<24h", *out)
    return body + bytes(CHROMA_STRIDE - len(body))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", type=float, default=0.70)
    parser.add_argument("--cn", type=float, default=0.85)
    parser.add_argument("--cc-tint", type=float, default=1.0)
    parser.add_argument("--cn-tint", type=float, default=1.0)
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--keep-service", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    factory = FACTORY.read_bytes()
    params = {}
    for item in args.param:
        key, _, value = item.partition("=")
        params[int(key, 0)] = int(value, 0)

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    backend = __import__("channel_backend").ChannelBackend(channel)
    try:
        reader = CpReader(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        if args.restore:
            live[:] = factory
            print("整块还原成出厂")
        else:
            for bank, factor, tint in ((BANK_CC, args.cc, args.cc_tint), (BANK_CN, args.cn, args.cn_tint)):
                off = CHROMA_BASE + bank * CHROMA_STRIDE
                live[off:off + CHROMA_STRIDE] = scaled(factory, bank, factor, tint)
                print(f"bank {bank} ← 出厂 ×{factor}（蓝基座 ×{tint}）")
            for index, value in sorted(params.items()):
                print(f"参数 {index}: {live[PARAM_BASE + index]} → {value}")
                live[PARAM_BASE + index] = value
        writer = CpWriter(target, channel)
        writer.write_unit(UNIT, bytes(live))
        check = reader.read_unit(UNIT)
        print("回读一致 ✓" if check == bytes(live) else "回读不一致！")
        print("参数 40..49:", list(live[PARAM_BASE + 40:PARAM_BASE + 50]))
    finally:
        if not args.keep_service:
            legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            legacy.close_target(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
