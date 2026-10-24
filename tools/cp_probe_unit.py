# -*- coding: utf-8 -*-
"""Probe a CP data unit: zero it for a moment, then restore the snapshot.

Every probe snapshots the original bytes first, writes the probe pattern,
holds for --hold seconds so the operator can watch the live image, then writes
the original back and verifies the readback. Nothing touches flash.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import patches, paths, windows_shim  # noqa: E402

paths.ensure_vendor_on_path()
from a6700_unlock.usb import legacy  # noqa: E402

import cp_read  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402
from cp_survey import catalog  # noqa: E402


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CP 单元清零探测（可回写）")
    parser.add_argument("--key", action="append", required=True,
                        help="要探测的单元，可重复，例如 --key 0x02a4000e")
    parser.add_argument("--hold", type=float, default=10.0, help="每次保持秒数")
    parser.add_argument("--gap", type=float, default=6.0, help="两次探测之间的间隔")
    parser.add_argument("--pattern", choices=("zero", "half"), default="zero")
    parser.add_argument("--out", default=str(ROOT.parent / "firmware" / "cp" / "probe"))
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args(argv)

    units = {key: size for key, _ram, size in catalog()}
    keys = [int(k, 16) for k in args.key]
    for key in keys:
        if key not in units:
            raise SystemExit(f"单元 0x{key:08x} 不在目录里")
    cp_read.CP_KEYS.update({key: units[key] for key in keys})

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    patches.install()
    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = channel = None
    failures = []
    try:
        target, channel = legacy.run_authentication(None, 0x0336, args.timeout, True, progress=log)
        reader = CpReader(target, channel)
        writer = CpWriter(target, channel)
        for index, key in enumerate(keys, start=1):
            size = units[key]
            log(f"第 {index} 段：读取 0x{key:08x}（{size} 字节）原始内容")
            original = reader.read_unit(key)
            snapshot = out_dir / f"unit-{key:08x}-orig.bin"
            snapshot.write_bytes(original)
            log(f"  快照 {snapshot.name} sha256 {hashlib.sha256(original).hexdigest()[:16]}")

            if args.pattern == "zero":
                probe = bytes(size)
            else:
                probe = bytes((b >> 1) for b in original)

            try:
                writer.write_unit(key, probe)
                log(f"  已写入探测值，保持 {args.hold:.0f} 秒 —— 请看相机屏幕")
                time.sleep(args.hold)
            finally:
                log("  正在写回原始内容")
                writer.write_unit(key, original)
                back = reader.read_unit(key)
                if back == original:
                    log("  回读一致，单元已复原")
                else:
                    failures.append(key)
                    log("  !!! 回读不一致，请立即断电或再次运行写回")
            if index < len(keys):
                log(f"  等待 {args.gap:.0f} 秒后进入下一段")
                time.sleep(args.gap)
    finally:
        if target is not None:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            except Exception:
                pass
            legacy.close_target(target)
    if failures:
        log("有单元未能复原：" + ", ".join(f"0x{key:08x}" for key in failures))
        return 1
    log("全部完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
