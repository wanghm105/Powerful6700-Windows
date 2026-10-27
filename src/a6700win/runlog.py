"""把运行日志落盘：出问题时要的是用户手上那一份，不是可能漏行的截图。

界面日志框（gui/widgets.py 的 LogBox）以前只活在内存里，关掉程序就没了，只能请
用户截图，而截图常常停在我们最想知道的那一行之后。现在同一条消息同时写进
数据目录/logs/run-<时间>-<tag>.log，诊断包也会带上最近几份。

约定：
* 只写不读、best-effort：目录不可写、磁盘满、被占用都不许把主流程带崩；
* 不重复报错：写失败就关掉句柄，之后静默；
* 只留最近 MAX_FILES 份，旧的自动删掉。
"""

from __future__ import annotations

import datetime as _datetime
from pathlib import Path

MAX_FILES = 10
PREFIX = "run-"
NEWLINE = chr(10)

_path = None
_handle = None


def _stamp():
    return _datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _version():
    from . import version

    return version.APP_VERSION


def _default_directory():
    from . import paths

    return paths.log_dir()


def _clean(tag):
    safe = "".join(ch for ch in str(tag) if ch.isalnum() or ch in "-_")[:24]
    return safe or "run"


def start(tag="run", directory=None):
    """开一份新日志，返回路径；开不出来就返回 None（不影响主流程）。"""
    global _path, _handle

    close()
    try:
        folder = Path(directory) if directory is not None else _default_directory()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ("%s%s-%s.log" % (PREFIX, _stamp(), _clean(tag)))
        handle = open(target, "w", encoding="utf-8", newline=NEWLINE)
    except Exception:  # noqa: BLE001 - 日志不许成为新的故障点
        return None
    _path, _handle = target, handle
    _trim(folder)
    write("Powerful6700Win %s · %s · %s" % (_version(), _stamp(), tag))
    write("日志文件：%s" % target)
    return target


def path():
    return _path


def write(message):
    """写一行；没有日志文件时什么都不做。"""
    handle = _handle
    if handle is None:
        return
    try:
        handle.write(str(message).rstrip() + NEWLINE)
        handle.flush()
    except Exception:  # noqa: BLE001
        close()


def close():
    global _path, _handle

    handle = _handle
    _handle = None
    _path = None
    if handle is None:
        return
    try:
        handle.close()
    except Exception:  # noqa: BLE001
        pass


def _trim(folder):
    """只留最近的 MAX_FILES 份。"""
    try:
        files = sorted(
            (item for item in folder.glob(PREFIX + "*.log") if item.is_file()),
            key=lambda item: (item.stat().st_mtime_ns, item.name),
            reverse=True,
        )
    except OSError:
        return
    for stale in files[MAX_FILES:]:
        try:
            stale.unlink()
        except OSError:
            continue
