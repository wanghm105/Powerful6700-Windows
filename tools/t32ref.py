"""扫描 ARM32 Thumb 裸镜像里指向指定区间的 ADR / MOVW+MOVT 引用。

用法： python tools/t32ref.py --image ../firmware/cp/cpapp-b.bin --lo 0xFE0000 --hi 0x11102B8
"""
from __future__ import annotations

import argparse
import struct
import sys


def adr_targets(data: bytes):
    """16 位 ADR：0xA0xx，target = ((pc+4) & ~3) + imm*4。"""
    for p in range(0, len(data) - 4, 2):
        hw = data[p] | (data[p + 1] << 8)
        if (hw & 0xF800) != 0xA000:
            continue
        imm = (hw & 0xFF) * 4
        rd = (hw >> 8) & 0x7
        pc = ((p + 4) & ~3)
        yield p, pc + imm, rd


def movw_targets(data: bytes):
    """MOVW/MOVT 32 位常量：0xF240/0xF2C0（ARMv7 Thumb-2）。"""
    pairs = {}
    for p in range(0, len(data) - 8, 2):
        hw1 = data[p] | (data[p + 1] << 8)
        if (hw1 & 0xFBF0) not in (0xF240, 0xF2C0):
            continue
        hw2 = data[p + 2] | (data[p + 3] << 8)
        if (hw2 & 0x8000) == 0:
            continue
        imm4 = (hw1 >> 0) & 0xF
        i = (hw1 >> 10) & 1
        imm3 = (hw2 >> 12) & 0x7
        imm8 = hw2 & 0xFF
        value = (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8
        reg = (hw2 >> 8) & 0xF
        is_movt = (hw1 & 0xFBF0) == 0xF2C0
        if not is_movt:
            pairs[reg] = (p, value)
        elif reg in pairs:
            start, low = pairs.pop(reg)
            yield start, (value << 16) | low, reg


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="../firmware/cp/cpapp-b.bin")
    parser.add_argument("--lo", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--hi", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    data = open(args.image, "rb").read()
    print(f"image {args.image} {len(data)} bytes")
    hits = []
    for p, target, rd in adr_targets(data):
        if args.lo <= target < args.hi:
            hits.append((p, target, "adr", rd))
    for p, target, rd in movw_targets(data):
        if args.lo <= target < args.hi:
            hits.append((p, target, "movw", rd))
    hits.sort()
    print(f"hits {len(hits)}")
    for p, target, kind, rd in hits[: args.limit]:
        print(f"  0x{p:06X} -> 0x{target:08X} {kind} r{rd}  delta 0x{target - args.lo:X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())