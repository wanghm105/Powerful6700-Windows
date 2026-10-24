"""一次性诊断：读回 CP 单元 0x02a40001 / 0x02a4000d，对比已知良好副本，
并可选把整份 /cp/cpapp-b.bin 备份到本地。

用法：
  python tools/diag_cc.py --read                 # 只读 + 对比
  python tools/diag_cc.py --read --dump-cpapp    # 顺带备份 cpapp（17.9 MB）
  python tools/diag_cc.py --restore-unit0d ../firmware/cp/live/unit-02a4000d.bin --confirm yes-write
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

from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402
from look_name import ChannelBackend  # noqa: E402

FIRMWARE = ROOT.parent / "firmware"
KEYS = {
    0x02A40001: FIRMWARE / "cp" / "live" / "unit-02a40001.bin",
    0x02A4000D: FIRMWARE / "cp" / "live" / "unit-02a4000d.bin",
}
CHROMA_BASE = 0x1250
CHROMA_STRIDE = 64
MATRIX_BASE = 0x1E0
MATRIX_STRIDE = 768


def connect():
    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    return target, ChannelBackend(channel), legacy


def diff_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if start is None:
                start = i
        elif start is not None:
            ranges.append((start, i))
            start = None
    if start is not None:
        ranges.append((start, min(len(a), len(b))))
    return ranges


def chroma_slot(data: bytes, slot: int, base: int) -> list[int]:
    import struct

    off = base + slot * CHROMA_STRIDE
    return list(struct.unpack_from("<24h", data, off))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--read", action="store_true")
    parser.add_argument("--dump-cpapp", action="store_true")
    parser.add_argument("--restore-unit0d", default="")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    target, backend, legacy = connect()
    raw_channel = backend.channel
    try:
        if args.dump_cpapp:
            out = FIRMWARE / "cp" / "cpapp-live.bin"
            size = flash.stat(backend, "/cp/cpapp-b.bin")
            digest = hashlib.sha256()
            offset = 0
            chunks = []
            while offset < size:
                n = min(0x80000, size - offset)
                data = flash.read_range(backend, "/cp/cpapp-b.bin", offset, n)
                chunks.append(data)
                digest.update(data)
                offset += n
            blob = b"".join(chunks)
            out.write_bytes(blob)
            print(f"cpapp 备份 → {out}  {len(blob):,} B  sha256 {digest.hexdigest()}")
            local = (FIRMWARE / "cp" / "cpapp-b.bin").read_bytes()
            print(f"本地副本 sha256 {hashlib.sha256(local).hexdigest()}  一致={blob == local}")

        if args.restore_unit0d:
            source = Path(args.restore_unit0d).read_bytes()
            if len(source) != 0x7000:
                raise SystemExit("单元文件应为 28672 字节")
            if args.confirm != "yes-write":
                raise SystemExit("写入需要 --confirm yes-write")
            writer = CpWriter(target, raw_channel)
            writer.write_unit(0x02A4000D, source)
            check = writer.read_unit(0x02A4000D)
            print("写回后一致" if check == source else "写回后不一致")
            return 0

        if args.read:
            reader = CpReader(target, raw_channel)
            for key, known_path in KEYS.items():
                data = reader.read_unit(key)
                print(f"unit 0x{key:08X} {len(data)} B sha {hashlib.sha256(data).hexdigest()[:16]}")
                if known_path.exists():
                    known = known_path.read_bytes()
                    if known == data:
                        print("  与本地基线一致")
                    else:
                        ranges = diff_ranges(known, data)
                        print(f"  与本地基线差异 {len(ranges)} 段，首 6 段: {[(hex(a), hex(b)) for a, b in ranges[:6]]}")
                        (FIRMWARE / "cp" / "live" / f"unit-{key:08x}.now.bin").write_bytes(data)
                        for slot in range(0, 55):
                            try:
                                old = chroma_slot(known, slot, CHROMA_BASE) if key == 0x02A40001 else None
                                new = chroma_slot(data, slot, CHROMA_BASE) if key == 0x02A40001 else None
                            except Exception:  # noqa: BLE001
                                break
                            if old and new and old != new:
                                print(f"  chroma 槽 {slot} 变化: {old[:6]} -> {new[:6]}")
                else:
                    print("  无本地基线可对比")
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
