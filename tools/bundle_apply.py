#!/usr/bin/env python
"""一次写入/还原（颜色 + 菜单文字）的命令行入口。

    python tools/bundle_apply.py --apply --preset zh --confirm yes-write
    python tools/bundle_apply.py --restore --confirm yes-write

和界面上的「一次写入（颜色 + 名字）」是同一段编排：两段独立会话，
中间自动等相机复位（默认 50 秒）。相机需先切到「USB 连接模式 → 海量存储器(MSC)」。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from a6700win import bundle, looknames, paths  # noqa: E402

paths.ensure_vendor_on_path()
from a6700win import patches  # noqa: E402

patches.install()


def say(message: str) -> None:
    print("  |", message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="一次写入 / 还原：颜色 + 菜单文字")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="颜色与菜单文字一起写")
    group.add_argument("--restore", action="store_true", help="颜色与菜单文字一起还原")
    parser.add_argument("--preset", choices=sorted(looknames.PRESETS), default=None,
                        help="命名方案；默认用上次保存的那套")
    parser.add_argument("--confirm", default="", help="必须带 --confirm yes-write")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整报告")
    args = parser.parse_args()

    if args.confirm != "yes-write":
        print("拒绝执行：这一步会同时改相机运行内存里的颜色与 /usr 里的语言资源。"
              "确认相机已切 MSC、只连这一台，再加 --confirm yes-write。", file=sys.stderr)
        return 2

    runner = bundle.apply if args.apply else bundle.restore
    try:
        report = runner(say, preset=args.preset)
    except bundle.BundleError as exc:
        print("失败：%s" % exc, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    names = report.get("names") or {}
    colors = report.get("colors") or {}
    print("命名方案：%s" % report.get("label"))
    for row in colors.get("looks") or []:
        print("  颜色 %-4s %-8s" % (row.get("name"), row.get("state")))
    if names:
        print("  文字 文件 %(bytes)s 字节 · 类型 %(kind)s · 模式 %(mode)s" % {
            "bytes": names.get("bytes"), "kind": names.get("kind"),
            "mode": names.get("mode") or "-"})
        for change in names.get("changes") or []:
            print("        0x%08x：%r → %r" % (change["rid"], change["old"], change["new"]))
    for line in bundle.summary(report):
        print("  " + line)
    if report.get("error"):
        print("停在这里：%s" % report["error"], file=sys.stderr)
        return 1
    print("用时 %.0f 秒" % float(report.get("seconds") or 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
