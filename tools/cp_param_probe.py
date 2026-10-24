"""探针：验证 CP 参数 50..55 是否是六个自定义外观的颜色 bank 索引。

做法：把 SE 的色度记录（bank 9）复制到 bank 40，再把参数 50..55 写成 40；
若 1ST..6BW 六个自定义位都变成 SE 的褐色，说明参数 50..55 = 自定义位 → bank。
写入前自动备份实时单元，可用 --restore 还原。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import patches, paths  # noqa: E402

paths.ensure_vendor_on_path()

from a6700_unlock.usb import legacy  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402

UNIT = 0x02A40001
PARAM_BASE = 0x1200
CHROMA_BASE = 0x1250
BANK = 40
SOURCE_BANK = 9
BACKUP = ROOT.parent / "firmware" / "cp" / "probe" / "unit-02a40001.params50.bin"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    try:
        reader, writer = CpReader(target, channel), CpWriter(target, channel)
        live = bytearray(reader.read_unit(UNIT))
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        if not args.restore:
            BACKUP.write_bytes(bytes(live))
            print(f"已备份实时单元 → {BACKUP.name}")

        if args.restore:
            if not BACKUP.exists():
                print("没有备份，无法还原")
                return 1
            restored = BACKUP.read_bytes()
            writer.write_unit(UNIT, restored)
            back = CpReader(target, channel).read_unit(UNIT)
            print("还原回读一致 ✓" if bytes(back) == restored else "还原回读不一致 ✗")
            return 0

        if args.confirm != "yes-write":
            print("写入需要 --confirm yes-write")
            return 2

        record = bytes(live[CHROMA_BASE + SOURCE_BANK * 64: CHROMA_BASE + (SOURCE_BANK + 1) * 64])
        live[CHROMA_BASE + BANK * 64: CHROMA_BASE + (BANK + 1) * 64] = record
        for param in range(50, 56):
            live[PARAM_BASE + param] = BANK
        print("参数 50..55 原值：", [live[PARAM_BASE + p] for p in range(50, 56)], "→ 写入", BANK)
        writer.write_unit(UNIT, bytes(live))
        back = CpReader(target, channel).read_unit(UNIT)
        same = all(back[PARAM_BASE + p] == BANK for p in range(50, 56)) and bytes(back) == bytes(live)
        print("回读一致 ✓" if same else "回读不一致 ✗")
        print(f"新 sha256 {hashlib.sha256(bytes(back)).hexdigest()[:16]}")
    finally:
        legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
        legacy.close_target(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
