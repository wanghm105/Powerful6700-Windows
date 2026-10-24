"""一次会话内：读回 /setting/BACKUP.BIN 存快照（可选）并把 cpapp 曲线写回恒等。

用法：
  python tools/setting_probe.py --out ../firmware/setting/BACKUP-contrast9.bin
  python tools/setting_probe.py --out ... --restore-curves --confirm yes-write
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import flash, patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

from look_name import ChannelBackend  # noqa: E402

BACKUP = "/setting/BACKUP.BIN"
CHUNK = 0x80000
SLOT_BASE = 0xFE0B50
SLOT_STRIDE = 0x400
SLOT_COUNT = 9


def identity_record() -> bytes:
    values = []
    for i in range(16):
        values.append(i * 0x1000)
    for i in range(16):
        values.append(0xF000 + i * 0x100)
    for i in range(16):
        values.append(0xFF00 + i * 0x1)
    while len(values) < 512:
        values.append(0xFFFF)
    return struct.pack("<512H", *values[:512])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--restore-curves", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    backend = ChannelBackend(channel)
    try:
        size = flash.stat(backend, BACKUP)
        print(f"{BACKUP} = {size:,} B")
        blob = bytearray()
        while len(blob) < size:
            want = min(CHUNK, size - len(blob))
            blob += flash.read_range(backend, BACKUP, len(blob), want)
            print(f"  已读 {len(blob):,} / {size:,}")
        out = Path(args.out)
        if not out.is_absolute():
            out = (ROOT / out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(bytes(blob))
        print(f"已保存 {out} sha256 {hashlib.sha256(blob).hexdigest()}")

        if args.restore_curves:
            if args.confirm != "yes-write":
                raise SystemExit("写曲线需要 --confirm yes-write")
            record = identity_record()
            for i in range(SLOT_COUNT):
                offset = SLOT_BASE + i * SLOT_STRIDE
                flash.write_block(backend, "/cp/cpapp-b.bin", offset, record)
                check = flash.read_range(backend, "/cp/cpapp-b.bin", offset, SLOT_STRIDE)
                print(f"  曲线槽 {i} @0x{offset:X} 回读{'一致' if check == record else '不一致'}")
                if check != record:
                    raise SystemExit("回读不一致，中止")
            print("cpapp 9 条曲线已写回恒等")
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
