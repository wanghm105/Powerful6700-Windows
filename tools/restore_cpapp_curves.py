"""把 cpapp 9 条曲线记录写回工厂字节（逐块回读校验）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from a6700win import flash  # noqa: E402
from a6700win.research import ServiceSession  # noqa: E402

FACTORY = ROOT.parent / "firmware" / "cp" / "cpapp-b.bin"
START, END = 0xFE0B50, 0xFE2F50


def main() -> int:
    data = FACTORY.read_bytes()[START:END]
    print(f"工厂曲线区 {len(data):,} 字节 sha256 {__import__('hashlib').sha256(data).hexdigest()[:16]}")
    with ServiceSession() as session:
        live = session.read_range("/cp/cpapp-b.bin", START, len(data))["data"]
        print("当前与工厂一致" if live == data else f"当前不同（差异 {sum(1 for a, b in zip(live, data) if a != b)} 字节），开始写回")
        if live != data:
            offset = 0
            while offset < len(data):
                block = data[offset:offset + flash.BLOCK]
                flash.write_block(session, "/cp/cpapp-b.bin", START + offset, block)
                offset += len(block)
            back = session.read_range("/cp/cpapp-b.bin", START, len(data))["data"]
            print("回读一致 ✓" if back == data else "回读不一致 ✗")
    return 0


if __name__ == "__main__":
    sys.exit(main())
