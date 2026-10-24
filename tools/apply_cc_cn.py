"""一次性把 CC / CN 做到 VV / VV2：写色度 bank + 改菜单名。

用法：
  python tools/apply_cc_cn.py --confirm yes-write
  python tools/apply_cc_cn.py --restore --confirm yes-write   # 回滚名字与 bank
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

import uxc  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402
from look_name import ChannelBackend  # noqa: E402

FIRMWARE = ROOT.parent / "firmware"
UNIT = 0x02A40001
CHROMA_BASE = 0x1250
STRIDE = 64
UXC_PATH = "/usr/share/app/string_simplifiedchinese_f.uxc"
UXC_SIZE = 145612

# (name, offsets in uxc, bank 列表)
RENAMES = {
    "PT": ([0x0DA94, 0x1DE98], ()),
    "NT": ([0x0A20C, 0x1E680], ()),
    "CC": ([0x117DC, 0x1DDD4], (1, 2)),
    "CN": ([0x11A10, 0x1DA94], (5,)),
}
BANK_SOURCE = {"CC": (6, 60), "CN": (4, 80)}  # CC: PT 记录 ×0.60；CN: NT 记录 ×0.80


def scaled(factory: bytes, bank: int, percent: int) -> bytes:
    off = CHROMA_BASE + bank * STRIDE
    rec = list(struct.unpack("<32h", factory[off:off + STRIDE]))
    for idx in (4, 5, 7):
        rec[idx] = int(round(rec[idx] * percent / 100))
    return struct.pack("<32h", *rec)


def patch_uxc_text(raw: bytes, offsets, new_text: str) -> bytes:
    blob = bytearray(raw)
    payload = new_text.encode("utf-8") + b"\x00"
    resource = uxc.decode(raw)
    for offset in offsets:
        match = [r for r in resource.records if r.offset == offset]
        if not match:
            raise SystemExit(f"UXC 偏移 0x{offset:X} 上没有记录")
        record = match[0]
        room = record.end - record.offset - 4
        if len(payload) > room:
            raise SystemExit(f"0x{offset:X} 容量不足：需要 {len(payload)} 实有 {room}")
        blob[record.offset + 4:record.end] = payload + bytes(room - len(payload))
    return bytes(blob)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", default="")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--skip-uxc", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    factory = (FIRMWARE / "cp" / "unit-02a40001.backup-def.bin").read_bytes()

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    backend = ChannelBackend(channel)
    try:
        reader = CpReader(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        print(f"实时色度单元 sha256 {hashlib.sha256(bytes(live)).hexdigest()[:16]}")

        if args.restore:
            live[:] = factory
            plan = []
        else:
            plan = []
            for name, (_, banks) in RENAMES.items():
                if not banks:
                    continue
                src_bank, percent = BANK_SOURCE[name]
                rec = scaled(factory, src_bank, percent)
                for bank in banks:
                    off = CHROMA_BASE + bank * STRIDE
                    live[off:off + STRIDE] = rec
                    plan.append((name, bank, struct.unpack("<8h", rec[:16])))
            for name, bank, values in plan:
                print(f"  {name} → bank {bank}: {values}")

        writer = CpWriter(target, channel)
        writer.write_unit(UNIT, bytes(live))
        check = reader.read_unit(UNIT)
        print("色度回读一致" if check == bytes(live) else "色度回读不一致！")
        if check != bytes(live):
            raise SystemExit("色度回读失败，中止")

        if not args.skip_uxc:
            raw = bytearray()
            while len(raw) < UXC_SIZE:
                raw += flash.read_range(backend, UXC_PATH, len(raw), min(0x80000, UXC_SIZE - len(raw)))
            print(f"UXC 读回 {len(raw):,} B sha256 {hashlib.sha256(bytes(raw)).hexdigest()[:16]}")
            updated = bytes(raw)
            # 按当前文本定位记录：先把之前改过的 PT/NT 还原，再把 VV/VV2 改成 CC/CN
            resource = uxc.decode(updated)
            by_text = {}
            for record in resource.records:
                text = updated[record.offset + 4:record.end].split(b"\x00")[0].decode("utf-8", "replace")
                by_text.setdefault(text, []).append(record)
            for old, new in (("CC", "PT"), ("CN", "NT"), ("VV", "CC"), ("VV2", "CN")):
                hits = by_text.get(old, [])
                print(f"  改名 {old!r} → {new!r}：{len(hits)} 条")
                if not hits:
                    raise SystemExit(f"找不到文本 {old!r} 的记录")
                for record in hits:
                    room = record.end - record.offset - 4
                    payload = new.encode("utf-8") + b"\x00"
                    if len(payload) > room:
                        raise SystemExit(f"{old}→{new} 容量不足：{room} < {len(payload)}")
                    buf = bytearray(updated)
                    buf[record.offset + 4:record.end] = payload + bytes(room - len(payload))
                    updated = bytes(buf)
            if updated != bytes(raw):
                for off in range(0, UXC_SIZE, flash.BLOCK):
                    chunk = updated[off:off + flash.BLOCK]
                    flash.write_block(backend, UXC_PATH, off, chunk)
                    print(f"  写 0x{off:06X} {len(chunk):,} B ok")
                back = flash.read_range(backend, UXC_PATH, 0, UXC_SIZE)
                print("UXC 回读一致" if back == updated else "UXC 回读不一致！")
                if back != updated:
                    raise SystemExit("UXC 回读失败")
            names = {}
            for record in uxc.decode(updated).records:
                if record.offset in (0x0DA94, 0x0A20C, 0x117DC, 0x11A10, 0x1DDD4, 0x1DA94):
                    names[hex(record.offset)] = updated[record.offset + 4:record.end].split(b"\x00")[0].decode("utf-8", "replace")
            print("菜单名:", names)
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
