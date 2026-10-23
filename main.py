"""从项目根目录启动（源码运行入口）。"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from a6700win.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
