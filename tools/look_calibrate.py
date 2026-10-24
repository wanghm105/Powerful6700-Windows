"""外观参数标定：把「我们写的参数（缩放系数 / 蓝基座 tint）」和「实测画面变化」拟合成直线。

一次标定需要至少两个已知参数点，每点：标签 缩放系数 蓝基座tint JPEG路径

用法：
    python tools/look_calibrate.py --raw photo/WHM00023.ARW ^
        --point PT 1.00 1.00 photo/WHM00023.JPG ^
        --point CC 0.62 1.15 photo/WHM00024.JPG ^
        --point NC 0.50 1.00 photo/WHM00026.JPG

第一个 --point 作为基准外观；其余点给出相对增益比与冷暖差。
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from look_loop import jpeg_rgb, linear_scene, fit_grid, measure_pair, srgb2lin  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True)
    p.add_argument("--point", nargs=4, action="append", required=True,
                   metavar=("LABEL", "FACTOR", "TINT", "JPEG"))
    p.add_argument("--step", type=int, default=2)
    args = p.parse_args(argv)

    scene = linear_scene(args.raw)
    rows = []
    for label, f, t, path in args.point:
        j = jpeg_rgb(path, args.step)
        s = fit_grid(scene, (j.shape[0], j.shape[1]))
        r = measure_pair(s, srgb2lin(j))
        rows.append(dict(label=label, factor=float(f), tint=float(t), **r))
        print("%-6s factor %.3f tint %.2f -> gain %.4f  warmth %+.5f" %
              (label, float(f), float(t), r["gain"], r["warmth"]))

    base = rows[0]
    print("")
    print("相对基准 %s:" % base["label"])
    for r in rows[1:]:
        ratio = r["gain"] / base["gain"]
        print("  %-6s ratio %.4f  每单位系数 %.4f  dWarmth %+.5f   tint %.2f" %
              (r["label"], ratio, ratio / r["factor"], r["warmth"] - base["warmth"], r["tint"]))

    same_tint = [r for r in rows if abs(r["tint"] - 1.0) < 1e-6]
    if len(same_tint) >= 2:
        x = np.array([r["factor"] for r in same_tint])
        y = np.array([r["gain"] for r in same_tint])
        a, b = np.polyfit(x, y, 1)
        print("")
        print("拟合(tint=1): gain = %.4f * factor + %.4f" % (a, b))
        print("反解: factor = (target_gain - %.4f) / %.4f" % (b, a))
    else:
        print("")
        print("(tint=1 的点不足 2 个, 暂不拟合 factor)")

    wide = [r for r in rows if abs(r["factor"] - 1.0) < 1e-6]
    if len(wide) >= 2:
        x = np.array([r["tint"] for r in wide])
        y = np.array([r["warmth"] for r in wide])
        c, d = np.polyfit(x, y, 1)
        print("拟合(factor=1): warmth = %+.5f * tint %+.5f" % (c, d))
        if abs(c) > 1e-7:
            print("反解: tint = (target_warmth %+.5f) / %+.5f" % (-d, c))
    else:
        print("(factor=1 的点不足 2 个, 暂不拟合 tint)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

