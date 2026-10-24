# -*- coding: utf-8 -*-
"""把实机 CP 单元与 /setting/BACKUP.BIN 里的持久副本逐一比对。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIRMWARE = ROOT.parent / "firmware"

sys.path.insert(0, str(ROOT / "tools"))
import cp_read  # noqa: E402

from a6700win.research import ServiceSession  # noqa: E402

# docs/PERSIST-STORE.md 记录的单元表：key -> (BACKUP.BIN 偏移, 长度)
UNITS = {0x02A40001: (0x1B2140, 8192), 0x02A4000D: (0x1B6870, 28672), 0x02A4000E: (0x1BD874, 1792)}


def main() -> int:
    backups = {name: (FIRMWARE / "setting" / name).read_bytes()
               for name in ("BACKUP-live.bin", "def/BACKUP.BIN", "post/BACKUP.BIN")}
    with ServiceSession(progress=lambda message: None) as session:
        reader = cp_read.CpReader(session.target, session.channel)
        for key, (offset, size) in UNITS.items():
            data = reader.read_unit(key)
            out = FIRMWARE / "cp" / "live" / f"unit-{key:08x}.bin"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            print(f"unit 0x{key:08x}: {len(data):,} B sha256 {hashlib.sha256(data).hexdigest()[:16]}", flush=True)
            for name, blob in backups.items():
                stored = blob[offset:offset + size]
                same = stored == data
                diff = sum(1 for a, b in zip(stored, data) if a != b)
                print(f"   vs {name}: {'一致' if same else f'差 {diff} 字节'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
