# -*- coding: utf-8 -*-
"""确认 CP 单元的改动是否会随关机写进 /setting/BACKUP.BIN。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIRMWARE = ROOT.parent / "firmware"

from a6700win import flash  # noqa: E402
from a6700win.research import ServiceSession  # noqa: E402

CHUNK = 0x80000
REMOTE = "/setting/BACKUP.BIN"
UNIT_OFFSET = 0x1B6870
MARKER = UNIT_OFFSET + 0x1250 + 9 * 64


def dump(session, out: Path) -> bytes:
    size = flash.stat(session, REMOTE)
    blob = bytearray()
    while len(blob) < size:
        block = min(CHUNK, size - len(blob))
        blob.extend(flash.read_range(session, REMOTE, len(blob), block))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(f"{out.name}: {len(blob):,} B sha256 {hashlib.sha256(blob).hexdigest()[:16]}", flush=True)
    return bytes(blob)


def main() -> int:
    baseline = (FIRMWARE / "setting" / "BACKUP-live.bin").read_bytes()
    with ServiceSession(progress=lambda message: None) as session:
        blob = dump(session, FIRMWARE / "setting" / "BACKUP-after.bin")
    print("标记长度 64 · 期望内容为 64 个 0x11", flush=True)
    print(f"BACKUP.BIN 里标记位置: {blob[MARKER:MARKER + 8].hex(' ')}", flush=True)
    print(f"改动前的同位置:        {baseline[MARKER:MARKER + 8].hex(' ')}", flush=True)
    diff = sum(1 for a, b in zip(blob, baseline) if a != b)
    print(f"整份差异 {diff} 字节", flush=True)
    if blob[MARKER:MARKER + 64] == bytes([0x11]) * 64:
        print("结论：关机时 CP 单元被写入 BACKUP.BIN ✅", flush=True)
    else:
        print("结论：BACKUP.BIN 里没有标记，关机不写（或另有落点）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
