"""读 /setting 下任意文件（可多个）并保存到本地，一次会话完成。"""
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

from look_name import ChannelBackend  # noqa: E402

CHUNK = 0x80000


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", action="append", required=True,
                        help="相机路径，例如 /setting/PSD.BIN")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    backend = ChannelBackend(channel)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        for path in args.file:
            size = flash.stat(backend, path)
            blob = bytearray()
            while len(blob) < size:
                want = min(CHUNK, size - len(blob))
                blob += flash.read_range(backend, path, len(blob), want)
            name = Path(path).name
            out = out_dir / name
            out.write_bytes(bytes(blob))
            print(f"{path} = {size:,} B -> {out} sha256 {hashlib.sha256(blob).hexdigest()[:32]}")
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
