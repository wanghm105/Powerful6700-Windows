"""把全部 CP 单元与 /setting/def/BACKUP.BIN 里的出厂副本逐字节对比，并可一键还原。"""
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
import cp_read  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402

FIRMWARE = ROOT.parent / "firmware"
# 出厂副本在 /setting/def/BACKUP.BIN 里的偏移（docs/PERSIST-STORE.md）
FACTORY = {
    0x02A40000: (0x1B0F3C, 4608),
    0x02A40001: (0x1B2140, 8192),
    0x02A40002: (0x1B4144, 768),
    0x02A40004: (0x1B464C, 1280),
    0x02A40005: (0x1B4B50, 1280),
    0x02A40006: (0x1B5054, 1280),
    0x02A40008: (0x1B5A5C, 1536),
    0x02A40009: (0x1B6060, 1024),
    0x02A4000B: (0x1B6568, 256),
    0x02A4000C: (0x1B666C, 512),
    0x02A4000D: (0x1B6870, 28672),
    0x02A4000E: (0x1BD874, 1792),
    0x02A4000F: (0x1BDF78, 512),
    0x02A40011: (0x1BE380, 768),
}


def runs(a, b):
    out, start = [], None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i - start)); start = None
    if start is not None:
        out.append((start, min(len(a), len(b)) - start))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--confirm", default="")
    args = ap.parse_args(argv)
    cp_read.CP_KEYS.update({k: size for k, (_, size) in FACTORY.items()})
    backup = (FIRMWARE / "setting" / "def" / "BACKUP.BIN").read_bytes()

    from a6700_unlock.usb import legacy  # noqa: PLC0415
    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: None)
    reader = CpReader(target, channel); writer = CpWriter(target, channel)
    dirty = []
    try:
        for key, (off, size) in FACTORY.items():
            want = backup[off:off + size]
            live = reader.read_unit(key)
            if live == want:
                continue
            diffs = runs(live, want)
            total = sum(n for _, n in diffs)
            dirty.append((key, len(diffs), total, diffs[:4]))
            print(f"0x{key:08X} 差 {total} 字节 / {len(diffs)} 段  实时 {hashlib.sha256(live).hexdigest()[:12]} 出厂 {hashlib.sha256(want).hexdigest()[:12]}")
            for d_off, d_len in diffs[:4]:
                print(f"    0x{d_off:05X} +{d_len}")
            if args.confirm == "yes-write":
                writer.write_unit(key, want)
                print("    已写回" if reader.read_unit(key) == want else "    回读不一致！")
        if not dirty:
            print("全部单元与出厂一致")
    finally:
        try: legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
        except Exception: pass
        try: legacy.close_target(target)
        except Exception: pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
