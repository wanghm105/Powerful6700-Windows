"""基于 live 基线与参数合成一个 CP CC1 单元文件（只改指定 bank 的 24 个 int16）。

用法：
    python tools/cp_slot.py --slot 6 --params "a,b,c,d,e,f" [--v6 N --v7 N] --out x.bin
    python tools/cp_slot.py --slot 4 --identity --out y.bin
    python tools/cp_slot.py --slot 9 --from-slot 6 --out z.bin

参数顺序与固件一致：g0 = (a, b, c, d, e, f, v6, v7)，其余两组（A1-B、A2-B）默认清零。
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "firmware" / "cp" / "live" / "unit-02a40001.bin"
SLOT_BASE = 0x1250
SLOT_STRIDE = 64


def load_base(path):
    data = bytearray(Path(path).read_bytes())
    if len(data) != 8192:
        raise SystemExit(f"{path} 长度 {len(data)}，应为 8192")
    return data


def slot_values(data, slot):
    off = SLOT_BASE + slot * SLOT_STRIDE
    return list(struct.unpack_from("<24h", data, off))


def write_slot(data, slot, values, group1=None, group2=None):
    off = SLOT_BASE + slot * SLOT_STRIDE
    flat = list(values)
    flat += list(group1) if group1 else [0] * 8
    flat += list(group2) if group2 else [0] * 8
    if len(flat) != 24:
        raise SystemExit("槽内数值必须是 24 个 int16")
    struct.pack_into("<24h", data, off, *[int(v) for v in flat])


def parse_params(text):
    parts = [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
    if len(parts) == 6:
        a, b, c, d, e, f = (int(float(p)) for p in parts)
        return [a, b, c, d, e, f]
    raise SystemExit(f"参数应形如 a,b,c,d,e,f（6 个数），收到 {text!r}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="合成 CC1 单元文件")
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--params", help="a,b,c,d,e,f")
    parser.add_argument("--identity", action="store_true", help="六系数全 0（单位矩阵）")
    parser.add_argument("--from-slot", type=int, help="复制另一个 bank 的 24 个值")
    parser.add_argument("--v6", type=int)
    parser.add_argument("--v7", type=int)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    data = load_base(args.base)
    current = slot_values(data, args.slot)
    if not 0 <= args.slot < 54:
        raise SystemExit("槽号应在 0..53")

    if args.from_slot is not None:
        values = slot_values(data, args.from_slot)
    else:
        if args.identity:
            values = [0, 0, 0, 0, 0, 0, current[6], current[7]]
        elif args.params:
            values = parse_params(args.params) + [current[6], current[7]]
        else:
            raise SystemExit("需要 --params、--identity 或 --from-slot 之一")
    if args.v6 is not None:
        values[6] = args.v6
    if args.v7 is not None:
        values[7] = args.v7

    write_slot(data, args.slot, values)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(bytes(data))
    print(f"槽 {args.slot} g0 = {values}")
    print(f"g1/g2 已清零；输出 {args.out}  {len(data)} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
