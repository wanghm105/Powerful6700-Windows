"""PyInstaller 打包入口：把 src/ 放进 sys.path 后转入正式命令行入口。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "src", HERE):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from a6700win.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
