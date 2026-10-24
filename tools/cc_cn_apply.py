"""把 CC/CN 的两条色度记录写进 CP 单元 0x02A40001（CC=PT bank 6，CN=NT bank 4）。

用法：
  python tools/cc_cn_apply.py --cc 0.60 --cn 0.80 --confirm yes-write
  python tools/cc_cn_apply.py --restore --confirm yes-write
源数据取出厂副本 firmware/cp/unit-02a40001.backup-def.bin，等比缩放 24 个 int16（含 v6）。
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
BANK_CC = 6   # PT
BANK_CN = 4   # NT
FACTORY = ROOT.parent / "firmware" / "cp" / "unit-02a40001.backup-def.bin"


def scaled(factory: bytes, bank: int, factor: float) -> bytes:
    off = CHROMA_BASE + bank * CHROMA_STRIDE
    values = struct.unpack_from("<24h", factory, off)
    out = [max(-32768, min(32767, int(round(v * factor)))) for v in values]
    body = struct.pack("<24h", *out)
    return body + bytes(CHROMA_STRIDE - len(body))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", type=float, default=0.60)
    parser.add_argument("--cn", type=float, default=0.80)
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--keep-service", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    factory = FACTORY.read_bytes()

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader = CpReader(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        for bank in (BANK_CC, BANK_CN):
            off = CHROMA_BASE + bank * CHROMA_STRIDE
            if args.restore:
                live[off:off + CHROMA_STRIDE] = factory[off:off + CHROMA_STRIDE]
            else:
                factor = args.cc if bank == BANK_CC else args.cn
                live[off:off + CHROMA_STRIDE] = scaled(factory, bank, factor)
        writer = CpWriter(target, channel)
        writer.write_unit(UNIT, bytes(live))
        check = reader.read_unit(UNIT)
        ok = check == bytes(live)
        print("回读一致 ✓" if ok else "回读不一致！")
        for bank in (BANK_CC, BANK_CN):
            off = CHROMA_BASE + bank * CHROMA_STRIDE
            vals = struct.unpack_from("<24h", live, off)
            print(f"bank {bank}: {vals}")
    finally:
        if not args.keep_service:
            legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            legacy.close_target(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
