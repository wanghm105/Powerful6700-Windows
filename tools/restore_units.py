"""把 CP 单元 0x02A40001 / 0x02A4000D 与出厂副本对比，并可整块还原。

用法：
  python tools/restore_units.py                 # 只对比
  python tools/restore_units.py --confirm yes-write   # 还原
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402

FIRMWARE = ROOT.parent / "firmware"
UNITS = {
    0x02A40001: FIRMWARE / "cp" / "unit-02a40001.backup-def.bin",
    0x02A4000D: FIRMWARE / "cp" / "unit-02a4000d.backup-def.bin",
}


def runs(a: bytes, b: bytes) -> list[tuple[int, int]]:
    out = []
    start = None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if start is None:
                start = i
        else:
            if start is not None:
                out.append((start, i - start))
                start = None
    if start is not None:
        out.append((start, min(len(a), len(b)) - start))
    return out


def label(offset: int) -> str:
    if 0x1250 <= offset < 0x1250 + 54 * 64:
        bank = (offset - 0x1250) // 64
        return f"色度 bank {bank}"
    if 0x1E0 <= offset < 0x1E0 + 64 * 768:
        return f"矩阵槽 {(offset - 0x1E0) // 768}"
    if 0x1200 <= offset < 0x1250:
        return "参数表"
    return "其它"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: None)
    reader = CpReader(target, channel)
    writer = CpWriter(target, channel)
    try:
        for key, path in UNITS.items():
            factory = path.read_bytes()
            live = reader.read_unit(key)
            print(f"\n单元 0x{key:08X}  实时 {hashlib.sha256(live).hexdigest()[:16]}  "
                  f"出厂 {hashlib.sha256(factory).hexdigest()[:16]}  "
                  f"{'一致' if live == factory else '不一致'}")
            diffs = runs(live, factory)
            total = sum(n for _, n in diffs)
            print(f"  差异 {total} 字节 / {len(diffs)} 段")
            for off, n in diffs[:12]:
                print(f"    0x{off:05X} ({label(off)}) {n} 字节")
            if args.confirm == "yes-write" and live != factory:
                writer.write_unit(key, factory)
                back = reader.read_unit(key)
                print("  已写回出厂值" if back == factory else "  回读不一致！")
    finally:
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
