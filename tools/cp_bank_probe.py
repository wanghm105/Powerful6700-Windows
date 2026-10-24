"""把若干 CC1 色度 bank 写成「去色记录」（全 0），用于判定某个外观用的是哪个 bank。

用法：
  python tools/cp_bank_probe.py --banks 22,23,24,25,26,27,30,31 --confirm yes-write
  python tools/cp_bank_probe.py --restore --confirm yes-write
--restore 从 ../firmware/cp/live/unit-02a40001.bin 拷回 0x1250 起整块色度区。
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--banks", default="")
    parser.add_argument("--zero-banks", default="")
    parser.add_argument("--factory-banks", default="")
    parser.add_argument("--pattern", default="zero", choices=("zero", "pink", "invert", "extreme"))
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--keep-service", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader = CpReader(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        base = BASELINE.read_bytes()
        if args.factory_banks:
            factory = (ROOT.parent / "firmware" / "cp" / "unit-02a40001.backup-def.bin").read_bytes()
            for bank in [int(x, 0) for x in args.factory_banks.split(",") if x.strip()]:
                off = CHROMA_BASE + bank * CHROMA_STRIDE
                live[off:off + CHROMA_STRIDE] = factory[off:off + CHROMA_STRIDE]
            print("已把若干 bank 还原成工厂值")
        if args.zero_banks:
            for bank in [int(x, 0) for x in args.zero_banks.split(",") if x.strip()]:
                off = CHROMA_BASE + bank * CHROMA_STRIDE
                live[off:off + CHROMA_STRIDE] = bytes(CHROMA_STRIDE)
            print("已把若干 bank 清零")
        if args.restore:
            live[CHROMA_BASE:CHROMA_BASE + CHROMA_SPAN] = base[CHROMA_BASE:CHROMA_BASE + CHROMA_SPAN]
            print("已从基线恢复整块色度区")
        if args.banks and not args.restore:
            banks = [int(x, 0) for x in args.banks.split(",") if x.strip()]
            if not banks and not args.zero_banks and not args.restore:
                raise SystemExit("必须给 --banks / --zero-banks / --restore")
            for bank in banks:
                off = CHROMA_BASE + bank * CHROMA_STRIDE
                if args.pattern == "zero":
                    record = bytes(CHROMA_STRIDE)
                elif args.pattern == "pink":
                    pairs = struct.pack("<24h", *([600, 0] * 12))
                    record = pairs + bytes(CHROMA_STRIDE - len(pairs))
                elif args.pattern == "invert":
                    pairs = struct.pack("<24h", *([-3000, 3000] * 12))
                    record = pairs + bytes(CHROMA_STRIDE - len(pairs))
                elif args.pattern == "extreme":
                    pairs = struct.pack("<24h", *([30000, -30000] * 12))
                    record = pairs + bytes(CHROMA_STRIDE - len(pairs))
                live[off:off + CHROMA_STRIDE] = record
            print(f"已把 bank {banks} 写成 {args.pattern}")
        writer = CpWriter(target, channel)
        writer.write_unit(UNIT, bytes(live))
        check = reader.read_unit(UNIT)
        print("回读一致" if check == bytes(live) else "回读不一致！")
    finally:
        if not args.keep_service:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            except Exception:  # noqa: BLE001
                pass
        try:
            legacy.close_target(target)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
