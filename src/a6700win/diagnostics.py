"""把「内容或布局不匹配」翻译成能读懂、能贴进 issue 的文字。

上游 operations.py:288 在 plan["compatible"] 为 False 时只打一句话；而
device_profile.inspect_sectors() 其实已经把差异算成了 issues（kind / index /
device / offset / actual）。界面和命令行之前一个字段都没显示，2026-10-25 的
issue #1 就卡在这里：用户只看到「内容或布局不匹配」，拿不到任何线索。

这一层只做三件事：
1. issue_lines() 把 issues 变成中文短句；issue_hint() 给一句「先做什么」。
2. read_interrupted() 认出「读取中途掉线」，别把它说成内容不符。
3. report() / export_bundle() 产出一段可复制文字和一个 zip，取证不用找目录。
"""
from __future__ import annotations

import json
import platform
import zipfile
from datetime import datetime, timezone
from pathlib import Path

_KIND_LABEL = {
    "sector-guard-mismatch": "结构守卫不匹配",
    "unknown-field": "字段取值未知",
    "unknown-value": "取值未知",
    "feature-requirement": "功能前提不满足",
    "identity-mismatch": "机型／固件身份不符",
}

# 相机在读取中途掉出 MSC 时抛上来的几种样子。实测最常见的是拔线、相机自己
# 重启、以及「一次上电只给一个服务会话」之后的 [Errno 32] Pipe error。
_INTERRUPT_MARKS = (
    "pipe error",
    "errno 32",
    "timed out",
    "timeout",
    "no such device",
    "libusb_error",
    "broken pipe",
    "device disconnected",
    "input/output error",
)


def _offset(value) -> str:
    try:
        return "0x%08X" % int(value)
    except (TypeError, ValueError):
        return str(value)


def describe(issue: dict) -> str:
    """把一条 issue 变成一句中文；不认识的 kind 原样带出去。"""
    issue = dict(issue or {})
    kind = str(issue.get("kind") or "unknown")
    label = _KIND_LABEL.get(kind, kind)
    if kind == "sector-guard-mismatch":
        return "%s：#%s · %s 偏移 %s（role=%s）" % (
            label, issue.get("index", "?"), issue.get("device", "?"),
            _offset(issue.get("offset")), issue.get("role", "?"))
    if kind == "unknown-field":
        return "%s：%s · %s 偏移 %s · 实际 %s" % (
            label, issue.get("edit_id", "?"), issue.get("image", "?"),
            _offset(issue.get("offset")), issue.get("actual", "?"))
    if kind == "unknown-value":
        return "%s：%s 偏移 %s · 实际 %s" % (
            label, issue.get("image", "?"), _offset(issue.get("offset")),
            issue.get("value", "?"))
    if kind == "feature-requirement":
        detail = issue.get("detail") or issue.get("message") or ""
        return "%s：%s%s" % (label, issue.get("feature", "?"),
                             (" · " + str(detail)) if detail else "")
    if kind == "identity-mismatch":
        digest = str(issue.get("sha256") or "")[:16]
        return "%s：%s%s" % (label, issue.get("image", "?"),
                             (" · sha256 " + digest + "…") if digest else "")
    tail = ", ".join("%s=%s" % (key, value) for key, value in sorted(issue.items())
                     if key != "kind")
    return "%s（%s）" % (label, tail) if tail else label


def issue_lines(issues, limit: int = 12) -> list[str]:
    """逐条列出差异；超出 limit 时最后一行写清还剩多少。"""
    rows = [describe(issue) for issue in (issues or [])]
    total = len(rows)
    if limit and total > limit:
        rows = rows[:limit] + ["…还有 %d 处，完整列表在运行目录的 plan.json 里" % (total - limit)]
    return rows


def issue_hint(issues) -> str:
    """一句话说明最可能的原因与下一步；没有可说的就返回空串。"""
    kinds = {str((issue or {}).get("kind") or "") for issue in (issues or [])}
    parts = []
    if "sector-guard-mismatch" in kinds:
        parts.append(
            "结构守卫钉住的那几个扇区，机身里的内容和登记的基线不一样。常见的三种原因："
            "相机不是 A6700 固件 2.00；这台相机被别的工具改过；出厂批次的内容本来就不同。"
            "只读检查不写任何东西，可以放心把诊断信息贴到 issue，我们按偏移对一遍。")
    if kinds & {"unknown-field", "unknown-value"}:
        parts.append(
            "某个功能当前的取值不在已知取值表里。最常见的是 FTP 队列有残留（传过一张没传完），"
            "或者这个功能被别的工具调过。先在相机菜单里把对应功能关掉、断线重连再试一次。")
    if "feature-requirement" in kinds:
        parts.append("这次操作有前置条件没满足，按提示把前置功能开到目标状态再重试。")
    return " ".join(parts)


def read_interrupted(message: str) -> bool:
    """这句报错更像「读到一半相机没了」而不是「内容不符」。"""
    text = str(message or "").lower()
    if not text:
        return False
    return any(mark in text for mark in _INTERRUPT_MARKS)


def _safe(call):
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - 诊断本身不能抛
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def environment() -> dict:
    """版本、路径、补丁状态、USB 枚举；任何一项失败都只记错误。"""
    from . import paths, version

    data = {
        "version": version.APP_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    data["paths"] = _safe(paths.describe)
    from . import patches

    data["patches"] = _safe(patches.status)
    try:
        from .usb import setupapi

        data["devices"] = _safe(setupapi.summary)
    except Exception as exc:  # noqa: BLE001
        data["devices"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
    return data


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def report(result: dict, env: dict | None = None, limit: int = 20) -> str:
    """一段可以直接粘进 issue 的纯文本。"""
    result = dict(result or {})
    plan = dict(result.get("plan") or {})
    issues = list(plan.get("issues") or [])
    env = dict(env or {})
    lines = [
        "Powerful6700Win %s · %s" % (env.get("version") or _local_version(), _stamp()),
        "结论：%s（设备访问：%s／写过：%s）" % (
            result.get("status") or "无操作记录",
            "是" if result.get("device_access") else "否",
            "是" if result.get("write_attempted") else "否"),
    ]
    if plan:
        lines.append("只读检查：读取 %s 扇区／%s 字节 · 兼容性 %s" % (
            plan.get("read_sectors", "—"), plan.get("read_bytes", "—"),
            "通过" if plan.get("compatible") else "未通过"))
    for key, label in (("error", "错误"), ("cleanup_warning", "清理提示")):
        if result.get(key):
            lines.append("%s：%s" % (label, result[key]))
    if result.get("run_directory"):
        lines.append("运行目录：%s" % result["run_directory"])
    from . import runlog

    log_path = runlog.path()
    if log_path:
        lines.append("运行日志：%s" % log_path)
    lines.append("问题：%d 处" % len(issues))
    lines.extend("  - " + row for row in issue_lines(issues, limit=limit))
    hint = issue_hint(issues)
    if hint:
        lines.extend(["", hint])
    if env:
        lines.extend(["", "环境："])
        for key in ("platform", "python", "machine", "version"):
            if env.get(key):
                lines.append("  %s=%s" % (key, env[key]))
        devices = env.get("devices") or {}
        if isinstance(devices, dict):
            if devices.get("error"):
                lines.append("  设备枚举失败：%s" % devices["error"])
            pids = devices.get("pids")
            if pids:
                try:
                    lines.append("  相机 PID：%s" % ", ".join("%#06x" % int(pid) for pid in pids))
                except (TypeError, ValueError):
                    lines.append("  相机 PID：%s" % pids)
    return "\n".join(lines)


def _local_version() -> str:
    from . import version

    return version.APP_VERSION


def export_bundle(result: dict, target: Path, env: dict | None = None) -> Path:
    """把结论、环境、运行目录里的原始记录与最近日志打成 zip。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = dict(result or {})
    plan = dict(data.get("plan") or {})
    slim = {key: data.get(key) for key in
            ("action", "status", "error", "device_access", "write_attempted", "verified",
             "run_directory", "cleanup_warning", "profile_sha256") if key in data}
    slim["plan"] = {key: plan.get(key) for key in
                    ("action", "compatible", "read_sectors", "read_bytes", "changed_bytes",
                     "changed_sectors", "issues", "features") if key in plan}
    info = dict(env if env is not None else environment())
    text = report(data, info)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.txt", text)
        archive.writestr("result.json",
                         json.dumps(slim, ensure_ascii=False, indent=2, default=str))
        archive.writestr("environment.json",
                         json.dumps(info, ensure_ascii=False, indent=2, default=str))
        run_dir = data.get("run_directory")
        if run_dir:
            folder = Path(str(run_dir))
            for name in ("plan.json", "result.json", "native-result.json"):
                path = folder / name
                try:
                    if path.is_file() and path.stat().st_size <= 2_000_000:
                        archive.writestr("run/" + name, path.read_bytes())
                except OSError:
                    continue
        for path, payload in _recent_logs():
            archive.writestr("logs/" + path.name, payload)
    return target


def _recent_logs(limit: int = 3, max_bytes: int = 300_000) -> list[tuple[Path, bytes]]:
    """最近的日志原文；超过上限的只取最后一段——截尾，不整份丢掉。"""
    from . import paths

    try:
        folder = paths.log_dir()
        files = sorted((item for item in folder.glob("*.log") if item.is_file()),
                       key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return []
    kept = []
    for path in files[:limit]:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > max_bytes:
            data = "……（前面省略）……\n".encode("utf-8") + data[-max_bytes:]
        kept.append((path, data))
    return kept
