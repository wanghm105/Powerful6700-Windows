# -*- coding: utf-8 -*-
"""List directories on the camera over the read-only payload (no camera writes)."""
from __future__ import annotations

import argparse
import io
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="列出相机上的目录内容")
    parser.add_argument("paths", nargs="+", help="绝对路径，例如 /mnt")
    parser.add_argument("--grep", default="", help="只显示匹配该子串的项（不区分大小写）")
    args = parser.parse_args(argv)

    from a6700win.research import ServiceSession

    with ServiceSession(progress=lambda message: print("·", message)) as session:
        for target in args.paths:
            print("==", target)
            try:
                entries = session.list_dir(target)
            except Exception as exc:
                print("   失败：", exc)
                continue
            if not entries:
                print("   （空目录）")
            for name in entries:
                if args.grep and args.grep.lower() not in name.lower():
                    continue
                print("  ", name)
            print("    共", len(entries), "项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
