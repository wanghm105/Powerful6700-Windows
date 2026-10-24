"""把 A7C2 参考渲染与机身实拍放在同一张表里对比逐色相响应。

用法：
  python tools/look_compare.py --st WHM00041.JPG \
      --pair cc="2-Classic-Chrome.a7look:WHM00042.JPG" \
      --pair nc="1-Classic-Neg.a7look:WHM00043.JPG" ...
"""
from __future__ import annotations
import argparse, json, sys, tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from look_loop import jpeg_rgb  # noqa: E402
from look_reference import decode_table, apply_look, save_png  # noqa: E402
from look_diff import analyse  # noqa: E402

LOOKDIR = ROOT.parent / "firmware" / "lut" / "a7c2" / "A7C2-Looks-and-DCP-3.0.3" / "Default-Six"


def row(d, label):
    cells = []
    for b in d["bins"]:
        if b["ratio"] is None:
            cells.append("%-14s" % "-")
        else:
            cells.append("%.2f/%+4.1f/%+5.0f" % (b["ratio"], b["rot"], b["dwarm"] * 1000))
    return "%-10s 整体 %-6.3f  " % (label, d["ratio"]) + " ".join(cells)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--st", required=True)
    p.add_argument("--pair", action="append", default=[], help="名字=a7look文件:实拍JPEG")
    p.add_argument("--step", type=int, default=3)
    p.add_argument("--json")
    a = p.parse_args(argv)
    base = jpeg_rgb(a.st, a.step)
    out = {"st": str(a.st), "looks": {}}
    hdr = "%-10s %-50s " % ("", "整体比") + " ".join("%9s" % ("%d-%d" % (i * 30, i * 30 + 30)) for i in range(12))
    print("列 = 饱和度比/色相旋转(度)/冷暖差(‰)，按 ST 的 12 个色相档")
    print(hdr)
    for item in a.pair:
        name, _, spec = item.partition("=")
        look_file, _, cam = spec.partition(":")
        doc = json.loads((LOOKDIR / look_file).read_text(encoding="utf-8-sig"))
        coeff = decode_table(doc)
        ref = apply_look(base, coeff)
        tmp = Path(tempfile.gettempdir()) / ("ref-%s.png" % name)
        save_png(ref, tmp)
        d_ref = analyse(a.st, str(tmp), step=a.step)
        d_cam = analyse(a.st, cam, step=a.step)
        print(row(d_ref, name + "(参考)"))
        print(row(d_cam, name + "(机身)"))
        out["looks"][name] = {"ref": d_ref, "camera": d_cam, "camera_file": cam, "look_file": look_file}
        print()
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写", a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
