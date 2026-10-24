"""按编号写 CP 单元 0x02a40001 的参数表（0x1200 + 编号，每项 1 字节）。

用法：
    python tools/cp_param_set.py --show
    python tools/cp_param_set.py --set 46=19 --set 48=20 --confirm yes-write
    python tools/cp_param_set.py --restore
写入前自动备份实时单元到 firmware/cp/probe/unit-02a40001.params.bin。
"""
from __future__ import annotations

import argparse
import hashlib
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
PARAM_BASE = 0x1200
BACKUP = ROOT.parent / "firmware" / "cp" / "probe" / "unit-02a40001.params.bin"
FACTORY_PARAMS = (16, 8, 14, 10, 12, 9, 15, 11, 13, 19)


def parse(items):
    pairs = []
    for item in items:
        name, _, value = item.partition("=")
        pairs.append((int(name), int(value, 0)))
    return pairs


def dump(unit: bytes) -> None:
    for start in (0, 20, 40):
        row = [unit[PARAM_BASE + p] for p in range(start, start + 20)]
        print(f"参数 {start:2d}..{start + 19:2d}: " + " ".join(f"{v:3d}" for v in row))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", action="append", default=[], metavar="N=VALUE")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--reset", action="store_true", help="把参数 40..49 写回出厂十个值")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader, writer = CpReader(target, channel), CpWriter(target, channel)
        live = bytes(reader.read_unit(UNIT))
        print("当前参数表：")
        dump(live)

        if args.restore:
            if not BACKUP.exists():
                print("没有备份，无法还原")
                return 1
            restored = BACKUP.read_bytes()
            writer.write_unit(UNIT, restored)
            back = CpReader(target, channel).read_unit(UNIT)
            print("还原回读一致 ✓" if bytes(back) == restored else "还原回读不一致 ✗")
            return 0

        if args.reset:
            if args.confirm != "yes-write":
                print("写入需要 --confirm yes-write")
                return 2
            unit = bytearray(live)
            for offset, value in enumerate(FACTORY_PARAMS):
                unit[PARAM_BASE + 40 + offset] = value
            writer.write_unit(UNIT, bytes(unit))
            back = bytes(CpReader(target, channel).read_unit(UNIT))
            print("出厂参数已写回，回读一致 ✓" if back == bytes(unit) else "回读不一致 ✗")
            dump(back)
            return 0

        if args.show or not args.set:
            return 0

        if args.confirm != "yes-write":
            print("写入需要 --confirm yes-write")
            return 2

        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_bytes(live)
        print(f"已备份 → {BACKUP.name}")

        unit = bytearray(live)
        for index, value in parse(args.set):
            old = unit[PARAM_BASE + index]
            unit[PARAM_BASE + index] = value & 0xFF
            print(f"参数 {index}: {old} → {value & 0xFF}")
        writer.write_unit(UNIT, bytes(unit))
        back = bytes(CpReader(target, channel).read_unit(UNIT))
        print("回读一致 ✓" if back == bytes(unit) else "回读不一致 ✗")
        print(f"新 sha256 {hashlib.sha256(back).hexdigest()[:16]}")
    finally:
        legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
        legacy.close_target(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
