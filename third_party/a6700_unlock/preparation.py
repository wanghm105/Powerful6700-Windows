"""Reusable preparation service for CLI and a future desktop UI.

This module never captures USB, authenticates, or constructs a device backend.
Human confirmations describe preparation only; compatibility needs a fresh
read-only device preflight in operations.execute.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .doctor import diagnose


@dataclass(frozen=True)
class MenuGuide:
    """Owned schematic content; no camera screenshot or firmware UI assets."""
    id: str
    title: str
    path: tuple[str, ...]
    target: str
    choices: tuple[str, ...]
    source_url: str
    source_note: str


@dataclass(frozen=True)
class PreparationStep:
    id: str
    title: str
    instruction: str
    confirmation_label: str
    skip_label: str = ""
    menu_guides: tuple[MenuGuide, ...] = ()


STEPS = (
    PreparationStep("ftp_stopped", "FTP：仅已有菜单时处理",
                    "首次解锁通常没有 FTP 菜单，这是正常情况，可直接继续。仅当机身已有此菜单且 FTP 开启时，停止传输并将 FTP 功能设为关；此前运行过 FTP 时，关闭后重启相机以释放介质占用。",
                    "已有 FTP 菜单，已关闭并完成准备", "没有 FTP 菜单，直接继续",
                    (MenuGuide("ftp-off", "FTP功能",
                               ("MENU", "网络", "传输/远程", "FTP传输功能", "FTP功能"),
                               "关", ("关", "开"), "",
                               "仅已解锁机身；依据项目菜单与实机记录，不属于 A6700 原厂公开菜单。位置以机身为准。"),)),
    PreparationStep("camera_msc", "设置 USB 海量存储模式",
                    "先断开 USB，在相机菜单中选择海量存储器(MSC)。若保留连接时选择，则接线后选择影像传输(MSC)。不要选择 MTP、电脑遥控或 USB 流式传输。",
                    "已设置 MSC 模式",
                    menu_guides=(MenuGuide("usb-msc", "USB连接模式",
                                           ("MENU", "设置", "USB", "USB连接模式"),
                                           "海量存储器(MSC)",
                                           ("连接时选择", "USB流式传输", "海量存储器(MSC)", "MTP", "电脑遥控"),
                                           "https://helpguide.sony.net/ilc/2320/v1/zh-cn/contents/0601_usb_connection.html",
                                           "菜单名称及选项依据 Sony A6700 简体中文帮助指南。"),)),
    PreparationStep("power_awake", "关闭自动关机，确认电量",
                    "在接线前将自动关机开始时间设为关，并确认电量充足或供电可靠。不要把自动关机温度当作这个项目；操作完成后可恢复原来的省电设置。",
                    "已关闭自动关机，电量或供电可靠",
                    menu_guides=(MenuGuide("power-save-off", "自动关机开始时间",
                                           ("MENU", "设置", "电源设置选项", "自动关机开始时间"),
                                           "关", ("关", "30分钟", "5分钟", "2分钟", "1分钟", "10秒"),
                                           "https://helpguide.sony.net/ilc/2320/v1/zh-cn/contents/0601B_power_save_start_time.html",
                                           "Sony 帮助指南说明 USB 供电或连接电脑时会停用自动关机；仍提前设为关，以覆盖连接切换阶段。"),)),
    PreparationStep("usb_connection", "最后连接 USB 数据线",
                    "完成上面的菜单设置后，使用可传数据的 USB 线连接相机与电脑，只连接一台目标相机。若弹出连接方式选择，选择影像传输(MSC)。日常功能管理不接 Pico 或测试板；操作期间保持相机开机。",
                    "已连接唯一相机，保持开机与唤醒"),
)
STEP_IDS = tuple(step.id for step in STEPS)


def assess(profile, confirmed=(), environment=None):
    """Return JSON-friendly facts and pending human steps, with no device I/O."""
    confirmed = frozenset(confirmed)
    unknown = confirmed.difference(STEP_IDS)
    if unknown:
        raise ValueError("Unknown preparation step: " + ", ".join(sorted(unknown)))
    environment = diagnose(profile) if environment is None else environment
    steps = [dict(asdict(step), confirmed=step.id in confirmed, verification="human") for step in STEPS]
    ready = bool(environment["ready"]) and all(step["confirmed"] for step in steps)
    return dict(status="ready-for-preflight" if ready else
                "environment-blocked" if not environment["ready"] else "preparation-required",
                ready=ready, environment=environment, steps=steps,
                next_step="device-read-only-preflight" if ready else "complete-preparation",
                compatibility_verified=False, device_access=False, write_attempted=False)


def show(report, emit=print):
    """Render the same facts used by a desktop UI, without mixing in I/O."""
    emit("环境检查：")
    for check in report["environment"]["checks"]:
        emit(f"  {'✓' if check['ok'] else '✗'} {check['name']}：{check['detail']}")
        if not check["ok"] and check.get("remediation"):
            emit("    处理方法：" + check["remediation"])
    emit("相机准备（需要人工确认，当前不能自动读取这些设置）：")
    for step in report["steps"]:
        emit(f"  {'✓' if step['confirmed'] else '○'} {step['title']}：{step['instruction']}")
        for menu in step['menu_guides']:
            emit("    菜单路径：" + " → ".join(menu['path']) + " → " + menu['target'])
        if step['skip_label']:
            emit("    无此菜单时：" + step['skip_label'])


def guide(profile, confirmed=(), interactive=False, emit=print, input_fn=None):
    """Fresh checks per operation. No cached confirmations across connections."""
    report = assess(profile, confirmed)
    show(report, emit)
    if not report["environment"]["ready"] or not interactive or report["ready"]:
        return report
    input_fn = input if input_fn is None else input_fn
    completed = {step["id"] for step in report["steps"] if step["confirmed"]}
    for step in report["steps"]:
        if step["confirmed"]:
            continue
        emit(f"完成后输入 y：{step['title']}（其他输入返回，尚未连接维护通道）")
        try:
            answer = input_fn().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes", "是", "已完成"):
            result = assess(profile, completed, report["environment"])
            result["cancelled"] = True
            return result
        completed.add(step["id"])
    return assess(profile, completed, report["environment"])
