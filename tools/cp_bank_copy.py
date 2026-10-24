"""把某个色度 bank 的记录复制到其它 bank（CP 单元 0x02a40001，0x1250+bank*64）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

from a6700_unlock.usb import legacy  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402

UNIT = 0x02A40001
CHROMA_BASE = 0x1250


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="source", type=int, required=True)
    parser.add_argument("--to", dest="targets", type=int, nargs="+", required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.confirm != "yes-write":
        print("写入需要 --confirm yes-write")
        return 2

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader, writer = CpReader(target, channel), CpWriter(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        record = bytes(live[CHROMA_BASE + args.source * 64: CHROMA_BASE + (args.source + 1) * 64])
        print(f"源 bank {args.source}: " + " ".join(str(v) for v in __import__("struct").unpack("<24h", record[:48])))
        for bank in args.targets:
            live[CHROMA_BASE + bank * 64: CHROMA_BASE + (bank + 1) * 64] = record
            print(f"bank {bank} ← 记录已复制")
        writer.write_unit(UNIT, bytes(live))
        back = bytes(CpReader(target, channel).read_unit(UNIT))
        print("回读一致 ✓" if back == bytes(live) else "回读不一致 ✗")
    finally:
        legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
        legacy.close_target(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
