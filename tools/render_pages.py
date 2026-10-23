"""无头渲染每个页面到 PNG，用于界面回归与文档配图（不需要相机）。

用法：
    QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts \
        ./.venv/Scripts/python.exe tools/render_pages.py --out .data/shots --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把每个页面渲染成 PNG")
    parser.add_argument("--out", default=str(ROOT / ".data" / "shots"), help="输出目录")
    parser.add_argument("--mode", default="physical", choices=("physical", "simulation"))
    parser.add_argument("--size", default="1240x860", help="窗口尺寸，例如 1240x860")
    parser.add_argument("--check", action="store_true", help="先跑一次启动检查再截图")
    args = parser.parse_args(argv)

    from a6700win.gui.render import render

    result = render(args.out, args.mode, args.size, args.check)
    for path in result["files"]:
        print("wrote %s" % path)
    print(json.dumps({k: result[k] for k in ("out", "phase", "ready")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
