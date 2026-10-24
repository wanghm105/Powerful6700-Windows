"""一键把外观名与色度单元还原成出厂状态。

回滚内容：
  1. CP 单元 0x02A40001 整块写回 ../firmware/cp/unit-02a40001.backup-def.bin（出厂副本）
  2. /usr/share/app/string_simplifiedchinese_f.uxc 里的 CC/CN 名字改回 VV/VV2

用法：python tools/restore_original.py --confirm yes-write
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import flash, patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

import uxc  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402
from look_name import ChannelBackend  # noqa: E402

FIRMWARE = ROOT.parent / "firmware"
UNIT = 0x02A40001
UXC_PATH = "/usr/share/app/string_simplifiedchinese_f.uxc"
UXC_SIZE = 145612
RESTORE_NAMES = (("CC", "VV"), ("CN", "VV2"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", default="")
    parser.add_argument("--skip-colour", action="store_true")
    parser.add_argument("--skip-names", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    factory = (FIRMWARE / "cp" / "unit-02a40001.backup-def.bin").read_bytes()
    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: None)
    backend = ChannelBackend(channel)
    try:
        if not args.skip_colour:
            reader = CpReader(target, channel)
            live = reader.read_unit(UNIT)
            print(f"实时色度单元 sha256 {hashlib.sha256(live).hexdigest()[:16]}")
            if live != factory:
                CpWriter(target, channel).write_unit(UNIT, factory)
                back = reader.read_unit(UNIT)
                print("色度已写回出厂值" if back == factory else "色度回读不一致！")
                if back != factory:
                    raise SystemExit("色度还原失败")
            else:
                print("色度单元本来就是出厂值")

        if not args.skip_names:
            raw = b""
            while len(raw) < UXC_SIZE:
                raw += flash.read_range(backend, UXC_PATH, len(raw), min(0x80000, UXC_SIZE - len(raw)))
            resource = uxc.decode(raw)
            by_text = {}
            for record in resource.records:
                text = raw[record.offset + 4:record.end].split(bytes([0]))[0].decode("utf-8", "replace")
                by_text.setdefault(text, []).append(record)
            offsets = sorted(r.offset for r in resource.records)

            def capacity(record) -> int:
                import bisect
                idx = bisect.bisect_left(offsets, record.offset) + 1
                limit = offsets[idx] if idx < len(offsets) else len(raw)
                return limit - record.offset - 4

            updated = raw
            for old, new in RESTORE_NAMES:
                hits = by_text.get(old, [])
                print(f"  改名 {old!r} → {new!r}：{len(hits)} 条")
                for record in hits:
                    room = capacity(record)
                    payload = new.encode("utf-8") + bytes([0])
                    if len(payload) > room:
                        raise SystemExit(f"{old}→{new} 容量不足")
                    buf = bytearray(updated)
                    buf[record.offset + 4:record.offset + 4 + room] = payload + bytes(room - len(payload))
                    updated = bytes(buf)
            if updated != raw:
                for off in range(0, UXC_SIZE, flash.BLOCK):
                    flash.write_block(backend, UXC_PATH, off, updated[off:off + flash.BLOCK])
                back = flash.read_range(backend, UXC_PATH, 0, UXC_SIZE)
                print("名字已写回（回读一致）" if back == updated else "名字回读不一致！")
            names = {}
            for record in uxc.decode(updated).records:
                text = updated[record.offset + 4:record.end].split(bytes([0]))[0].decode("utf-8", "replace")
                if text in {"VV", "VV2", "CC", "CN", "PT", "NT"}:
                    names[hex(record.offset)] = text
            print("当前名字:", names)
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
