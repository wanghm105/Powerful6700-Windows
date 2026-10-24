"""两张同机位 JPEG 的逐像素色度响应分析（比全图均值灵敏得多）。

输出：整体色度比、整体色相旋转，以及按参考图色相分 12 档的「饱和度比 / 色相旋转 / 冷暖偏移」。

用法：
    python tools/look_diff.py 参考.JPG 目标.JPG [--step 3] [--json out.json]
"""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from look_loop import jpeg_rgb, srgb2lin  # noqa: E402

W = np.array([0.2126, 0.7152, 0.0722], np.float32)


def opponent(lin):
    y = (lin * W).sum(2, keepdims=True)
    cb = lin[..., 2:3] - y
    cr = lin[..., 0:1] - y
    return y[..., 0], cb[..., 0], cr[..., 0]


def analyse(ref_path, out_path, step=3):
    a = srgb2lin(jpeg_rgb(ref_path, step))
    b = srgb2lin(jpeg_rgb(out_path, step))
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    a = a[:h, :w]; b = b[:h, :w]
    ya, cba, cra = opponent(a)
    yb, cbb, crb = opponent(b)
    ma = np.hypot(cba, cra); mb = np.hypot(cbb, crb)
    mask = (ya > 0.01) & (ya < 0.9) & (ma > 3e-3)
    ratio = np.where(mask, mb / np.maximum(ma, 1e-6), np.nan)
    hue_a = np.degrees(np.arctan2(cra, cba)) % 360
    hue_b = np.degrees(np.arctan2(crb, cbb)) % 360
    rot = ((hue_b - hue_a + 180) % 360) - 180
    overall_ratio = float(np.nanmedian(ratio))
    overall_rot = float(np.nanmedian(np.where(mask, rot, np.nan)))
    bins = []
    for i in range(12):
        lo, hi = i * 30, (i + 1) * 30
        sel = mask & (hue_a >= lo) & (hue_a < hi)
        if sel.sum() < 2000:
            bins.append({"hue": f"{lo}-{hi}", "n": int(sel.sum()), "ratio": None, "rot": None})
            continue
        bins.append({
            "hue": f"{lo}-{hi}",
            "n": int(sel.sum()),
            "ratio": round(float(np.nanmedian(ratio[sel])), 4),
            "rot": round(float(np.nanmedian(rot[sel])), 2),
            "dwarm": round(float(np.nanmean((b[..., 0] - b[..., 2])[sel] - (a[..., 0] - a[..., 2])[sel])), 5),
        })
    return {"ref": os.path.basename(ref_path), "target": os.path.basename(out_path),
            "ratio": round(overall_ratio, 4), "rot": round(overall_rot, 2), "bins": bins}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("ref"); p.add_argument("target")
    p.add_argument("--step", type=int, default=3)
    p.add_argument("--json")
    args = p.parse_args(argv)
    r = analyse(args.ref, args.target, args.step)
    print("%s -> %s  整体色度比 %.4f  色相旋转 %+0.2f°" % (r["ref"], r["target"], r["ratio"], r["rot"]))
    print("  色相区间    像素数     色度比   旋转    冷暖差")
    for b in r["bins"]:
        if b["ratio"] is None:
            print("  %-10s %8d       --      --      --" % (b["hue"], b["n"]))
        else:
            print("  %-10s %8d   %6.3f  %+6.2f  %+.4f" % (b["hue"], b["n"], b["ratio"], b["rot"], b["dwarm"]))
    if args.json:
        Path(args.json).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print("written", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

