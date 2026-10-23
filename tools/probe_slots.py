"""零化指定 CP 色度槽，用于把「菜单外观」和「CP 槽号」对上（只改内存，掉电恢复）。

用法： python tools/probe_slots.py --zero 0,1,2,3 [--key 0x02a40001]
"""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp_read import CpReader, CP_KEYS  # noqa: E402
from cp_write import CpWriter  # noqa: E402

CHROMA_BASE = 0x1250
CHROMA_SIZE = 64
SENSER_MIN = 0x200


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--zero", default="")
    parser.add_argument("--key", default="0x02a40001")
    parser.add_argument("--out", default="../firmware/cp")
    parser.add_argument("--base", default="")
    args = parser.parse_args(argv)
    key = int(args.key, 0)
    slots = [int(x) for x in args.zero.split(",") if x.strip()]

    from a6700win.paths import ensure_vendor_on_path, state_dir
    from a6700win import patches
    ensure_vendor_on_path()
    patches.install()
    from a6700win import windows_shim
    from a6700_unlock.usb import legacy

    with windows_shim.device_lock(state_dir()):
        reader = CpReader(None, None)
        target = None
        try:
            target, channel = legacy.run_authentication(None, 0x0336, 25.0, True, progress=lambda m: print(m, flush=True))
            reader.target = target
            reader.channel = channel
            writer = CpWriter(target, channel)
            base_path = Path(args.base) if args.base else None
            unit = base_path.read_bytes() if base_path and base_path.exists() else reader.read_unit(key)
            out = Path(args.out) / ("unit-%08x.zero_%s.bin" % (key, "_".join(str(s) for s in slots)))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(unit)
            print("当前单元 sha256=%s -> %s" % (hashlib.sha256(unit).hexdigest()[:16], out), flush=True)
            data = bytearray(unit)
            for slot in slots:
                start = CHROMA_BASE + slot * CHROMA_SIZE
                if start + CHROMA_SIZE > len(data):
                    print("槽 %d 越界" % slot, flush=True)
                    continue
                data[start:start + CHROMA_SIZE] = bytes(CHROMA_SIZE)
            patched = bytes(data)
            writer.write_unit(key, patched)
            back = reader.read_unit(key)
            same = back == patched
            print("写入回读一致=%s 变更字节=%d" % (same, sum(1 for a, b in zip(unit, patched) if a != b)), flush=True)
            print("已零化槽：%s（相机断电即恢复）" % slots, flush=True)
        finally:
            if target is not None:
                try:
                    legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
                except Exception as exc:
                    print("STOP 失败：%s" % exc, flush=True)
                try:
                    legacy.close_target(target)
                except Exception:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
