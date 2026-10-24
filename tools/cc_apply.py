"""一次会话内完成两件事（避免反复切 MSC）：

1. 把 CP 单元 0x02a4000d 的色度槽 9（SE）从 0x11 标记恢复成基线值
2. 把 cpapp 的 9 条 1024 B 曲线改写成指定形状（默认 gamma22）并逐块回读校验

用法：
  python tools/cc_apply.py --shape gamma22 --confirm yes-write
  python tools/cc_apply.py --shape identity --confirm yes-write   # 还原曲线
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

from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402
from look_name import ChannelBackend  # noqa: E402

FIRMWARE = ROOT.parent / "firmware"
UNIT0D = 0x02A4000D
CHROMA_BASE = 0x1250
CHROMA_STRIDE = 64
SLOT_BASE = 0xFE0B50
SLOT_STRIDE = 0x400
SLOT_COUNT = 9
CPAPP = "/cp/cpapp-b.bin"


def curve(shape: str) -> list[int]:
    import importlib.util

    spec = importlib.util.spec_from_file_location("cpapp_curve", ROOT / "tools" / "cpapp_curve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.shape(shape)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape", default="gamma22")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--keep-service", action="store_true")
    parser.add_argument("--skip-unit0d", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    backend = ChannelBackend(channel)
    try:
        if not args.skip_unit0d:
            reader = CpReader(target, channel)
            live = reader.read_unit(UNIT0D)
            base = (FIRMWARE / "cp" / "live" / "unit-02a4000d.bin").read_bytes()
            off = CHROMA_BASE + 9 * CHROMA_STRIDE
            live_slot = live[off : off + CHROMA_STRIDE]
            base_slot = base[off : off + CHROMA_STRIDE]
            print(f"SE 色度槽现状 {live_slot[:8].hex()} … 基线 {base_slot[:8].hex()}")
            if live_slot != base_slot:
                patched = bytearray(live)
                patched[off : off + CHROMA_STRIDE] = base_slot
                writer = CpWriter(target, channel)
                writer.write_unit(UNIT0D, bytes(patched))
                check = reader.read_unit(UNIT0D)
                print("SE 槽恢复后回读一致" if check == bytes(patched) else "SE 槽恢复后回读不一致")

        record = struct.pack("<512H", *curve(args.shape))
        assert len(record) == SLOT_STRIDE
        digest = hashlib.sha256()
        for i in range(SLOT_COUNT):
            offset = SLOT_BASE + i * SLOT_STRIDE
            current = flash.read_range(backend, CPAPP, offset, SLOT_STRIDE)
            flash.write_block(backend, CPAPP, offset, record)
            check = flash.read_range(backend, CPAPP, offset, SLOT_STRIDE)
            digest.update(check)
            print(f"  曲线槽 {i} @0x{offset:X} 回读{'一致' if check == record else '不一致'}")
            if check != record:
                raise SystemExit("回读不一致，中止")
        print(f"9 条曲线已改写为 {args.shape}，sha256 {digest.hexdigest()[:16]}")
        print("请关机重启，然后拍 ST / PT(CC) 各一张对比影调")
    finally:
        if not args.keep_service:
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
