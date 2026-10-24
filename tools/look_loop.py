"""外观调色闭环：用 RAW 当“无限精细色卡”，量出相机外观的真实响应。

三个子命令：
  measure  --raw A.ARW --jpeg LABEL=FILE [LABEL=FILE ...]     量每张 JPEG 相对 RAW 场景的色度增益/冷暖
  simulate --jpeg BASE.JPG --out DIR --param FACTOR:TINT ...  离线把候选参数渲染成预览图（近似模型）
  solve    --base-gain G --slope S --target-gain T ...        由标定斜率反解参数

色度增益 = 中位 (输出色度 / 场景色度)，以线性光计算；冷暖 = 中位色度像素上的 (R-B) 均值。
"""
from __future__ import annotations
import argparse, os
from PySide6.QtGui import QImage
import numpy as np

W = np.array([0.2126, 0.7152, 0.0722], np.float32)


def jpeg_rgb(path: str, step: int = 1) -> np.ndarray:
    img = QImage(path).convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine())
    a = a[:, : w * 3].reshape(h, w, 3).astype(np.float32) / 255.0
    return a[::step, ::step]


def linear_scene(path: str) -> np.ndarray:
    import rawpy
    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                              output_color=rawpy.ColorSpace.sRGB, use_camera_wb=True,
                              no_auto_bright=True, gamma=(1, 1), output_bps=16)
    return (rgb.astype(np.float32) / 65535.0)


def srgb2lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin2srgb(x):
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 0), 1 / 2.4) - 0.055)


def fit_grid(a: np.ndarray, shape) -> np.ndarray:
    h, w = shape
    ys = np.linspace(0, a.shape[0] - 1, h).astype(int)
    xs = np.linspace(0, a.shape[1] - 1, w).astype(int)
    return a[ys][:, xs]


def chroma_of(rgb: np.ndarray):
    s = rgb.sum(2, keepdims=True) + 1e-6
    d = rgb / s - 1.0 / 3.0
    return np.sqrt((d * d).sum(2)), d


def measure_pair(scene_lin: np.ndarray, out_lin: np.ndarray) -> dict:
    ms, _ = chroma_of(scene_lin)
    mo, _ = chroma_of(out_lin)
    msk = (ms > 0.02) & (ms < 0.3) & (scene_lin.max(2) < 0.95) & (scene_lin.min(2) > 0.002)
    gain = float(np.median(mo[msk] / np.maximum(ms[msk], 1e-6)))
    mx = out_lin.max(2); mn = out_lin.min(2)
    sat = np.where(mx > 0.02, (mx - mn) / np.maximum(mx, 1e-6), 0)
    cm = msk & (sat > 0.03) & (sat < 0.9)
    warm = float(np.mean((out_lin[..., 0] - out_lin[..., 2])[cm]))
    return {"gain": gain, "warmth": warm, "pixels": int(msk.sum())}


def simulate(base_lin: np.ndarray, factor: float, tint: float) -> np.ndarray:
    """近似相机 CP 模型：色度整体乘 factor，蓝通道按 tint 缩放（tint<1 偏暖）。"""
    y = (base_lin * W).sum(2, keepdims=True)
    out = y + factor * (base_lin - y)
    out[..., 2] *= tint
    return np.clip(out, 0, 1)


def cmd_measure(args):
    scene = linear_scene(args.raw)
    print("scene %s  mean=%s" % (os.path.basename(args.raw), np.round(scene.reshape(-1, 3).mean(0), 4)))
    rows = []
    for item in args.jpeg:
        label, path = item.split("=", 1)
        j = jpeg_rgb(path, args.step)
        h, w = j.shape[:2]
        s = fit_grid(scene, (h, w))
        r = measure_pair(s, srgb2lin(j))
        rows.append((label, r))
        print("%-8s gain %.4f  warmth %+0.4f  (%d px)" % (label, r["gain"], r["warmth"], r["pixels"]))
    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in rows}, fh, ensure_ascii=False, indent=2)
        print("written", args.json)


def cmd_pairs(args):
    rows = []
    for item in args.pair:
        label, rest = item.split("=", 1)
        raw, jpeg_path = rest.split(",", 1)
        scene = linear_scene(raw)
        j = jpeg_rgb(jpeg_path, args.step)
        h, w = j.shape[:2]
        r = measure_pair(fit_grid(scene, (h, w)), srgb2lin(j))
        rows.append((label, r))
        print("%-8s gain %.4f  warmth %+0.4f  (%d px)  %s" % (label, r["gain"], r["warmth"], r["pixels"], os.path.basename(jpeg_path)))
    if rows:
        base = rows[0]
        print("-- 相对 %s --" % base[0])
        for label, r in rows:
            print("%-8s ratio %.3f   delta_warmth %+0.4f" % (
                label, r["gain"] / base[1]["gain"], r["warmth"] - base[1]["warmth"]))
    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in rows}, fh, ensure_ascii=False, indent=2)
        print("written", args.json)


def cmd_simulate(args):
    base = srgb2lin(jpeg_rgb(args.jpeg, args.step))
    os.makedirs(args.out, exist_ok=True)
    for item in args.param:
        f, t = item.split(":")
        out = lin2srgb(simulate(base, float(f), float(t)))
        img = QImage((out * 255).astype(np.uint8).tobytes(), out.shape[1], out.shape[0],
                     out.shape[1] * 3, QImage.Format_RGB888)
        path = os.path.join(args.out, "preview_f%s_t%s.png" % (f, t))
        img.save(path)
        print("wrote", path)


def cmd_solve(args):
    slope = args.slope
    factor = args.target_gain / args.base_gain / slope if slope else float("nan")
    print("factor ≈ %.3f   (target_gain %.3f / base %.3f / slope %.3f)" % (factor, args.target_gain, args.base_gain, slope))


def main(argv=None):
    p = argparse.ArgumentParser(prog="look_loop")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure")
    m.add_argument("--raw", required=True)
    m.add_argument("--jpeg", nargs="+", required=True)
    m.add_argument("--step", type=int, default=2)
    m.add_argument("--json")
    m.set_defaults(func=cmd_measure)

    pr = sub.add_parser("pairs")
    pr.add_argument("--pair", nargs="+", action="extend", required=True, help="LABEL=RAW,JPEG")
    pr.add_argument("--step", type=int, default=2)
    pr.add_argument("--json")
    pr.set_defaults(func=cmd_pairs)

    s = sub.add_parser("simulate")
    s.add_argument("--jpeg", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--param", nargs="+", required=True)
    s.add_argument("--step", type=int, default=4)
    s.set_defaults(func=cmd_simulate)

    c = sub.add_parser("solve")
    c.add_argument("--base-gain", type=float, required=True)
    c.add_argument("--slope", type=float, required=True)
    c.add_argument("--target-gain", type=float, required=True)
    c.set_defaults(func=cmd_solve)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())



