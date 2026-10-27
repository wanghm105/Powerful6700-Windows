"""一次写入：外观颜色 + 菜单文字，按同一个选择一起写下去。

用户要的是「选中文富士就写中文名 + 富士滤镜」——名字和颜色必须对得上，不能只写一半。
但这两样东西在相机里属于完全不同的子系统：

* 颜色：CP 色度单元 0x02A40001 的 4 条记录，写在相机运行内存里，关机时才落盘；
* 菜单文字：/usr 语言资源文件（约 145 KB），写下去就持久。

而且实测过：**同一个 USB 会话里既写 CP 单元又写 145 KB 文件，必掉线**
（第 13 次传输左右端点挂掉，文件停在半截）。所以这里不发明新协议，只做编排：
两段独立会话、顺序执行，中间的空档由 `cp.session` 的冷却兜着（默认 50 秒）。

失败处理也一样刻意：前一段失败就整段停下、什么都不写；后一段失败则保留前一段的结果
并在返回值里说清楚，让用户能单独回滚颜色。
"""

from __future__ import annotations

import time

from . import looknames, looks


class BundleError(RuntimeError):
    """一次写入/还原失败。"""


COOLDOWN_HINT = "两次连接之间要等相机复位（约 1 分钟），这是实测出来的硬要求，不是慢。"


def _label(preset: str | None) -> str:
    preset = preset or looknames.load_preset()
    return str((looknames.PRESETS.get(preset) or {}).get("label") or preset)


def _report(preset: str | None) -> dict:
    choice = preset or looknames.load_preset()
    return {
        "preset": choice,
        "label": _label(choice),
        "steps": [],
        "colors": None,
        "names": None,
        "wrote": False,
        "error": None,
        "seconds": 0.0,
    }


def _colors(progress, report: dict, restoring: bool) -> bool:
    """第一段：写 CP 色度单元（相机运行内存）。返回是否真的写了。"""
    progress("第 1 段：改颜色（写进相机的运行内存）…")
    try:
        result = looks.restore(progress) if restoring else looks.apply(progress)
    except Exception as exc:  # noqa: BLE001 - 交给调用方决定怎么讲
        raise BundleError(f"改颜色这一段失败，菜单名字一个字都没动：{exc}") from exc
    report["colors"] = result
    report["steps"].append("colors")
    wrote = bool((result or {}).get("wrote"))
    report["wrote"] = report["wrote"] or wrote
    return wrote


def _names(progress, report: dict, restoring: bool, colors_wrote: bool) -> bool:
    """第二段：写 /usr 语言资源（持久）。失败时如实说明颜色已经变了。"""
    progress("第 2 段：改菜单名字（会重新连一次相机）…")
    try:
        result = looknames.restore(progress, preset=report["preset"]) if restoring \
            else looknames.apply(progress, preset=report["preset"])
    except Exception as exc:  # noqa: BLE001
        tail = "颜色已经写进相机了，可以单独点「还原颜色」改回去" if colors_wrote \
            else "颜色这一段没有写入"
        raise BundleError(f"改菜单名字这一段失败：{exc}。{tail}。") from exc
    report["names"] = result
    report["steps"].append("names")
    wrote = bool((result or {}).get("wrote"))
    report["wrote"] = report["wrote"] or wrote
    return wrote


def _run(progress, preset: str | None, restoring: bool) -> dict:
    report = _report(preset)
    started = time.monotonic()
    action = "还原" if restoring else "写入"
    progress(f"一次{action}：颜色 + 名字（名字用「{report['label']}」）。"
             f"分两次连接，中间等相机自己复位，全程大约 2 分钟。{COOLDOWN_HINT}")
    try:
        colors_wrote = _colors(progress, report, restoring)
        try:
            _names(progress, report, restoring, colors_wrote)
        except BundleError as exc:
            report["error"] = str(exc)
            return report
    finally:
        report["seconds"] = round(time.monotonic() - started, 1)
    return report


def apply(progress=lambda message: None, preset: str | None = None) -> dict:
    """把四条外观颜色与对应菜单文字一起写下去（两段会话）。"""
    return _run(progress, preset, restoring=False)


def restore(progress=lambda message: None, preset: str | None = None) -> dict:
    """把颜色与菜单文字一起还原（两段会话）。"""
    return _run(progress, preset, restoring=True)


def summary(report: dict | None) -> list[str]:
    """把两段的实际结果压成几句话，界面和命令行都能直接用。"""
    report = report or {}
    lines: list[str] = []
    colors = report.get("colors") or {}
    names = report.get("names") or {}
    label = report.get("label") or ""
    if colors:
        rows = colors.get("looks") or []
        states = "，".join(f"{row.get('name')}={_state(row.get('state'))}" for row in rows)
        lines.append(f"颜色：{states}")
    if names:
        preset = (looknames.PRESETS.get(str(names.get("preset") or "")) or {}).get("label")
        changes = names.get("changes") or []
        text = f"菜单名字：改了 {len(changes)} 条" if changes else "菜单名字：不用改"
        if preset:
            text += f"（{preset}）"
        lines.append(text)
        mode = names.get("mode")
        if mode == "baseline":
            lines.append("菜单名字用出厂底稿整份写回，读回来一模一样。")
        elif mode == "labels-factory":
            lines.append("菜单名字改回短名之后和出厂文件一致，属于逐字节还原。")
        elif mode == "labels":
            lines.append("本地没有出厂底稿，菜单名字只改回了出厂短名。")
    if label and report.get("steps"):
        lines.append(f"两段都按「{label}」这套叫法对齐。")
    if report.get("seconds"):
        lines.append(f"总用时 {report['seconds']:.0f} 秒。")
    return lines


_STATE = {"installed": "已写入", "factory": "出厂", "other": "其它改动"}


def _state(value) -> str:
    return _STATE.get(str(value), "未知")
