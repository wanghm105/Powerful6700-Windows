# -*- coding: utf-8 -*-
"""菜单文字：把相机语言资源里的外观短名改成本项目的名字，并且能还原。

为什么单独一个模块：「自定义外观」改的是 CP 单元里的颜色（RAM，关机后才落盘），
而菜单上显示的文字在 `/usr/share/app/string_simplifiedchinese_f.uxc` 里（ext2 文件，
一写就持久）。两者风险等级不同，所以分开写、分开讲、分开还原。

写入链路：认证进服务模式 → 读整份资源 → 保存基线 → UXC 重排（grow）→
分块写回 → 需要时截断 → 整份回读比对。

还原链路（三档，界面如实报告用的是哪一档）：
1. 出厂基线（整份文件逐字节写回）：需要事先保存过出厂资源，或由用户导入。
   写完回读的 SHA-256 必须等于基线的 SHA-256，才算「无损」。
2. 短名回写：没有基线时，把记录的文字改回出厂短名（PT / NT / VV / VV2）。
   菜单显示恢复正常，但文件字节与出厂不同（记录顺序与补齐受历史改名影响）。
3. 什么都不做：没有差异就只报告，不写。
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
from contextlib import contextmanager
from pathlib import Path

from . import cp, flash, paths, uxc

BLOB_PATH = "/usr/share/app/string_simplifiedchinese_f.uxc"
STORE = "looknames"
INDEX_NAME = "index.json"

# 每个外观在语言资源里有两条记录：一条菜单短名、一条列表/详情名。历史上的改名都是
# 两条一起改，否则菜单与详情一个改了一个没改，看起来像没生效。
SLOT_RIDS: dict[str, tuple[int, ...]] = {
    "ST": (0x021C658E,),
    "PT": (0x021C6654, 0x021C6F8B),
    "NT": (0x021C6434, 0x021C7002),
    "VV": (0x021C687B, 0x021C6F80),
    "VV2": (0x021C689A, 0x021C6F4D),
    "FL": (0x021C6CC9,),
    "IN": (0x021C6857,),
    "SH": (0x021C6961,),
    "BW": (0x021C65F8,),
    "SE": (0x021C658A,),
}
ALL_RIDS = tuple(rid for rids in SLOT_RIDS.values() for rid in rids)

# 已实测的出厂资源（A6700，固件 2.00）：SHA-256 → 字节数。
FACTORY_SHA256 = {
    "fe263360c15b5530508bf7b098c96ec39cd4c38536b23653d15e6ea977b80e42": 145612,
}

MIN_BYTES = 4096
MAX_BYTES = flash.DATA_MAX
CHUNK = flash.BLOCK

KIND_TEXT = {
    "factory": "出厂资源（哈希匹配）",
    "factory-labels": "出厂短名",
    "renamed": "本项目名字",
    "other": "其它改动",
}


class LookNamesError(RuntimeError):
    """资源读写失败；不包含任何「已重试」语义。"""


# --------------------------------------------------------------------- 命名方案
#: 两套可选的菜单文字：官方原名（英文，和胶片模拟自己的叫法一致）与中文简称。
PRESETS: dict[str, dict] = {
    "official": {"label": "官方原名", "note": "Classic Chrome / Classic Neg. / Positive Film / Negative Film"},
    "zh": {"label": "中文简称", "note": "富士CC / 富士NC / 理光正片 / 理光负片"},
}
DEFAULT_PRESET = "official"
PRESET_FILE = "settings.json"


def preset_labels() -> list[dict]:
    return [{"key": key, **value} for key, value in PRESETS.items()]


def _preset_path() -> Path:
    return store_dir() / PRESET_FILE


def load_preset() -> str:
    try:
        data = json.loads(_preset_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_PRESET
    key = str(data.get("preset") or "")
    return key if key in PRESETS else DEFAULT_PRESET


def save_preset(key: str) -> str:
    if key not in PRESETS:
        raise LookNamesError(f"未知的命名方案 {key!r}")
    try:
        _preset_path().write_text(json.dumps({"preset": key, "saved_at": _stamp()},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # 记不住选择不影响这次写入
    return key


# --------------------------------------------------------------------- 目标
def targets(preset: str | None = None) -> list[dict]:
    """外观槽位 → 要写入的菜单文字（按命名方案），来自 docs/looks-profile.json。"""
    from . import looks

    choice = preset or load_preset()
    if choice not in PRESETS:
        raise LookNamesError(f"未知的命名方案 {choice!r}")
    rows = []
    for item in looks.profile():
        slot = str(item.get("menu_slot") or "").upper()
        names = item.get("menu_names") or {}
        text = str(names.get(choice) or item.get("menu_text") or "").strip()
        if not slot or not text:
            continue
        if slot not in SLOT_RIDS:
            raise LookNamesError(f"未知的菜单槽位 {slot}（配方里的 menu_slot 写错了？）")
        variants = {key: str((names.get(key) or "")).strip() for key in PRESETS if names.get(key)}
        rows.append({"look": str(item.get("name") or slot),
                     "label": str(item.get("slot") or item.get("menu") or slot),
                     "slot": slot, "text": text, "variants": variants})
    if not rows:
        raise LookNamesError("looks-profile.json 里没有 menu_names / menu_text。")
    return rows


def _edits(rows: list[dict]) -> dict[int, str]:
    edits: dict[int, str] = {}
    for row in rows:
        for rid in SLOT_RIDS[row["slot"]]:
            edits[rid] = row["text"]
    return edits


# --------------------------------------------------------------------- 分类
def _texts(raw: bytes) -> dict[int, str]:
    try:
        return uxc.texts(raw, ALL_RIDS)
    except uxc.UxcError as exc:
        raise LookNamesError(f"语言资源格式不符：{exc}") from exc


def classify(raw: bytes) -> str:
    """整份资源的身份：出厂 / 出厂短名 / 本项目名字 / 其它改动。"""
    if hashlib.sha256(raw).hexdigest() in FACTORY_SHA256:
        return "factory"
    texts = _texts(raw)
    look_slots = {row["slot"] for row in targets()}
    if all(texts.get(rid) == slot for slot in look_slots for rid in SLOT_RIDS[slot]):
        return "factory-labels"
    for preset in PRESETS:
        try:
            wanted = _edits(targets(preset))
        except LookNamesError:
            continue
        if all(texts.get(rid) == text for rid, text in wanted.items()):
            return "renamed"
    return "other"


# --------------------------------------------------------------------- 基线
def store_dir() -> Path:
    folder = paths.data_root() / STORE
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _index_path() -> Path:
    return store_dir() / INDEX_NAME


def _read_index() -> list[dict]:
    path = _index_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _write_index(items: list[dict]) -> None:
    payload = {"schema": "a6700win/looknames/1", "items": items}
    _index_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def capture(raw: bytes, source: str) -> dict:
    """把整份资源存一份基线；同一份内容只存一次。"""
    digest = hashlib.sha256(raw).hexdigest()
    path = store_dir() / f"baseline-{digest[:16]}.bin"
    if not path.is_file():
        path.write_bytes(raw)
    item = {"sha256": digest, "bytes": len(raw), "kind": classify(raw),
            "source": source, "saved_at": _stamp(), "file": path.name}
    items = [entry for entry in _read_index() if str(entry.get("sha256")) != digest]
    items.append(item)
    items.sort(key=lambda entry: str(entry.get("saved_at") or ""), reverse=True)
    _write_index(items)
    return item


def baseline_items() -> list[dict]:
    """索引里存在、文件也还在的基线条目（新到旧）。"""
    alive = []
    for item in _read_index():
        name = str(item.get("file") or "")
        if name and (store_dir() / name).is_file():
            alive.append(item)
    return alive


def best_baseline() -> dict | None:
    """可用于还原的出厂基线：优先哈希匹配，其次「出厂短名」。"""
    items = baseline_items()
    for item in items:
        if str(item.get("sha256")) in FACTORY_SHA256:
            return item
    for item in items:
        if item.get("kind") in ("factory", "factory-labels"):
            return item
    return None


def baseline_summary() -> dict:
    best = best_baseline()
    items = baseline_items()
    return {
        "ready": best is not None,
        "best": best,
        "count": len(items),
        "items": items[:6],
        "dir": str(store_dir()),
    }


def import_file(path: str | Path) -> dict:
    """把用户手上一份 UXC 资源导入为基线（校验格式与槽位完整）。"""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise LookNamesError(f"读不了这个文件：{exc}") from exc
    if not MIN_BYTES <= len(raw) <= MAX_BYTES:
        raise LookNamesError(f"文件 {len(raw):,} 字节，不像这份语言资源（预期十万字节级）。")
    texts = _texts(raw)
    missing = [slot for slot, rids in SLOT_RIDS.items() if not any(rid in texts for rid in rids)]
    if missing:
        raise LookNamesError("这份资源里缺少外观记录：" + "、".join(missing))
    return capture(raw, source=f"导入 {source.name}")


def auto_import() -> list[dict]:
    """把项目里已有的固件备份（开发环境才有）收进基线库。"""
    imported = []
    known = {str(item.get("sha256")) for item in baseline_items()}
    roots = [paths.bundled_root() / "firmware" / "uxc",
             paths.project_root() / "firmware" / "uxc",
             paths.project_root().parent / "firmware" / "uxc"]
    seen: set[Path] = set()
    for folder in roots:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.uxc*.bin")):
            if path in seen:
                continue
            seen.add(path)
            try:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if digest in known or not MIN_BYTES <= len(raw) <= MAX_BYTES:
                    continue
                _texts(raw)
            except (OSError, LookNamesError):
                continue
            imported.append(capture(raw, source=path.name))
            known.add(digest)
    return imported


# --------------------------------------------------------------------- 读写
class _Backend:
    """把 Senser 通道包成 flash 模块要的 _command/_file 形状（与 tools/look_name.py 同款）。"""

    def __init__(self, channel: cp.CpChannel):
        self.cp = channel
        self.channel = channel.channel

    def _command(self, command: int, payload: bytes) -> bytes:
        code, body = self.channel.send(0x40, struct.pack("<HH", 0x1001, command) + payload)
        if code:
            raise LookNamesError(f"USB 服务命令失败：0x{command:04x}, code={code}")
        return body

    def _file(self, command: int, ident: int, data: bytes) -> None:
        body = self._command(command, bytes([0, ident, 0]) + data)
        if len(body) != 4 or body != b"\0" * 4:
            raise LookNamesError("文件写入或载荷执行失败，状态：" + body[:16].hex())


@contextmanager
def _scope(progress=lambda message: None, channel=None):
    """给了 channel 就复用调用方的会话，否则自己认证一次并保证退出服务模式。"""
    if channel is not None:
        yield channel, _Backend(channel)
        return
    with cp.session(progress) as opened:
        yield opened, _Backend(opened)


def _read_blob(backend) -> bytes:
    size = flash.stat(backend, BLOB_PATH)
    if not MIN_BYTES <= size <= MAX_BYTES:
        raise LookNamesError(f"相机上的资源是 {size:,} 字节，不在预期范围，停止操作。")
    if size % 4:
        raise LookNamesError(f"资源长度 {size} 不是 4 的倍数，格式不对，停止操作。")
    data = flash.read_range(backend, BLOB_PATH, 0, size)
    if len(data) != size:
        raise LookNamesError(f"只读到 {len(data):,}/{size:,} 字节，停止操作。")
    return data


def _write_blob(backend, blob: bytes, progress, live: bytes | None = None) -> bool:
    """把整份资源写回相机：调长度 → 分块写 → 整份回读比对。

    `live` 是调用方刚读到的当前内容（有就复用，省掉整份读）。相机在一次插入周期里
    能撑的传输次数有限，多读 5 块就可能把会话撑掉。长度先对齐再做覆盖写：变短是
    截断，变长是 ftruncate 扩零 —— 写入器不能越界追加，否则最后一块报范围超长。
    """
    if live is not None and live == blob:
        progress("相机上的资源与目标一致，无需写入。")
        return False
    current = len(live) if live is not None else flash.stat(backend, BLOB_PATH)
    # 写入器只在文件现有长度内覆盖，不能越界追加。所以先把长度调到目标值：
    # 变短是截断，变长是 ftruncate 扩零 —— 否则最后一块会报「范围超出文件长度」。
    if len(blob) != current:
        progress(f"把文件长度从 {current:,} 调整到 {len(blob):,} 字节…")
        flash.truncate(backend, BLOB_PATH, len(blob))
    total = (len(blob) + CHUNK - 1) // CHUNK
    for index, offset in enumerate(range(0, len(blob), CHUNK), start=1):
        chunk = blob[offset:offset + CHUNK]
        progress(f"写入 0x{offset:06x}（{len(chunk):,} 字节，{index}/{total}）…")
        flash.write_block(backend, BLOB_PATH, offset, chunk)
    progress("整份回读比对…")
    got = _read_blob(backend)
    if got != blob:
        raise LookNamesError("回读与目标不一致，不要再写第二次；请用「还原菜单文字」或基线恢复。")
    return True


# --------------------------------------------------------------------- 报告
def _rows(raw: bytes, preset: str | None = None) -> list[dict]:
    texts = _texts(raw)
    rows = []
    for row in targets(preset):
        rids = SLOT_RIDS[row["slot"]]
        present = [texts[rid] for rid in rids if rid in texts]
        if not present:
            state = "missing"
            current = "（资源里没有这条记录）"
        elif all(text == row["text"] for text in present):
            state = "installed"
            current = row["text"]
        elif all(text == row["slot"] for text in present):
            state = "factory"
            current = row["slot"]
        elif len(set(present)) == 1:
            state = "other"
            current = present[0]
        else:
            state = "mixed"
            current = " / ".join(present)
        rows.append({"look": row["look"], "slot": row["slot"], "target": row["text"],
                     "current": current, "rids": list(rids), "state": state,
                     "variants": row.get("variants") or {}})
    return rows


def _others(raw: bytes, rows: list[dict]) -> list[dict]:
    texts = _texts(raw)
    used = {row["slot"] for row in rows}
    out = []
    for slot, rids in SLOT_RIDS.items():
        if slot in used:
            continue
        for rid in rids:
            if rid in texts:
                out.append({"slot": slot, "text": texts[rid]})
                break
    return out


def _report(raw: bytes, preset: str | None = None) -> dict:
    choice = preset or load_preset()
    rows = _rows(raw, choice)
    return {
        "path": BLOB_PATH,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "kind": classify(raw),
        "preset": choice,
        "presets": preset_labels(),
        "looks": rows,
        "others": _others(raw, rows),
        "baseline": baseline_summary(),
    }


def read(progress=lambda message: None, channel=None, preset=None) -> dict:
    """只读：读出资源、四条外观当前显示的名字、以及本地基线情况。"""
    with _scope(progress, channel) as (_opened, backend):
        progress("读取相机语言资源…")
        raw = _read_blob(backend)
    if not baseline_items():
        try:
            progress("本地还没有基线，看看项目里有没有早先的备份…")
            if auto_import():
                progress("已把项目里的备份收进基线库。")
        except Exception:  # noqa: BLE001 - 自动收纳失败不影响读取结果
            pass
    return _report(raw, preset)


def apply(progress=lambda message: None, channel=None, preset=None) -> dict:
    """按选定的命名方案写入四条外观的菜单文字（写 /usr 文件，持久）。"""
    choice = save_preset(preset or load_preset())
    with _scope(progress, channel) as (_opened, backend):
        progress(f"读取相机语言资源…（命名方案：{PRESETS[choice]['label']}）")
        raw = _read_blob(backend)
        captured = None
        digest = hashlib.sha256(raw).hexdigest()
        if not any(str(item.get("sha256")) == digest for item in baseline_items()):
            progress("这份资源还没有基线，先存一份（还原就靠它）…")
            captured = capture(raw, source="写入前自动保存")
        new, changes = uxc.rename_all(raw, _edits(targets(choice)))
        if not changes:
            progress("四条记录已经是目标文字，无需写入。")
            wrote = False
        else:
            for change in changes:
                progress(f"改名 0x{change['rid']:08x}：{change['old']!r} → {change['new']!r}")
            wrote = _write_blob(backend, new, progress, live=raw)
        after = _read_blob(backend)
    report = _report(after, choice)
    report.update({"wrote": wrote, "changes": changes, "captured": captured})
    return report


def restore(progress=lambda message: None, channel=None, preset=None) -> dict:
    """还原菜单文字：有出厂基线就逐字节写回，没有就把文字改回出厂短名。"""
    with _scope(progress, channel) as (_opened, backend):
        best = best_baseline()
        changes: list[dict] = []
        if best is not None:
            # 走整份基线时只在长度相同的情况下读一遍当前内容（判断是否已经一致）；
            # 长度不同就直接写 —— 相机一次插入周期能撑的传输次数有限，能少一趟就少一趟。
            size = flash.stat(backend, BLOB_PATH)
            target = (store_dir() / str(best["file"])).read_bytes()
            if hashlib.sha256(target).hexdigest() != str(best["sha256"]):
                raise LookNamesError("基线文件被改动过（哈希不符），拒绝用它还原。")
            try:
                _texts(target)
            except LookNamesError as exc:
                raise LookNamesError(f"基线文件无法解析：{exc}") from exc
            mode = "baseline"
            progress(f"当前 {size:,} 字节，用出厂基线还原（{len(target):,} 字节，"
                     f"{KIND_TEXT.get(str(best.get('kind')), '基线')}）…")
            live = _read_blob(backend) if size == len(target) else None
            wrote = _write_blob(backend, target, progress, live=live)
        else:
            raw = _read_blob(backend)
            mode = "labels"
            progress("没有出厂基线：只把文字改回出厂短名…")
            texts = _texts(raw)
            wanted = {rid: slot for slot, rids in SLOT_RIDS.items()
                      for rid in rids if rid in texts and texts[rid] != slot}
            new, changes = uxc.rename_all(raw, wanted)
            if hashlib.sha256(new).hexdigest() in FACTORY_SHA256:
                # 短名回写恰好把文件恢复成了出厂资源：升级成整份基线，下次就走逐字节那一档。
                mode = "labels-factory"
                progress("短名回写后的哈希与出厂资源一致，已把它登记为出厂基线。")
                capture(new, source="短名回写重建（哈希与出厂一致）")
            if not changes:
                progress("文字已是出厂短名，无需写入。")
                wrote = False
            else:
                wrote = _write_blob(backend, new, progress, live=raw)
        after = _read_blob(backend)
    report = _report(after, preset)
    report.update({"wrote": wrote, "mode": mode, "changes": changes})
    return report
