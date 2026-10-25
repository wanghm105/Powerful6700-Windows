#!/usr/bin/env python
"""菜单文字（外观名字）的命令行入口：状态 / 写入 / 还原。

    python tools/looknames_apply.py --status
    python tools/looknames_apply.py --apply --preset zh --confirm yes-write
    python tools/looknames_apply.py --restore --confirm yes-write

相机需先切到「USB 连接模式 → 海量存储器(MSC)」并只连一台 A6700。
写入会把整份语言资源（约 142 KB）存成基线；还原优先整份逐字节写回。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from a6700win import looknames, paths  # noqa: E402

paths.ensure_vendor_on_path()
from a6700win import patches  # noqa: E402

patches.install()


def say(message: str) -> None:
    print("  |", message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="菜单文字状态 / 写入 / 还原")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="只读：打印当前文字与基线状态")
    group.add_argument("--apply", action="store_true", help="写入当前命名方案")
    group.add_argument("--restore", action="store_true", help="还原（有基线整份写回，否则改回短名）")
    parser.add_argument("--preset", choices=sorted(looknames.PRESETS), default=None,
                        help="命名方案；默认用上次保存的那套")
    parser.add_argument("--confirm", default="", help="写入类操作必须带 --confirm yes-write")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    writing = args.apply or args.restore
    if writing and args.confirm != "yes-write":
        print("拒绝执行：写入会持久修改相机固件里的语言资源文件。"
              "确认相机已切 MSC、只连这一台，再加 --confirm yes-write。", file=sys.stderr)
        return 2

    try:
        if args.status:
            report = looknames.read(say, preset=args.preset)
        elif args.apply:
            report = looknames.apply(say, preset=args.preset)
        else:
            report = looknames.restore(say, preset=args.preset)
    except looknames.LookNamesError as exc:
        print("失败：%s" % exc, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("文件：%s" % report.get("path"))
        print("字节：%(bytes)s  sha256：%(sha256)s  类型：%(kind)s" % report)
        for row in report.get("looks") or []:
            print("  %-6s %-18s 当前 %-20s 目标 %-20s %s" % (
                row.get("slot"), row.get("label") or "",
                row.get("current"), row.get("target"), row.get("state")))
        if report.get("mode"):
            print("模式：%s" % report["mode"])
        baseline = report.get("baseline") or {}
        best = baseline.get("best")
        if isinstance(best, dict):
            print("基线：出厂 %(bytes)s 字节 · %(kind)s · sha256 %(sha)s… · 共 %(count)s 份" % {
                "bytes": best.get("bytes"), "kind": best.get("kind"),
                "sha": str(best.get("sha256"))[:12], "count": baseline.get("count")})
        else:
            print("基线：%s（%s 份）" % (best or "无出厂基线", baseline.get("count")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
