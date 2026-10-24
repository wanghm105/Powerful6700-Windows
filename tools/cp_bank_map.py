"""按分组给 CC1 色度 bank 写不同方向的极端值，用观察到的色相定位某个外观读的是哪个 bank。

用法：
  python tools/cp_bank_map.py --spec "0-6:30000,0;7-12:0,30000;13-19:-30000,0;20-25:0,-30000" --confirm yes-write
  python tools/cp_bank_map.py --restore --confirm yes-write
--restore 从 ../firmware/cp/baseline/unit-02a40001.bin 或 live 基线拷回 0x1250 起整块色度区。
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
CHROMA_SPAN = CHROMA_STRIDE * 54
BASELINE = ROOT.parent / "firmware" / "cp" / "unit-02a40001.backup-def.bin"


def parse_spec(text):
    groups = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        where, value = part.split(":")
        lo, _, hi = where.partition("-")
        lo = int(lo, 0)
        hi = int(hi, 0) if hi else lo
        cb, cr = [int(x, 0) for x in value.split(",")]
        groups.append((lo, hi, cb, cr))
    return groups


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--keep-service", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    groups = parse_spec(args.spec) if args.spec else []

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader = CpReader(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        if args.restore:
            base = BASELINE.read_bytes()
            live[CHROMA_BASE:CHROMA_BASE + CHROMA_SPAN] = base[CHROMA_BASE:CHROMA_BASE + CHROMA_SPAN]
            print("已从基线还原 0x1250 起整块色度区")
        for lo, hi, cb, cr in groups:
            pairs = struct.pack("<24h", *([cb, cr] * 12))
            record = pairs + bytes(CHROMA_STRIDE - len(pairs))
            for bank in range(lo, hi + 1):
                off = CHROMA_BASE + bank * CHROMA_STRIDE
                live[off:off + CHROMA_STRIDE] = record
            print(f"bank {lo}..{hi} ← ({cb}, {cr})")
        writer = CpWriter(target, channel)
        writer.write_unit(UNIT, bytes(live))
        check = reader.read_unit(UNIT)
        print("回读一致" if check == bytes(live) else "回读不一致！")
    finally:
        if not args.keep_service:
            legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            legacy.close_target(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
