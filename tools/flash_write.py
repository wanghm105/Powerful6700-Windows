"""机身文件写入（需要显式确认；默认只做零变化的 probe 自检）。

用法：
    python tools/flash_write.py --probe                     # 只读+写回同样的字节，证明写入链路可用
    python tools/flash_write.py --stat                      # 列出目标文件长度与挂载状态
    python tools/flash_write.py --verify BACKUP --target cpapp --offset 0x1000 --length 0x200
    python tools/flash_write.py --write-hex 0x1000 00112233 --target cpapp --confirm yes-write

--probe 写的是它自己刚读出来的字节，语义零变化；--write-hex / --write-file 必须带
--confirm yes-write，并且写前会先把该范围的现有字节读出来做 SHA-256 记录。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import flash  # noqa: E402

LOG = ROOT / ".data" / "flash-log"


def target_path(name: str) -> str:
    if name in flash.TARGETS:
        return flash.TARGETS[name]["path"]
    if name.startswith("/"):
        return name
    raise SystemExit(f"未知目标 {name}；可用 {', '.join(sorted(flash.TARGETS))} 或绝对路径")


def record(entry: dict) -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-flash.json"
    (LOG / name).write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="A6700 机身文件写入（显式确认）")
    parser.add_argument("--target", default="cpapp", help="appfw / cpapp / 绝对路径")
    parser.add_argument("--probe", action="store_true", help="零变化写入自检")
    parser.add_argument("--stat", action="store_true")
    parser.add_argument("--offset", default="0x0")
    parser.add_argument("--length", default="0x200")
    parser.add_argument("--verify", metavar="BACKUP", help="把相机上的该范围与本地备份文件比对")
    parser.add_argument("--write-hex", nargs=2, metavar=("OFFSET", "HEX"))
    parser.add_argument("--write-file", nargs=2, metavar=("OFFSET", "FILE"))
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    path = target_path(args.target)
    offset = int(args.offset, 0)
    length = int(args.length, 0)

    from a6700win.research import ServiceSession

    elf = flash.payload()
    print(f"载荷 flash_write.elf sha256 {hashlib.sha256(elf).hexdigest()}", flush=True)
    print(f"目标 {path}", flush=True)

    with ServiceSession(progress=lambda message: print(message, flush=True)) as session:
        size = flash.stat(session, path, elf)
        print(f"长度 {size:,} 字节（0x{size:x}）", flush=True)
        if args.stat:
            return 0
        if args.probe:
            done = flash.probe(session, path, offset, min(length, flash.BLOCK), elf)
            entry = dict(action="probe", path=path, offset=offset, length=done["length"],
                         verified=True, payload_sha256=hashlib.sha256(elf).hexdigest())
            record(entry)
            print("probe 成功：写入相同字节并经回读校验。", flush=True)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            return 0
        if args.verify:
            backup = Path(args.verify)
            data = backup.read_bytes()
            if offset + length > len(data):
                raise SystemExit("范围超出备份文件")
            current = flash.read_range(session, path, offset, length, elf)
            expected = data[offset:offset + length]
            match = current == expected
            print(f"相机内容 sha256 {hashlib.sha256(current).hexdigest()}", flush=True)
            print(f"备份内容 sha256 {hashlib.sha256(expected).hexdigest()}", flush=True)
            print("一致" if match else "不一致（先不要写）", flush=True)
            return 0 if match else 3
        block = None
        if args.write_hex:
            offset = int(args.write_hex[0], 0)
            block = bytes.fromhex(args.write_hex[1])
        elif args.write_file:
            offset = int(args.write_file[0], 0)
            block = Path(args.write_file[1]).read_bytes()
        if block is None:
            parser.error("需要 --stat / --probe / --verify / --write-hex / --write-file 之一")
        if args.confirm != "yes-write":
            raise SystemExit("写入必须带 --confirm yes-write")
        if len(block) > flash.BLOCK:
            raise SystemExit(f"单块最多 {flash.BLOCK} 字节")
        before = flash.read_range(session, path, offset, len(block), elf)
        print(f"写入前 sha256 {hashlib.sha256(before).hexdigest()}", flush=True)
        done = flash.write_block(session, path, offset, block, elf)
        after = flash.read_range(session, path, offset, len(block), elf)
        match = after == block
        entry = dict(action="write", path=path, offset=offset, length=len(block),
                     before_sha256=hashlib.sha256(before).hexdigest(),
                     after_sha256=hashlib.sha256(after).hexdigest(),
                     expected_sha256=hashlib.sha256(block).hexdigest(),
                     verified=match, payload_sha256=hashlib.sha256(elf).hexdigest())
        record(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        return 0 if match else 4


if __name__ == "__main__":
    raise SystemExit(main())
