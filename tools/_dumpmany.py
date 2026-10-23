"""一次会话内 dump 多个分区（只读）。用法：python tools/_dumpmany.py SUFFIX PART [PART...]"""
from __future__ import annotations
import hashlib
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from a6700win.research import ServiceSession

OUT = Path("../firmware/parts")
OUT.mkdir(parents=True, exist_ok=True)
CHUNK = 0x40000

def main(argv):
    suffix = argv[0]
    parts = [p for p in argv[1:]]
    with ServiceSession(progress=lambda m: print(m, flush=True)) as session:
        for part in parts:
            path = f"/dev/{part}"
            try:
                size = session.stat(path)
            except Exception as exc:
                print(f"{part}: stat 失败 {exc}", flush=True)
                continue
            out = OUT / f"{part}-{suffix}.bin"
            digest = hashlib.sha256()
            started = time.monotonic()
            done = 0
            with out.open("wb") as handle:
                while done < size:
                    length = min(CHUNK, size - done)
                    data = session.read_range(path, done, length)["data"]
                    if not data:
                        raise SystemExit(f"{part}: 偏移 {done} 读到 0 字节")
                    handle.write(data)
                    digest.update(data)
                    done += len(data)
            rate = done / max(1e-6, time.monotonic() - started)
            print(f"{part}: {done:,} 字节 {rate/1024:.0f} KiB/s sha256={digest.hexdigest()}", flush=True)

main(sys.argv[1:])
