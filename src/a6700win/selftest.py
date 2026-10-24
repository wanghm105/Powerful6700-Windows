"""离线自检：不接触相机也能确认这台机器上的关键环节是否就绪。

打包后的 CI 用它做冒烟测试（--offline-self-test），用户也能在“关于”页
手动跑一次，把结果贴给维护者。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _check(results: list, identifier: str, name: str, function) -> bool:
    try:
        detail, ok = function()
    except Exception as exc:  # noqa: BLE001 - 自检要收集失败而不是抛出
        results.append(dict(id=identifier, name=name, ok=False, detail=str(exc)))
        return False
    results.append(dict(id=identifier, name=name, ok=ok, detail=detail))
    return ok


def run(output: str | Path | None = None) -> dict:
    from . import patches, paths, version

    results: list[dict] = []

    _check(results, "python", "Python 运行时", lambda: (sys.version.split()[0], sys.version_info >= (3, 10)))
    _check(results, "platform", "操作系统", lambda: (sys.platform, sys.platform.startswith("win")))

    def vendor():
        paths.ensure_vendor_on_path()
        import a6700_unlock

        return ("a6700_unlock %s" % getattr(a6700_unlock, "__version__", "unknown"), True)

    _check(results, "vendor", "内置设备运行时", vendor)

    def files():
        root = paths.vendor_package_dir()
        required = [
            root / "catalog.py",
            root / "operations.py",
            root / "desktop" / "controller.py",
            root / "data" / "a6700-2.00.json",
            root / "data" / "native" / "reader.elf",
            root / "data" / "native" / "writer.elf",
        ]
        missing = [str(item.relative_to(root)) for item in required if not item.is_file()]
        return (missing[0] if missing else "资源完整", not missing)

    _check(results, "files", "内置资源文件", files)

    def data_dir():
        root = paths.data_root()
        probe = root / ".selftest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return (str(root), True)

    _check(results, "data-dir", "数据目录可写", data_dir)

    _check(results, "libusb", "libusb 运行库", lambda: _libusb())

    def setupapi():
        from .usb import setupapi

        payload = setupapi.summary()
        return ("Sony PID: %s" % (payload["pids"] or "未连接"), payload["available"])

    _check(results, "setupapi", "Windows 设备枚举", setupapi)

    def wdi():
        from .usb import driver

        return (str(driver.wdi_executable()), driver.wdi_available())

    _check(results, "wdi", "驱动安装组件（随包附带）", wdi)

    def controller():
        from .app import build_controller

        instance = build_controller("simulation")
        snapshot = instance.snapshot()
        required = {"revision", "phase", "features", "notice", "steps", "environment"}
        missing = sorted(required - set(snapshot))
        return ("缺失字段: %s" % missing if missing else "ok", not missing)

    _check(results, "controller", "控制器快照", controller)

    payload = dict(
        app=version.APP_NAME,
        version=version.APP_VERSION,
        platform=sys.platform,
        ok=all(item["ok"] for item in results),
        checks=results,
        paths=paths.describe(),
    )
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _libusb():
    from .usb import windows_auth

    path = windows_auth.libusb_library_path()
    import ctypes

    ctypes.CDLL(path)
    return (path, True)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 控制台不支持重配置时保持原样
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    output = argv[0] if argv else None
    payload = run(output)
    for item in payload["checks"]:
        mark = "OK  " if item["ok"] else ("SKIP" if item.get("optional") else "FAIL")
        print("%s %-12s %s" % (mark, item["id"], item["detail"]))
    print("结果: %s" % ("通过" if payload["ok"] else "存在失败项"))
    return 0 if payload["ok"] else 1
