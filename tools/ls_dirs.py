# -*- coding: utf-8 -*-
"""一次会话列出多个目录，用于找挂载点与持久化文件的位置。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import dump  # noqa: E402
from a6700win.research import ServiceSession  # noqa: E402

CANDIDATES = ["/setting", "/data", "/cp", "/etc", "/system", "/var", "/mnt", "/nmnt",
              "/usr/data", "/usr/local", "/usr/share/app"]


def main(argv: list[str]) -> int:
    targets = argv or CANDIDATES
    with ServiceSession(progress=lambda message: None) as session:
        for path in targets:
            try:
                rows = dump.list_dir(session, path)
            except Exception as exc:  # noqa: BLE001
                print(f"{path}: 打不开 ({exc})", flush=True)
                continue
            preview = " ".join(rows[:14])
            print(f"{path}: {len(rows)} 项  {preview}{' …' if len(rows) > 14 else ''}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
