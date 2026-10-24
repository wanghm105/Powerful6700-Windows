# -*- coding: utf-8 -*-
"""单字节持久性验证：改一个对解码无影响的填充字节，断电重启后回读确认。

目标位置是 UXC 资源里某条记录末尾的补齐字节（解码在 NUL 处停止，因此这一字节
不参与任何语义），改写它既能验证「写入真的落到闪存」，又不会影响界面。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import flash, paths  # noqa: E402
from a6700win.research import ServiceSession  # noqa: E402

TARGET = "/usr/share/app/string_simplifiedchinese.uxc"
OFFSET = 0x1CD8          # '子网掩码' 记录之后的 3 个补齐字节之一
LOG = None


def _log_path() -> Path:
    global LOG
    if LOG is None:
        directory = paths.data_root() / "flash-log"
        directory.mkdir(parents=True, exist_ok=True)
        LOG = directory / "persist-byte.json"
    return LOG


def read_byte(session, offset: int, length: int = 1) -> bytes:
    return flash.read_range(session, TARGET, offset, length)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="单字节持久性验证")
    parser.add_argument("action", choices=["write", "check", "restore"])
    args = parser.parse_args(argv)

    with ServiceSession(progress=lambda message: print(message, flush=True)) as session:
        context = read_byte(session, OFFSET - 8, 12)
        print(f"上下文 {context.hex(' ')}", flush=True)
        if args.action == "write":
            original = read_byte(session, OFFSET, 1)
            if original == b"\xff":
                raise SystemExit("该位置已经是 0xff，换一个偏移再试")
            value = bytes([original[0] ^ 0xFF])
            print(f"原值 {original.hex()} → 写入 {value.hex()}", flush=True)
            flash.write_block(session, TARGET, OFFSET, value)
            after = read_byte(session, OFFSET, 1)
            print(f"回读 {after.hex()} ({'一致' if after == value else '不一致'})", flush=True)
            _log_path().write_text(json.dumps({"target": TARGET, "offset": OFFSET,
                                               "original": original.hex(), "written": value.hex()},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"记录写入 {_log_path()}", flush=True)
        elif args.action == "check":
            now = read_byte(session, OFFSET, 1)
            print(f"当前值 {now.hex()}", flush=True)
        else:
            record = json.loads(_log_path().read_text(encoding="utf-8"))
            original = bytes.fromhex(record["original"])
            flash.write_block(session, TARGET, OFFSET, original)
            after = read_byte(session, OFFSET, 1)
            print(f"恢复为 {after.hex()} ({'一致' if after == original else '不一致'})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
