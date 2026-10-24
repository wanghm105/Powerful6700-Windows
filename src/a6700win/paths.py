r"""Windows 端路径解析：源码运行与 PyInstaller 冻结运行都要成立。

数据目录按优先级探测可写位置：POWERFUL6700_DATA → 程序目录\.data
→ %LOCALAPPDATA%\Powerful6700Win → 系统临时目录。

程序目录优先于 LOCALAPPDATA，是因为提权与否会改变 LOCALAPPDATA 的可写性：
以管理员运行时能建目录、普通权限运行时不能，同一个程序就会在两种权限下落到
两个不同的数据目录，驱动组件、备份与状态互相看不见。固定用程序目录下的 .data，
绿色副本换台机器照样带着自己的备份走。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from .version import APP_NAME

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent

_root: Path | None = None


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """可写项目根：源码运行时是 Powerful6700Win/，冻结运行时是 exe 所在目录。"""
    if frozen():
        return Path(sys.executable).resolve().parent
    return SRC_DIR.parent


def bundled_root() -> Path:
    """只读资源根：PyInstaller onedir 是 _internal/，源码运行时是项目根。"""
    if frozen():
        return Path(getattr(sys, "_MEIPASS", project_root()))
    return project_root()


def third_party_root() -> Path:
    return bundled_root() / "third_party"


def vendor_package_dir() -> Path:
    return third_party_root() / "a6700_unlock"


def ensure_vendor_on_path() -> str:
    """把 third_party 放进 sys.path，使 a6700_unlock 可导入。"""
    target = str(third_party_root())
    if target not in sys.path:
        sys.path.insert(0, target)
    return target


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / (".write-probe-%d" % os.getpid())
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def data_root() -> Path:
    global _root
    if _root is not None:
        return _root
    candidates: list[Path] = []
    override = os.environ.get("POWERFUL6700_DATA")
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(project_root() / ".data")
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        candidates.append(Path(base) / APP_NAME)
    candidates.append(Path(tempfile.gettempdir()) / APP_NAME)
    for candidate in candidates:
        if _writable(candidate):
            _root = candidate
            return candidate
    raise OSError("找不到可写的数据目录：%s" % ", ".join(str(item) for item in candidates))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    return _ensure(data_root() / "state")


def backup_dir() -> Path:
    return _ensure(data_root() / "backups")


def run_dir() -> Path:
    return _ensure(data_root() / "runs")


def log_dir() -> Path:
    return _ensure(data_root() / "logs")


def driver_dir() -> Path:
    return _ensure(data_root() / "driver")


def documents_dir() -> Path:
    candidate = Path.home() / "Documents"
    return _ensure(candidate) if candidate.is_dir() else data_root()


def describe() -> dict:
    """用于自检与诊断输出的可序列化路径快照（不创建目录）。"""
    root = data_root()
    return dict(
        frozen=frozen(),
        project_root=str(project_root()),
        bundled_root=str(bundled_root()),
        third_party=str(third_party_root()),
        data_root=str(root),
        state_dir=str(root / "state"),
        backup_dir=str(root / "backups"),
        driver_dir=str(root / "driver"),
    )
