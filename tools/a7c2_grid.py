"""从 A7C2 官方对照图（四宫格）量出每个外观相对 ST 的逐色相饱和度目标。

对照图 seq：左上 ST，右上=第二个，左下=第三个，右下=第四个（见 README.txt）。
每格是同一场景的相机直出，只缩放拼接，没有曝光/白平衡/色彩调整。
量的是「按色相分档的色度中位数」，与像素对齐无关，因此不需要严格的像素级配准。
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from look_loop import jpeg_rgb, srgb2lin  # noqa: E402

W = np.array([0.2126, 0.7152, 0.0722])
BINS = np.arange(0, 361, 30)


def stats(rgb):
    lin = srgb2lin(rgb)
    y = (lin * W).sum(2)
    cb = lin[..., 2] - y
    cr = lin[..., 0] - y
    m = np.hypot(cb, cr)
    hue = np.degrees(np.arctan2(cr, cb)) % 360
    sel = (y > 0.02) & (y < 0.95) & (m > 2e-3)
    s = m / np.maximum(y, 1e-6)
    out = {}
    for i in range(12):
        b = sel & (hue >= BINS[i]) & (hue < BINS[i] + 30)
        out[i] = (float(np.median(s[b])), int(b.sum()))
    out["all"] = (float(np.median(s[sel])), int(sel.sum()))
    return out


def quadrants(img, margin=0.05):
    h, w, _ = img.shape
    tiles = []
    for j in (0, 1):
        for i in (0, 1):
            y0, y1 = int(h * j / 2), int(h * (j + 1) / 2)
            x0, x1 = int(w * i / 2), int(w * (i + 1) / 2)
            dy, dx = int((y1 - y0) * margin), int((x1 - x0) * margin)
            tiles.append(img[y0 + dy:y1 - dy, x0 + dx:x1 - dx])
    return tiles  # TL, TR, BL, BR


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True)
    p.add_argument("--step", type=int, default=4)
    p.add_argument("--json")
    a = p.parse_args(argv)
    files = sorted(Path(a.dir).glob("*.jpg"))
    panels = {}
    for f in files:
        name = f.name
        if "ST_NC_CC_NN" in name:
            labels = ["ST", "NC", "CC", "NN"]
        elif "ST_E_GR" in name:
            labels = ["ST", "Eterna", "GR正片", "GR负片"]
        elif "ST_FL_FL2_FL3" in name or "ST5324" in name:
            labels = ["ST", "FL", "FL2", "FL3"]
        else:
            continue
        img = jpeg_rgb(str(f), a.step)
        tiles = quadrants(img)
        st = stats(tiles[0])
        names = []
        for lbl, t in zip(labels[1:], tiles[1:]):
            s = stats(t)
            panels.setdefault(lbl, []).append((st, s))
            names.append(f.name)
    print("外观      整体比 " + " ".join("%6s" % ("%d-%d" % (BINS[i], BINS[i] + 30)) for i in range(12)))
    import json
    out = {}
    for lbl, pairs in panels.items():
        ratios = []
        for st, s in pairs:
            ratios.append([s[i][0] / st[i][0] if st[i][0] > 1e-6 else np.nan for i in range(12)])
        arr = np.array(ratios)
        med = np.nanmedian(arr, 0)
        overall = [s["all"][0] / st["all"][0] for st, s in pairs]
        out[lbl] = {"overall": round(float(np.median(overall)), 3),
                    "bins": [None if not np.isfinite(x) else round(float(x), 3) for x in med],
                    "sources": names}
        print("%-9s %6.2f  " % (lbl, np.median(overall)) + " ".join(
            "%6.2f" % x if np.isfinite(x) else "     -" for x in med))
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写", a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
