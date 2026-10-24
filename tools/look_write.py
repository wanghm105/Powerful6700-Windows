"""按「基底记录 × 缩放」一次性合成并写入多个外观的色度记录。

用法：
  python tools/look_write.py --look CC=bank6:bank6:0.76 --look NC=bank4:bank4:0.68 ^
      --look VV=bank1:bank3:1.10 --look VV2=bank5:bank5:0.80 --confirm yes-write

每个 --look 形如  菜单名=目标bank:基底bank:系数
 目标bank 1..9 对应 CP 单元 0x1250 + bank*64 的 64 字节记录；
 基底 bank 取自出厂副本 unit-02a40001.backup-def.bin。
"""
from __future__ import annotations
import argparse, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
from a6700win import patches, paths, windows_shim  # noqa: E402
paths.ensure_vendor_on_path()
from a6700_unlock.usb import legacy  # noqa: E402
from cp_read import CpReader  # noqa: E402
from cp_write import CpWriter  # noqa: E402

UNIT = 0x02A40001
CHROMA_BASE, STRIDE = 0x1250, 64
PARAM_BASE = 0x1200
FACTORY = ROOT.parent / "firmware" / "cp" / "unit-02a40001.backup-def.bin"


def _bank_values(factory: bytes, bank: int) -> list[int]:
    off = CHROMA_BASE + bank * STRIDE
    return list(struct.unpack_from("<24h", factory, off))


def blend(factory: bytes, spec: str) -> list[float]:
    """基底描述：'6' 或 '4+14' 或 '4*0.6+14*0.4'，返回 24 个加权平均分量。"""
    total = 0.0
    acc = [0.0] * 24
    for part in spec.split("+"):
        bank, _, weight = part.partition("*")
        w = float(weight) if weight else 1.0
        vals = _bank_values(factory, int(bank.replace("bank", "")))
        acc = [a + v * w for a, v in zip(acc, vals)]
        total += w
    return [a / total for a in acc]


def record(factory: bytes, base: str, factor: float, pairs=()) -> bytes:
    vals = blend(factory, base)
    out = [max(-32768, min(32767, int(round(v * factor)))) for v in vals]
    for idx, pf in pairs:
        out[idx * 2] = max(-32768, min(32767, int(round(out[idx * 2] * pf))))
        out[idx * 2 + 1] = max(-32768, min(32767, int(round(out[idx * 2 + 1] * pf))))
    body = struct.pack("<24h", *out)
    return body + bytes(STRIDE - len(body))


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--look", action="append", default=[],
                   help="菜单名=目标bank:基底bank:系数")
    p.add_argument("--param", action="append", default=[], help="N=V 写参数表（0x1200+N）")
    p.add_argument("--confirm", default="")
    p.add_argument("--keep-service", action="store_true")
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args(argv)
    if args.confirm != "yes-write":
        print("需要 --confirm yes-write")
        return 2

    factory = FACTORY.read_bytes()
    plan = []
    for spec in args.look:
        name, rest = spec.split("=", 1)
        target, base, factor = rest.split(":", 2)
        pairs = []
        if "@" in factor:
            factor, _, pair_spec = factor.partition("@")
            for item in pair_spec.split(","):
                if not item.strip():
                    continue
                idx, _, pf = item.partition("*")
                pairs.append((int(idx), float(pf)))
        plan.append((name, int(target.replace("bank", "")), base, float(factor), pairs))

    patches.install()
    lock = windows_shim.device_lock(paths.state_dir()); lock.__enter__()
    target = channel = None
    try:
        target, channel = legacy.run_authentication(None, 0x0336, args.timeout, True,
                                                    progress=lambda m: print(m, flush=True))
        reader, writer = CpReader(target, channel), CpWriter(target, channel)
        unit = bytearray(reader.read_unit(UNIT))
        for name, tbank, bbank, factor, pairs in plan:
            rec = record(factory, bbank, factor, pairs)
            off = CHROMA_BASE + tbank * STRIDE
            unit[off:off + STRIDE] = rec
            print("bank %d <- 基底 %s × %.3f  pair覆写 %s  (%s)" % (tbank, bbank, factor, pairs, name))
        for item in args.param:
            index, value = item.split("=", 1)
            unit[PARAM_BASE + int(index)] = int(value) & 0xFF
            print("param %s = %d" % (index, int(value) & 0xFF))
        writer.write_unit(UNIT, bytes(unit))
        back = reader.read_unit(UNIT)
        if back != bytes(unit):
            print("回读不一致 ✗")
            return 3
        print("回读一致 ✓")
        for name, tbank, bbank, factor, pairs in plan:
            off = CHROMA_BASE + tbank * STRIDE
            print("  bank %d: %s" % (tbank, struct.unpack_from("<24h", back, off)))
    finally:
        if not args.keep_service:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            except Exception as exc:
                print("stop failed", exc)
        try: legacy.close_target(target)
        except Exception as exc: print("close failed", exc)
        try: lock.__exit__(None, None, None)
        except Exception: pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


