# -*- coding: utf-8 -*-
"""UXC-v7 字符串资源：解码、就地改名、可增长改名。

格式（与 refs/a7c2-fl23/src/looks/looktool/resources.py 一致）：
  0..7   "uxc\\x07\\0\\0\\0\\0"
  8      u16 kind（必须 8）
  10     u16 group
  12     u32 descriptor = count | (((count+1)&~1)<<12)
  16..   索引表，count 个 u16，值为 0xffff 表示该槽无记录
  base   (16+count*2+3)&~3，记录区：u32 (0x1e000000|rid&0xffffff) + UTF-8 + NUL + 补齐到 4 字节
  rid    = 0x02000000 | ((group<<13) + index)

两种改名：
- patch_text：新文字不长于原记录容量，就地替换，索引表一个字都不动；
- grow：任意长度（≥1 字节），整块后移并重写索引表，文件长度随之变化。

为什么需要 grow：菜单里原本是 "PT" 这种两字母缩写，要写「富士CC」就必须加长；
就地替换装不下，只能重排。重排是确定性的、可逆的（把文字改回短名即可再缩回去），
但缩回去的文件与出厂文件不逐字节相同 —— 要逐字节还原，靠的是写入前保存的整份基线。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"uxc\x07\0\0\0\0"

# 名字上限：相机菜单一行很短，写太长只会被截断；200 字节足够任何语言。
TEXT_MAX = 200


class UxcError(ValueError):
    """资源格式不符或改名越界。"""


@dataclass
class Record:
    index: int
    rid: int
    offset: int
    text: str
    end: int          # 指向 NUL 之后第一个字节
    padding: int      # 补齐字节数（0..3）

    @property
    def capacity(self) -> int:
        """本条记录（不含 rid 头部）能装下的文字字节数。"""
        return self.end - 4 - self.offset


@dataclass
class Resource:
    count: int
    group: int
    base: int
    records: list[Record]

    def find(self, text: str) -> list[Record]:
        return [r for r in self.records if r.text == text]

    def by_rid(self) -> dict[int, Record]:
        return {r.rid: r for r in self.records}


def decode(raw: bytes) -> Resource:
    if len(raw) < 16 or raw[:8] != MAGIC:
        raise UxcError("不是 UXC-v7 字符串资源")
    kind, group, descriptor = struct.unpack_from("<HHI", raw, 8)
    if kind != 8:
        raise UxcError(f"kind {kind} 不受支持")
    count = descriptor & 0x1FFF
    if not count or descriptor != count | (((count + 1) & ~1) << 12):
        raise UxcError("索引描述符不是本工具支持的形式")
    base = (16 + count * 2 + 3) & ~3
    if base >= len(raw) or len(raw) % 4:
        raise UxcError("资源长度不是 4 的倍数或索引区越界")
    records: list[Record] = []
    for index in range(count):
        (pointer,) = struct.unpack_from("<H", raw, 16 + 2 * index)
        if pointer == 0xFFFF:
            continue
        at = base + pointer * 4
        rid = 0x02000000 | ((group << 13) + index)
        if at + 5 > len(raw) or struct.unpack_from("<I", raw, at)[0] != (0x1E000000 | (rid & 0xFFFFFF)):
            raise UxcError(f"第 {index} 槽的索引与记录不一致")
        end = raw.find(b"\0", at + 4)
        if end < 0:
            raise UxcError("字符串没有结束符")
        text = raw[at + 4:end].decode("utf-8", "strict")
        nxt = (end + 4) & ~3
        if nxt > len(raw):
            raise UxcError("记录补齐越过文件末尾")
        records.append(Record(index=index, rid=rid, offset=at, text=text,
                              end=end + 1, padding=nxt - (end + 1)))
    return Resource(count=count, group=group, base=base, records=records)


def _encode(text: str) -> bytes:
    if not text:
        raise UxcError("名字不能为空")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise UxcError(f"名字无法编码为 UTF-8：{exc}") from exc
    if len(encoded) > TEXT_MAX:
        raise UxcError(f"名字最多 {TEXT_MAX} 字节（当前 {len(encoded)}）")
    if any(ch < 32 or ch == 127 for ch in encoded):
        raise UxcError("名字不能含控制字符")
    return encoded


def patch_text(raw: bytes, record: Record, text: str) -> bytes:
    """就地替换同一条记录的文字；不移动索引，因此要求新文字不超过原记录容量。"""
    encoded = _encode(text)
    room = record.capacity
    if len(encoded) > room:
        raise UxcError(f"新文字 {len(encoded)} 字节超过原记录容量 {room} 字节")
    body = bytearray(raw)
    body[record.offset + 4:record.offset + 4 + len(encoded)] = encoded
    body[record.offset + 4 + len(encoded):record.offset + 4 + room] = b"\0" * (room - len(encoded))
    return bytes(body)


def grow(raw: bytes, rid: int, text: str) -> tuple[bytes, int]:
    """把 rid 的文字换成任意长度的 text：重排记录块与索引表。

    返回 (新文件字节, 该记录在新文件里的偏移)。新文件长度是 4 的倍数；
    除本条记录外，后续记录整体平移，索引表按新偏移重写，内容一个字节都不改。
    """
    encoded = _encode(text)
    resource = decode(raw)
    target = resource.by_rid().get(rid)
    if target is None:
        raise UxcError(f"找不到 rid 0x{rid:08x}")
    if target.text == text:
        return raw, target.offset

    at = target.offset
    old_len = ((target.end + 3) & ~3) - at
    new_block = struct.pack("<I", 0x1E000000 | (rid & 0xFFFFFF)) + encoded + b"\0"
    new_block += b"\0" * ((-len(new_block)) % 4)
    delta = len(new_block) - old_len
    if delta % 4:
        raise UxcError("内部错误：增长量不是 4 的倍数")

    body = bytearray(raw[:at]) + bytearray(new_block) + bytearray(raw[at + old_len:])
    for record in resource.records:
        if record.rid == rid:
            new_offset = at
        elif record.offset > at:
            new_offset = record.offset + delta
        else:
            continue
        pointer = (new_offset - resource.base) // 4
        if not 0 <= pointer <= 0xFFFF:
            raise UxcError("索引指针越界")
        struct.pack_into("<H", body, 16 + 2 * record.index, pointer)
    if len(body) % 4:
        raise UxcError("内部错误：文件长度不是 4 的倍数")
    return bytes(body), at


def rename_all(raw: bytes, edits: dict[int, str]) -> tuple[bytes, list[dict]]:
    """按 {rid: text} 依次改名；返回 (新文件, 每条实际变化的记录)。"""
    body = raw
    done: list[dict] = []
    for rid, text in edits.items():
        before = decode(body).by_rid().get(rid)
        if before is None:
            raise UxcError(f"找不到 rid 0x{rid:08x}")
        if before.text == text:
            continue
        body, at = grow(body, rid, text)
        done.append({"rid": rid, "old": before.text, "new": text, "offset": at})
    return body, done


def texts(raw: bytes, rids) -> dict[int, str]:
    """只取指定 rid 的当前文字（缺失的 rid 不在结果里）。"""
    table = decode(raw).by_rid()
    return {rid: table[rid].text for rid in rids if rid in table}
