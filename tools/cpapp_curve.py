"""cpapp 曲线层实验：把 9 条 1024 B 恒等曲线改写成指定形状，并可选写回真机。

用法（全部需要相机处于 MSC / WinUSB 已绑定）：
  python tools/cpapp_curve.py --show                      # 只看当前 9 条记录形状（离线读本地镜像）
  python tools/cpapp_curve.py --shape gamma22 --dry-run    # 生成补丁窗口，不写
  python tools/cpapp_curve.py --shape gamma22 --apply --confirm yes-write
  python tools/cpapp_curve.py --restore ../firmware/cp/cpapp-live.bin --apply --confirm yes-write

曲线格式：512 个 u16，分段线性恒等映射（16 段 4096 + 16 段 256 + 尾部 1 级）。
这里只改值域内的斜率，不改分段结构。
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from a6700win import paths  # noqa: E402

paths.ensure_vendor_on_path()

BASE = Path(__file__).resolve().parent.parent
LOCAL_IMAGE = BASE.parent / "firmware" / "cp" / "cpapp-b.bin"
TARGET_PATH = "/cp/cpapp-b.bin"
SLOT_BASE = 0xFE0B50
SLOT_STRIDE = 0x400
SLOT_COUNT = 9
ENTRIES = 512

# 恒等分段：前 16 个点每步 4096，接着 16 个点每步 256，再逐步 1 直到 65535
BREAK = 16
FINE = 16


def identity() -> list[int]:
    values: list[int] = []
    v = 0
    for _ in range(BREAK):
        values.append(v)
        v += 0x1000
    for _ in range(FINE):
        values.append(v)
        v += 0x100
    while v < 0xFFFF:
        values.append(v)
        v += 1
    while len(values) < ENTRIES:
        values.append(0xFFFF)
    return values[:ENTRIES]


def shape(name: str) -> list[int]:
    base = identity()
    if name == "identity":
        return base
    out: list[int] = []
    for value in base:
        x = value / 0xFFFF
        if name == "gamma22":
            y = x ** (1 / 2.2)
        elif name == "gamma08":
            y = x ** (1 / 0.8)
        elif name == "invert":
            y = 1.0 - x
        elif name == "softs":
            y = 1 / (1 + math.exp(-6 * (x - 0.5)))
            lo = 1 / (1 + math.exp(3))
            hi = 1 / (1 + math.exp(-3))
            y = (y - lo) / (hi - lo)
        else:
            raise SystemExit(f"unknown shape {name}")
        out.append(max(0, min(0xFFFF, int(round(y * 0xFFFF)))))
    # 保持单调
    for i in range(1, len(out)):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


def windows_from(image: bytes) -> list[dict]:
    return [
        {
            "offset": SLOT_BASE + i * SLOT_STRIDE,
            "length": SLOT_STRIDE,
            "before": image[SLOT_BASE + i * SLOT_STRIDE : SLOT_BASE + (i + 1) * SLOT_STRIDE],
        }
        for i in range(SLOT_COUNT)
    ]


def build(new_curve: list[int], image: bytes) -> list[dict]:
    payloads = []
    record = struct.pack("<512H", *new_curve)
    assert len(record) == SLOT_STRIDE
    for i, window in enumerate(windows_from(image)):
        payloads.append(
            {
                "offset": window["offset"],
                "before": window["before"],
                "after": record,
                "slot": i,
            }
        )
    return payloads


def connect():
    import struct as _struct

    from a6700_unlock.usb import legacy  # noqa: PLC0415

    from a6700win import patches  # noqa: PLC0415
    from look_name import ChannelBackend  # noqa: PLC0415

    patches.install()
    target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
    return target, ChannelBackend(channel), legacy


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=str(LOCAL_IMAGE))
    parser.add_argument("--shape", default="identity")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--restore", default="")
    parser.add_argument("--out", default=str(BASE / ".data" / "cpapp-curve-plan.json"))
    args = parser.parse_args(argv)

    image = Path(args.image).read_bytes()
    print(f"镜像 {args.image} {len(image):,} B")

    if args.restore:
        source = Path(args.restore).read_bytes()
        if len(source) != len(image):
            raise SystemExit("还原镜像是整份 cpapp，请用 --image 指向真机字节数一致的镜像")
        payloads = [
            {
                "offset": w["offset"],
                "before": image[w["offset"] : w["offset"] + w["length"]],
                "after": source[w["offset"] : w["offset"] + w["length"]],
                "slot": i,
            }
            for i, w in enumerate(windows_from(image))
        ]
    else:
        curve = shape(args.shape)
        print(f"曲线 {args.shape}：首 4 个值 {curve[:4]}，末 4 个 {curve[-4:]}")
        payloads = build(curve, image)

    if args.show:
        vals = struct.unpack_from("<512H", image, SLOT_BASE)
        print("slot0 抽样：", [hex(v) for v in vals[::32]])
        return 0

    Path(args.out).write_text(
        json.dumps(
            [
                {
                    "offset": hex(p["offset"]),
                    "before": p["before"].hex(),
                    "after": p["after"].hex(),
                }
                for p in payloads
            ],
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"补丁计划写入 {args.out}（{len(payloads)} 个窗口，每个 {SLOT_STRIDE} B）")

    if not args.apply:
        print("未写入（加 --apply --confirm yes-write 才写）")
        return 0
    if args.confirm != "yes-write":
        raise SystemExit("写入需要 --confirm yes-write")

    from a6700win import flash  # noqa: PLC0415

    target, backend, legacy = connect()
    try:
        for payload in payloads:
            live = flash.read_range(backend, TARGET_PATH, payload["offset"], SLOT_STRIDE)
            if live != payload["before"]:
                raise SystemExit(f"0x{payload['offset']:X} 现场值与计划不符，已中止（未写入）")
            flash.write_block(backend, TARGET_PATH, payload["offset"], payload["after"])
            check = flash.read_range(backend, TARGET_PATH, payload["offset"], SLOT_STRIDE)
            print(f"  写入 0x{payload['offset']:X} 回读{'一致' if check == payload['after'] else '不一致'}")
            if check != payload["after"]:
                raise SystemExit("回读不一致，中止")
        print("全部完成：请关机重启后再看画面")
    finally:
        try:
            legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            legacy.close_target(target)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
