"""只读读取某分区的前 N 字节。用法：python tools/_peek.py PART BYTES"""
from __future__ import annotations
import sys
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from a6700win.research import ServiceSession

part, want = sys.argv[1], int(sys.argv[2])
CHUNK = 0x40000
out = Path(f"../firmware/parts/{part}-head.bin")
with ServiceSession(progress=lambda m: print(m, flush=True)) as session:
    done = 0
    with out.open("wb") as handle:
        while done < want:
            n = min(CHUNK, want - done)
            data = session.read_range(f"/dev/{part}", done, n)["data"]
            if not data:
                break
            handle.write(data)
            done += len(data)
print(f"{part}: {done:,} 字节 -> {out}")
