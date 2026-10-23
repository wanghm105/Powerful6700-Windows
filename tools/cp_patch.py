"""在一次服务模式会话里连续写入多个 CP 单元（RAM，掉电即恢复）。

用法：
    python tools/cp_patch.py 0x02a40001:file1.bin [0x02a4000d:file2.bin ...] [--keep-service]

每次写入前把相机当时的整块内容存成 <file>.orig（仅首次），写完立刻回读校验。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import patches, paths, windows_shim  # noqa: E402

paths.ensure_vendor_on_path()

from a6700_unlock.usb import legacy  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp_read import CpReader, CP_KEYS  # noqa: E402
from cp_write import CpWriter  # noqa: E402


def parse_pair(text):
    key_text, _, file_text = text.partition(":")
    if not file_text:
        raise SystemExit(f"参数格式应为 0xKEY:FILE ，收到 {text!r}")
    key = int(key_text, 16)
    if key not in CP_KEYS:
        raise SystemExit(f"不支持的 CP 单元 0x{key:08x}")
    data = Path(file_text).read_bytes()
    if len(data) != CP_KEYS[key]:
        raise SystemExit(f"{file_text} 长度 {len(data)} 与单元大小 {CP_KEYS[key]} 不符")
    return key, Path(file_text), data


def main(argv=None):
    parser = argparse.ArgumentParser(description="一次会话写入多个 CP 单元")
    parser.add_argument("pairs", nargs="+", metavar="0xKEY:FILE")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--keep-service", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    jobs = [parse_pair(text) for text in args.pairs]
    for key, path, data in jobs:
        print(f"目标单元 0x{key:08x}  {path.name}  {len(data)} B  sha256 {hashlib.sha256(data).hexdigest()}")
    if args.dry_run:
        print("dry-run：未接触相机。")
        return 0

    patches.install()
    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = channel = None
    failures = 0
    try:
        target, channel = legacy.run_authentication(None, 0x0336, args.timeout, True, progress=print)
        reader = CpReader(target, channel)
        writer = CpWriter(target, channel)
        for key, path, data in jobs:
            backup = Path(str(path) + ".orig")
            current = reader.read_unit(key)
            if not backup.exists():
                backup.write_bytes(current)
                print(f"已保存写入前备份：{backup.name}")
            else:
                print(f"已有写入前备份：{backup.name}")
            if current == data:
                print(f"0x{key:08x} 当前内容与目标一致，跳过写入。")
                continue
            started = time.monotonic()
            writer.write_unit(key, data)
            print(f"0x{key:08x} 写入完成 {time.monotonic()-started:.2f}s，回读校验…")
            after = reader.read_unit(key)
            if after == data:
                print(f"0x{key:08x} 回读一致 ✅")
            else:
                diff = sum(1 for a, b in zip(after, data) if a != b)
                print(f"0x{key:08x} 回读不一致 ❌ 差异字节 {diff}  sha256 {hashlib.sha256(after).hexdigest()}")
                failures += 1
        return 0 if failures == 0 else 2
    finally:
        if target is not None:
            if args.keep_service:
                print("保持服务模式（未发送 STOP）；观察完请拔插 USB 让相机恢复。")
            else:
                try:
                    legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
                    print("已发送退出服务模式指令。")
                except Exception as exc:
                    print(f"退出服务模式失败：{exc}；请拔插 USB")
        try:
            lock.__exit__(None, None, None)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
