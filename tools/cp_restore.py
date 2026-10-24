"""把最早备份整份写回 CP 单元（用于恢复被清零/替换的色度与矩阵）。"""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp_read import CpReader
from cp_write import CpWriter

UNITS = {
    0x02A40001: "../firmware/cp/unit-02a40001.bin",
    0x02A4000D: "../firmware/cp/unit-02a4000d.bin",
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    args = parser.parse_args(argv)
    keys = [int(x, 0) for x in args.only.split(",") if x.strip()] or list(UNITS)

    from a6700win.paths import ensure_vendor_on_path, state_dir
    from a6700win import patches
    ensure_vendor_on_path()
    patches.install()
    from a6700win import windows_shim
    from a6700_unlock.usb import legacy

    with windows_shim.device_lock(state_dir()):
        target = None
        try:
            target, channel = legacy.run_authentication(None, 0x0336, 30.0, True, progress=lambda m: print(m, flush=True))
            reader, writer = CpReader(target, channel), CpWriter(target, channel)
            for key in keys:
                data = Path(UNITS[key]).read_bytes()
                print("恢复 0x%08x：备份 %d 字节 sha256=%s" % (key, len(data), hashlib.sha256(data).hexdigest()[:16]), flush=True)
                writer.write_unit(key, data)
                back = reader.read_unit(key)
                print("  回读一致=%s（%d 字节）" % (back == data, len(back)), flush=True)
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
