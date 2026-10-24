# -*- coding: utf-8 -*-
"""把 /setting（nflasha2）里的文件整份读回来，用于比较与备份。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import flash  # noqa: E402
from a6700win.research import ServiceSession  # noqa: E402

CHUNK = 0x80000


def main(argv: list[str]) -> int:
    if not argv:
        print("用法: dump_setting.py <相机路径> <输出文件>")
        return 2
    remote, out = argv[0], Path(argv[1])
    with ServiceSession(progress=lambda message: None) as session:
        size = flash.stat(session, remote)
        print(f"{remote}: {size:,} B", flush=True)
        digest = hashlib.sha256()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as handle:
            done = 0
            while done < size:
                block = min(CHUNK, size - done)
                data = flash.read_range(session, remote, done, block)
                handle.write(data)
                digest.update(data)
                done += len(data)
                print(f"  {done:,}/{size:,}", flush=True)
    print(f"sha256 {digest.hexdigest()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
