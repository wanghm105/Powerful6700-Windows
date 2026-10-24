"""UXC-v7 改名（可增长）：把某条记录的文字换成长名字，整体后移并重写索引表。

用法（离线预览/校验）：
  python tools/uxc_grow.py --file ../firmware/uxc/orig.bin --set 0x021c6654="Fuji Classic Chrome" --out /tmp/x.bin
用法（真机写入）：
  python tools/uxc_grow.py --set 0x021c6654="Fuji Classic Chrome" --confirm yes-write
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import flash, patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

import uxc  # noqa: E402
from channel_backend import ChannelBackend  # noqa: E402

TARGET = "/usr/share/app/string_simplifiedchinese_f.uxc"
BACKUP_DIR = ROOT.parent / "firmware" / "uxc"


def grow(raw: bytes, rid: int, text: str) -> tuple[bytes, int]:
    """返回 (新文件, 记录所在新偏移)。"""
    resource = uxc.decode(raw)
    target = next((r for r in resource.records if r.rid == rid), None)
    if target is None:
        raise SystemExit(f"找不到 rid 0x{rid:06x}")
    encoded = text.encode("utf-8")
    if not 1 <= len(encoded) <= 200:
        raise SystemExit("名字必须是 1..200 字节 UTF-8")
    if any(ch < 32 for ch in encoded):
        raise SystemExit("名字不能含控制字符")

    at = target.offset
    old_len = ((target.end + 3) & ~3) - at
    new_block = struct.pack("<I", 0x1E000000 | (rid & 0xFFFFFF)) + encoded + b"\0"
    new_block += b"\0" * ((-len(new_block)) % 4)
    delta = len(new_block) - old_len
    if delta % 4:
        raise SystemExit("内部错误：增长量不是 4 的倍数")

    body = bytearray(raw[:at]) + bytearray(new_block) + bytearray(raw[at + old_len:])
    # 重写索引表：本记录指向新块起点；其后（严格大于 at）的记录整体后移 delta
    for record in resource.records:
        if record.rid == rid:
            target_offset = at
        elif record.offset > at:
            target_offset = record.offset + delta
        else:
            continue
        pointer = (target_offset - resource.base) // 4
        struct.pack_into("<H", body, 16 + 2 * record.index, pointer)
    if len(body) % 4:
        raise SystemExit("内部错误：文件长度不是 4 的倍数")
    return bytes(body), at


def verify(raw: bytes, expect: dict[int, str]) -> None:
    resource = uxc.decode(raw)
    for record in resource.records:
        want = expect.get(record.rid)
        if want is not None and record.text != want:
            raise SystemExit(f"校验失败：rid 0x{record.rid:06x} 期望 {want!r} 实得 {record.text!r}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="")
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--out", default="")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--keep-service", action="store_true")
    args = parser.parse_args(argv)

    edits: dict[int, str] = {}
    for item in args.set:
        rid_text, _, text = item.partition("=")
        edits[int(rid_text, 0)] = text

    if args.file:
        raw = Path(args.file).read_bytes()
        body = raw
        for rid, text in edits.items():
            body, at = grow(body, rid, text)
            print(f"rid 0x{rid:06x} → {text!r}（新偏移 0x{at:06x}，文件 {len(raw)} → {len(body)}）")
        verify(body, edits)
        print(f"离线校验通过：{len(body)} 字节 sha256 {hashlib.sha256(body).hexdigest()[:16]}")
        if args.out:
            Path(args.out).write_bytes(body)
            print(f"已写出 {args.out}")
        if args.confirm != "yes-write":
            print("（未给 --confirm yes-write，仅预览）")
        return 0

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    backend = ChannelBackend(channel)
    try:
        size = flash.stat(backend, TARGET)
        live = flash.read_range(backend, TARGET, 0, size)
        print(f"当前资源 {size} 字节 sha256 {hashlib.sha256(live).hexdigest()[:16]}")
        body = live
        for rid, text in edits.items():
            body, at = grow(body, rid, text)
            print(f"rid 0x{rid:06x} → {text!r}（新偏移 0x{at:06x}，{size} → {len(body)}）")
        verify(body, edits)
        print(f"离线校验通过：{len(body)} 字节 sha256 {hashlib.sha256(body).hexdigest()[:16]}")
        if args.confirm != "yes-write":
            print("（未给 --confirm yes-write，未写入）")
            return 0
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = BACKUP_DIR / f"string_simplifiedchinese_f.uxc.{stamp}.bin"
        backup.write_bytes(live)
        print(f"已备份 → {backup}")
        flash.truncate(backend, TARGET, len(body))
        for offset in range(0, len(body), flash.BLOCK):
            chunk = body[offset:offset + flash.BLOCK]
            flash.write_block(backend, TARGET, offset, chunk)
        print("写入完成，回读校验…")
        got = flash.read_range(backend, TARGET, 0, len(body))
        if got != body:
            raise SystemExit("回读不一致！请用备份还原")
        print("回读校验通过，重启相机后生效。")
    finally:
        if not args.keep_service:
            legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            legacy.close_target(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
