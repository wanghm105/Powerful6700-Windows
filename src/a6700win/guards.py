
"""结构守卫的时间戳豁免（Windows 移植层）。

上游 device-profile 的「结构守卫」按 sha256 全字节钉死若干 512 字节扇区，用来确认
相机固件没有被换过。问题在于：其中 9 个扇区落在 /usr 分区（nflasha15，ext2）的
inode 表里，相机自己每次开机读写文件都会刷新 inode 的 atime/ctime/mtime，于是
守卫在用户什么都没做的情况下判定不匹配，界面上表现为「兼容性检查未通过 / blocked」。

本模块只做一件很窄的事：对数据表里登记过的那几个 inode 守卫扇区，
- 比对前把每个 256 字节 inode 记录里的 atime/ctime/mtime（偏移 0x08–0x14）清零；
- 同时把该守卫的期望 sha256 换成「清零后」的期望值。
其余字节（mode/uid/gid/size/blocks 以及另一个 inode 的全部内容、扇区里的其它字节）
仍然逐字节校验，固件真被换掉时照样会 blocked。

数据表由 tools/gen_guard_overlay.py 从本机固件镜像生成，schema 见
src/a6700win/data/guard-overlay.json。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

OVERLAY_PATH = Path(__file__).resolve().parent / "data" / "guard-overlay.json"

_cache: dict | None = None
_wrapped = False


class GuardOverlayError(RuntimeError):
    """豁免表缺失或格式不对。"""


def overlay() -> dict:
    """读取并校验豁免表（进程内缓存）。"""
    global _cache
    if _cache is not None:
        return _cache
    try:
        data = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GuardOverlayError("缺少结构守卫豁免表：%s" % exc) from exc
    if data.get("schema") != "a6700win/guard-overlay/1":
        raise GuardOverlayError("结构守卫豁免表版本不支持：%r" % (data.get("schema"),))
    size = int(data.get("inode_size") or 0)
    if size <= 0 or size > 512:
        raise GuardOverlayError("结构守卫豁免表的 inode 大小不合法：%r" % (size,))
    _cache = data
    return data


def records() -> dict[int, dict]:
    return {int(key): value for key, value in (overlay().get("records") or {}).items()}


def normalize(sector: bytes) -> bytes:
    """把 inode 记录里的时间戳字段清零；长度不合法时原样返回。"""
    data = overlay()
    size = int(data["inode_size"])
    fields = [(int(start), int(end)) for start, end in data.get("volatile") or []]
    if not fields or len(sector) % size:
        return bytes(sector)
    buf = bytearray(sector)
    for base in range(0, len(buf), size):
        for start, end in fields:
            if 0 <= start < end <= size:
                buf[base + start:base + end] = b"\0" * (end - start)
    return bytes(buf)


def digest(sector: bytes) -> str:
    return hashlib.sha256(normalize(sector)).hexdigest()


def prepare(profile, sectors: list[bytes]) -> list[bytes]:
    """就地登记豁免：返回清零时间戳后的扇区副本，并修正守卫的期望哈希。"""
    table = records()
    if not table:
        return list(sectors)
    prepared = list(sectors)
    for index, entry in table.items():
        if index >= len(profile.entries):
            continue
        row = profile.entries[index]
        if row.get("role") != "guard":
            continue
        expected = entry.get("normalized_sha256")
        if not expected:
            continue
        row["sha256"] = expected
        row["_a6700win_normalized"] = True
        if index < len(prepared) and len(prepared[index]) == 512:
            prepared[index] = normalize(prepared[index])
    return prepared


def wrap_inspect(original):
    """包一层 inspect_sectors：先做豁免准备，再交给上游原函数。"""

    def inspect_sectors(profile, sectors, action="inspect", features=None):
        return original(profile, prepare(profile, list(sectors)), action, features)

    inspect_sectors._a6700win_wrapped = True
    inspect_sectors._a6700win_original = original
    return inspect_sectors


def install() -> list[str]:
    """替换 device_profile / operations 两个模块里的 inspect_sectors。"""
    global _wrapped
    from a6700_unlock import device_profile, operations

    applied = []
    for module in (device_profile, operations):
        current = getattr(module, "inspect_sectors", None)
        if current is None or getattr(current, "_a6700win_wrapped", False):
            continue
        wrapped = wrap_inspect(current)
        wrapped.__name__ = "inspect_sectors"
        wrapped.__doc__ = current.__doc__
        module.inspect_sectors = wrapped
        applied.append(module.__name__ + ".inspect_sectors")
    if applied:
        _wrapped = True
    return applied


def status() -> dict:
    """给诊断页用：有多少守卫扇区参与时间戳豁免。"""
    try:
        table = records()
    except GuardOverlayError as exc:
        return dict(ok=False, detail=str(exc), count=0, indices=[])
    return dict(
        ok=True,
        detail="%d 个 inode 守卫扇区只比对内容、放行时间戳漂移" % len(table),
        count=len(table),
        indices=sorted(table),
    )
