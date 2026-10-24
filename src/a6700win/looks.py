# -*- coding: utf-8 -*-
"""自定义外观（CC / NC / 理光正片 / 理光负片）的写入与自检。

配方来自 docs/looks-profile.json：每个外观记 64 字节写入值 record_hex 与 64
字节出厂值 factory_hex。GUI 直接按这两份十六进制改写 CP 单元 0x02A40001 的
色度记录，运行时不需要固件副本，冻结包同样可用。

为什么不现算：早期配方是「基底记录 × 系数 + 某一组 (Cb,Cr) 缩放」，重算需要
出厂副本；烘成十六进制后，运行时只剩「读 → 换四条记录 → 回读」，路径更短，
也更容易在界面上讲清楚。

安全边界：
- 只动 4 条记录（bank 1/4/6/14）；写前后逐条比对，其它记录有任何变化都报告；
- 写完立刻回读，不一致直接报失败，不重试；
- 只改 RAM，不碰 flash；要持久必须让相机正常关机一次（它会自己写 BACKUP.BIN）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import cp, paths

UNIT = cp.CHROMA_UNIT
CHROMA_BASE = 0x1250
STRIDE = 64
BANKS = 32


class LooksError(RuntimeError):
    """配方缺失或写入链路失败。"""


def profile_path() -> Path:
    for candidate in (
        paths.bundled_root() / "docs" / "looks-profile.json",
        paths.project_root() / "docs" / "looks-profile.json",
        paths.project_root().parent / "docs" / "looks-profile.json",
    ):
        if candidate.is_file():
            return candidate
    raise LooksError("缺少 docs/looks-profile.json，无法确定要写入的配方。")


def profile() -> list[dict]:
    data = json.loads(profile_path().read_text(encoding="utf-8"))
    looks = data.get("looks") or []
    if not looks:
        raise LooksError("looks-profile.json 里没有任何外观条目。")
    seen: set[int] = set()
    for item in looks:
        for key in ("record_hex", "factory_hex"):
            raw = bytes.fromhex(item[key])
            if len(raw) != STRIDE:
                raise LooksError(str(item.get("name")) + " 的 " + key + " 不是 64 字节。")
            item[key] = raw
        bank = int(item["bank"])
        if not 0 <= bank < BANKS:
            raise LooksError(str(item.get("name")) + " 的 bank 越界：" + str(bank))
        if bank in seen:
            raise LooksError("两个外观指向同一条记录 bank " + str(bank) + "。")
        seen.add(bank)
        item["bank"] = bank
    return looks


def classify(current: bytes, item: dict) -> str:
    """一条记录的三种状态：写入了配方 / 仍是出厂 / 被别的东西改过。"""
    if current == item["record_hex"]:
        return "installed"
    if current == item["factory_hex"]:
        return "factory"
    return "other"


def record(unit: bytes, bank: int) -> bytes:
    offset = CHROMA_BASE + bank * STRIDE
    return unit[offset:offset + STRIDE]


def _splice(unit: bytes, item: dict, key: str) -> bytes:
    offset = CHROMA_BASE + item["bank"] * STRIDE
    out = bytearray(unit)
    out[offset:offset + STRIDE] = item[key]
    return bytes(out)


def changed_banks(before: bytes, after: bytes, targets: set[int]) -> list[int]:
    """写入前后，除目标记录外还有哪些记录变了（正常应为空）。"""
    if len(before) != len(after):
        raise LooksError("两次读取的单元长度不同，结果不可比。")
    return [bank for bank in range(BANKS)
            if bank not in targets and record(before, bank) != record(after, bank)]


def read_state(progress=lambda message: None) -> dict:
    """只读：报告四条记录现在处于哪种状态。"""
    looks = profile()
    with cp.session(progress) as channel:
        progress("读取 CP 色度单元…")
        unit = channel.read_unit(UNIT)
    rows = []
    for item in looks:
        rows.append({
            "name": item["name"],
            "menu": item.get("menu", ""),
            "bank": item["bank"],
            "state": classify(record(unit, item["bank"]), item),
            "rms": item.get("rms"),
        })
    return {"looks": rows, "sha256": hashlib.sha256(unit).hexdigest()}


def _write(looks: list[dict], key: str, progress) -> dict:
    with cp.session(progress) as channel:
        progress("读取当前的 CP 色度单元…")
        unit = channel.read_unit(UNIT)
        target = unit
        for item in looks:
            target = _splice(target, item, key)
        if target == unit:
            progress("四条记录已是目标状态，无需写入。")
        else:
            progress("写入色度记录…")
            channel.write_unit(UNIT, target)
        progress("回读校验…")
        after = channel.read_unit(UNIT)
    if after != target:
        diff = sum(1 for a, b in zip(after, target) if a != b)
        raise LooksError("回读不一致：" + str(diff) + " 个字节不同；请重启相机后再试，不要重复写入。")
    moved = changed_banks(unit, after, {item["bank"] for item in looks})
    if moved:
        progress("注意：这些与本页无关的记录也变了：bank " + str(moved))
    rows = []
    for item in looks:
        rows.append({
            "name": item["name"],
            "menu": item.get("menu", ""),
            "bank": item["bank"],
            "state": classify(record(after, item["bank"]), item),
            "rms": item.get("rms"),
        })
    return {
        "looks": rows,
        "moved": moved,
        "sha256": hashlib.sha256(after).hexdigest(),
        "wrote": target != unit,
    }


def apply(progress=lambda message: None) -> dict:
    """写入配方。"""
    return _write(profile(), "record_hex", progress)


def restore(progress=lambda message: None) -> dict:
    """把四条记录还回出厂值（其它记录一律不碰）。"""
    return _write(profile(), "factory_hex", progress)
