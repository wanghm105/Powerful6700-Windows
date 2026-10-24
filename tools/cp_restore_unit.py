"""把 CP 单元整块写回指定出厂副本，并打印写前的差异清单。

用法：python tools/cp_restore_unit.py --key 0x02a40001 --from ../firmware/cp/unit-02a40001.backup-def.bin --confirm yes-write
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="0x02a40001")
    parser.add_argument("--from", dest="source", required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    key = int(args.key, 0)
    factory = Path(args.source)
    if not factory.is_absolute():
        factory = (ROOT / factory).resolve()
    target_bytes = factory.read_bytes()

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader = CpReader(target, channel)
        live = reader.read_unit(key)
        print(f"实时单元 0x{key:08X} {len(live):,} B sha256 {hashlib.sha256(live).hexdigest()[:16]}")
        print(f"出厂副本          {len(target_bytes):,} B sha256 {hashlib.sha256(target_bytes).hexdigest()[:16]}")
        spans = []
        for i in range(0, len(live), 64):
            if live[i:i + 64] != target_bytes[i:i + 64]:
                spans.append(i)
        if spans:
            print(f"不同的 64 B 槽位：{[hex(s) for s in spans]}")
            for s in spans:
                bank = (s - 0x1250) // 64 if s >= 0x1250 else None
                print(f"  +0x{s:04X} bank {bank}: 实时 {live[s:s+8].hex()} 出厂 {target_bytes[s:s+8].hex()}")
        else:
            print("实时单元与出厂副本完全一致")
        if live != target_bytes:
            writer = CpWriter(target, channel)
            writer.write_unit(key, target_bytes)
            check = reader.read_unit(key)
            print("已写回出厂值，回读一致" if check == target_bytes else "回读不一致！")
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
