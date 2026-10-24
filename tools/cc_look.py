"""从 .cube 估计「整体去饱和系数 k」与「平均色相旋转 theta」，
再在 YCbCr 空间合成一个 1024 基准、行和守恒的 3x3 矩阵（= CP CC1 的 6 个系数）。

用法：
    python tools/cc_look.py ../firmware/lut/Fuji_CC.cube [--json out.json] [--sat 1.0] [--rot 1.0]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

W = np.array([0.2126, 0.7152, 0.0722])
A = np.array(
    [
        [0.2126, 0.7152, 0.0722],
        [-0.1146, -0.3854, 0.5000],
        [0.5000, -0.4542, -0.0458],
    ]
)
A_INV = np.linalg.inv(A)


def load_cube(path):
    size = None
    values = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        head = s.split()[0].upper()
        if head == "LUT_3D_SIZE":
            size = int(s.split()[-1])
            continue
        if head in {"TITLE", "DOMAIN_MIN", "DOMAIN_MAX", "LUT_3D_INPUT_RANGE"}:
            continue
        parts = s.split()
        if len(parts) == 3:
            try:
                values.append([float(v) for v in parts])
            except ValueError:
                continue
    if size is None:
        raise SystemExit(f"{path} 里没有 LUT_3D_SIZE")
    table = np.array(values, dtype=np.float64)
    if table.shape[0] != size ** 3:
        raise SystemExit(f"{path} 行数 {table.shape[0]} 与 {size}^3 不符")
    return size, table.reshape(size, size, size, 3)


def grid(size):
    axis = np.linspace(0.0, 1.0, size)
    b, g, r = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.stack([r, g, b], axis=-1).reshape(-1, 3)


def measure(x, y):
    Yx = x @ W
    mask = (Yx > 0.12) & (Yx < 0.88)
    x = x[mask]
    y = y[mask]
    cx = x @ A[1:].T
    cy = y @ A[1:].T
    rx = np.hypot(cx[:, 0], cx[:, 1])
    ry = np.hypot(cy[:, 0], cy[:, 1])
    good = rx > 0.02
    k = ry[good] / rx[good]
    ang = np.degrees(np.arctan2(cy[good, 1], cy[good, 0]) - np.arctan2(cx[good, 0], cx[good, 1]))
    ang = (ang + 180.0) % 360.0 - 180.0
    return float(np.median(k)), float(np.median(ang)), k, ang


def synthesize(k, theta_deg):
    t = math.radians(theta_deg)
    chroma = k * np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    ycc = np.zeros((3, 3))
    ycc[0, 0] = 1.0
    ycc[1:, 1:] = chroma
    m = A_INV @ ycc @ A
    return m * 1024.0


def to_params(m):
    a = -m[0, 1]
    b = -m[0, 2]
    c = -m[1, 0]
    d = -m[1, 2]
    e = -m[2, 0]
    f = -m[2, 1]
    return [a, b, c, d, e, f]


def main(argv=None):
    parser = argparse.ArgumentParser(description=".cube → 整体去饱和/色相旋转 → CC1 6 系数")
    parser.add_argument("cube")
    parser.add_argument("--sat", type=float, default=1.0, help="叠加到测得 k 上的倍率")
    parser.add_argument("--rot", type=float, default=1.0, help="叠加到测得 theta 上的倍率")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    size, table = load_cube(args.cube)
    x = grid(size)
    y = table.reshape(-1, 3)
    k, theta, kk, aa = measure(x, y)
    k_used = k * args.sat
    theta_used = theta * args.rot
    m = synthesize(k_used, theta_used)
    params = to_params(m)
    print(f"{Path(args.cube).name}: size={size}")
    print(f"  测得的整体去饱和 k = {k:.3f}（四分位 {np.percentile(kk,25):.3f} / {np.percentile(kk,75):.3f}）")
    print(f"  测得的平均色相旋转 theta = {theta:+.1f}°（四分位 {np.percentile(aa,25):+.1f} / {np.percentile(aa,75):+.1f}）")
    print(f"  采用 k={k_used:.3f} theta={theta_used:+.1f}°")
    print("  矩阵：")
    for row in m:
        print("   ", [round(v) for v in row], "行和", round(row.sum()))
    print("  参数 (取整) =", [round(p) for p in params])
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "cube": str(args.cube),
                    "size": size,
                    "k": k,
                    "k_used": k_used,
                    "theta": theta,
                    "theta_used": theta_used,
                    "params": [round(p) for p in params],
                    "matrix": [[round(float(v)) for v in row] for row in m],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("  已写入", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
