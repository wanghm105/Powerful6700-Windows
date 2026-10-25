"""Powerful6700 · Windows 命令行入口。默认启动图形界面。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _attach_console() -> None:
    """窗口化 exe 默认没有 stdout/stderr；从终端调用时借用父进程控制台。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if not kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
            kernel32.AllocConsole()
        for name in ("stdout", "stderr"):
            handle = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            setattr(sys, name, handle)
    except Exception:  # noqa: BLE001 - 真的没有控制台时静默降级
        import io

        sys.stdout = sys.stdout or io.StringIO()
        sys.stderr = sys.stderr or io.StringIO()


def _utf8_streams() -> None:
    _attach_console()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 无控制台时忽略
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="Powerful6700Win",
        description="Sony A6700 Windows 工具（上游 a6700-unlock 的 Windows 端口）。",
    )
    parser.add_argument("--demo", action="store_true", help="以演示模式启动（不需要连接相机）")
    parser.add_argument("--diagnose", action="store_true", help="打印环境诊断信息后退出")
    parser.add_argument("--offline-self-test", action="store_true", help="运行离线自检后退出")
    parser.add_argument("--json", metavar="PATH", help="把自检结果写入指定 JSON 文件")
    parser.add_argument("--render-pages", metavar="DIR", help=argparse.SUPPRESS)
    parser.add_argument("--elevated-worker", metavar="REQUEST", help=argparse.SUPPRESS)
    parser.add_argument("--dump", metavar="PATH", help=argparse.SUPPRESS)
    parser.add_argument("--out", metavar="FILE", help=argparse.SUPPRESS)
    parser.add_argument("--bytes", type=int, metavar="N", help=argparse.SUPPRESS)
    parser.add_argument("--offset", type=int, default=0, metavar="N", help=argparse.SUPPRESS)
    parser.add_argument("--chunk", type=int, default=None, metavar="N", help=argparse.SUPPRESS)
    parser.add_argument("--inspect-once", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    args = build_parser().parse_args(argv)

    from . import paths

    paths.ensure_vendor_on_path()

    if args.elevated_worker:
        from .usb import driver

        return driver.run_elevated_worker(args.elevated_worker)

    if args.offline_self_test:
        from . import selftest

        target = args.json
        if target is None and not sys.stdout.isatty():
            # 窗口化 exe 从资源管理器启动时没有控制台，结果落到日志目录。
            target = str(paths.log_dir() / "offline-self-test.json")
        return selftest.main([target] if target else [])

    if args.render_pages:
        from .gui.render import render

        result = render(args.render_pages, "simulation" if args.demo else "physical", check=True)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.dump:
        if not args.out:
            print("--dump 需要同时给出 --out 输出文件")
            return 2
        from .research import ResearchError, read_file_to

        try:
            report = read_file_to(
                args.dump,
                Path(args.out),
                progress=lambda m: print(m, flush=True),
                offset=args.offset,
                limit=args.bytes,
                chunk=args.chunk,
            )
        except ResearchError as exc:
            print(f"读取失败：{exc}")
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.inspect_once:
        from . import inspect_once

        return inspect_once.main([args.json] if args.json else [])

    if args.diagnose:
        from . import patches

        print(json.dumps(patches.status(), ensure_ascii=False, indent=2, default=str))
        return 0

    from .gui.window import run

    return run("simulation" if args.demo else "physical")


if __name__ == "__main__":
    raise SystemExit(main())
