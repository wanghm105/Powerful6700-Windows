# -*- coding: utf-8 -*-
"""UXC-v7 字符串资源：通用解码、就地改名与填充字节定位。

格式（与 refs/a7c2-fl23/src/looks/looktool/resources.py 一致）：
  0..7   "uxc\\x07\\0\\0\\0\\0"
  8      u16 kind（必须 8）
  10     u16 group
  12     u32 descriptor = count | (((count+1)&~1)<<12)
  16..   索引表，count 个 u16，值为 0xffff 表示该槽无记录
  base   (16+count*2+3)&~3，记录区：u32 (0x1e000000|rid&0xffffff) + UTF-8 + NUL + 补齐到 4 字节
  rid    = 0x02000000 | ((group<<13) + index)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"uxc\x07\0\0\0\0"


@dataclass
class Record:
    index: int
    rid: int
    offset: int
    text: str
    end: int          # 指向 NUL 之后第一个字节
    padding: int      # 补齐字节数（0..3）


@dataclass
class Resource:
    count: int
    group: int
    base: int
    records: list[Record]
    padded: list[Record]

    def find(self, text: str) -> list[Record]:
        return [r for r in self.records if r.text == text]


def decode(raw: bytes) -> Resource:
    if len(raw) < 16 or raw[:8] != MAGIC:
        raise ValueError("不是 UXC-v7 字符串资源")
    kind, group, descriptor = struct.unpack_from("<HHI", raw, 8)
    if kind != 8:
        raise ValueError(f"kind {kind} 不受支持")
    count = descriptor & 0x1FFF
    if not count or descriptor != count | (((count + 1) & ~1) << 12):
        raise ValueError("索引描述符不是本工具支持的形式")
    base = (16 + count * 2 + 3) & ~3
    if base >= len(raw) or len(raw) % 4:
        raise ValueError("资源长度不是 4 的倍数或索引区越界")
    records: list[Record] = []
    for index in range(count):
        (pointer,) = struct.unpack_from("<H", raw, 16 + 2 * index)
        if pointer == 0xFFFF:
            continue
        at = base + pointer * 4
        rid = 0x02000000 | ((group << 13) + index)
        if at + 5 > len(raw) or struct.unpack_from("<I", raw, at)[0] != (0x1E000000 | (rid & 0xFFFFFF)):
            raise ValueError(f"第 {index} 槽的索引与记录不一致")
        end = raw.find(b"\0", at + 4)
        if end < 0:
            raise ValueError("字符串没有结束符")
        text = raw[at + 4:end].decode("utf-8")
        nxt = (end + 4) & ~3
        if nxt > len(raw):
            raise ValueError("记录补齐越过文件末尾")
        records.append(Record(index=index, rid=rid, offset=at, text=text, end=end + 1, padding=nxt - (end + 1)))
    return Resource(count=count, group=group, base=base, records=records,
                    padded=[r for r in records if r.padding])


def patch_text(raw: bytes, record: Record, text: str) -> bytes:
    """就地替换同一条记录的文字；不移动索引，因此要求新文字不超过原记录长度。"""
    encoded = text.encode("utf-8")
    if not 1 <= len(encoded) <= 63:
        raise ValueError("名字必须是 1..63 字节 UTF-8")
    if any(ch < 32 for ch in encoded):
        raise ValueError("名字不能含控制字符")
    room = record.end - 4 - record.offset
    if len(encoded) > room:
        raise ValueError(f"新文字 {len(encoded)} 字节超过原记录容量 {room} 字节")
    body = bytearray(raw)
    body[record.offset + 4:record.offset + 4 + len(encoded)] = encoded
    body[record.offset + 4 + len(encoded):record.offset + 4 + room] = b"\0" * (room - len(encoded))
    return bytes(body)


def main(argv: list[str]) -> int:
    import sys
    from pathlib import Path

    if not argv:
        print("用法: uxc.py <文件> [--find 文字] [--pads]")
        return 2
    raw = Path(argv[0]).read_bytes()
    resource = decode(raw)
    print(f"count={resource.count} group={resource.group} base={resource.base:#x} "
          f"records={len(resource.records)} 有补齐的={len(resource.padded)}")
    if "--pads" in argv:
        for record in resource.padded[:12]:
            print(f"  0x{record.offset + 4 + len(record.text.encode()):08x} pad={record.padding} rid=0x{record.rid:06x} {record.text[:24]!r}")
    if "--find" in argv:
        needle = argv[argv.index("--find") + 1]
        for record in resource.find(needle):
            print(f"  0x{record.offset:08x} rid=0x{record.rid:06x} index={record.index} {record.text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
