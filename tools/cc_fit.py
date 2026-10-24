"""把 .cube 拟合成 CP CC1 的 6 系数矩阵（1024 对角基准、行和守恒）。

用法：
    python tools/cc_fit.py ../firmware/lut/Fuji_CC.cube [--strength 1.0] [--json out.json]

拟合在亮度归一化空间里做：每个采样点 x 与其亮度 Yx 相除，得到同亮度的色度方向；
目标 y 同样处理。四参数各自独立最小二乘，随后按 strength 与单位阵插值。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

W = np.array([0.2126, 0.7152, 0.0722])


def load_cube(path):
    size = None
    values = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.upper().startswith("LUT_3D_SIZE"):
            size = int(s.split()[-1])
            continue
        if s.upper().startswith(("TITLE", "DOMAIN_MIN", "DOMAIN_MAX", "LUT_3D_INPUT")):
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
    return np.stack([r, g, b], axis=-1)  # (size,size,size,3) 顺序 r,g,b


def fit(x, y):
    Yx = x @ W
    Yy = y @ W
    mask = np.isfinite(Yx) & np.isfinite(Yy) & (Yx > 0.15)
    x = x[mask]
    y = y[mask]
    Yx = Yx[mask]
    Yy = Yy[mask]
    if len(x) < 64:
        raise SystemExit("可用采样点太少，无法拟合")
    xn = x / Yx[:, None]
    yn = y / Yy[:, None]
    R, G, B = xn[:, 0], xn[:, 1], xn[:, 2]
    tr = 1024.0 * (yn[:, 0] - xn[:, 0])
    tg = 1024.0 * (yn[:, 1] - xn[:, 1])
    tb = 1024.0 * (yn[:, 2] - xn[:, 2])
    a, b = np.linalg.lstsq(np.stack([G - R, B - R], 1), tr, rcond=None)[0]
    c, d = np.linalg.lstsq(np.stack([G - R, G - B], 1), tg, rcond=None)[0]
    e, f = np.linalg.lstsq(np.stack([B - R, B - G], 1), tb, rcond=None)[0]
    pred = xn @ matrix(a, b, c, d, e, f).T / 1024.0
    err = float(np.abs(pred - yn).mean())
    return (float(a), float(b), float(c), float(d), float(e), float(f)), err, int(len(x))


def matrix(a, b, c, d, e, f):
    return np.array(
        [
            [a + b + 1024.0, -a, -b],
            [-c, c + d + 1024.0, -d],
            [-e, -f, e + f + 1024.0],
        ]
    )


def neutral_check(params):
    """灰阶是否仍为灰：矩阵行和相等时白点不动，这里用数值确认。"""
    M = matrix(*params)
    grey = np.array([0.5, 0.5, 0.5])
    out = M @ grey / 1024.0
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=".cube → CC1 6 系数")
    parser.add_argument("cube")
    parser.add_argument("--strength", type=float, default=1.0, help="与单位阵插值，1=完全套用拟合结果")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    size, table = load_cube(args.cube)
    x = grid(size).reshape(-1, 3)
    y = table.reshape(-1, 3)
    params, err, used = fit(x, y)
    s = args.strength
    params = tuple(p * s for p in params)
    M = matrix(*params)
    grey = neutral_check(params)
    print(f"{Path(args.cube).name}: size={size} 采样点={used} 平均色度误差={err:.4f} strength={s}")
    print("参数 a,b,c,d,e,f =", [round(p) for p in params])
    print("矩阵：")
    for row in M:
        print("  ", [round(v) for v in row], "行和", round(row.sum()))
    print("灰色 (0.5,0.5,0.5) 输出 =", [round(float(v), 4) for v in grey])

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "cube": str(args.cube),
                    "size": size,
                    "strength": s,
                    "params": [round(p) for p in params],
                    "matrix": [[round(float(v)) for v in row] for row in M],
                    "mean_chroma_error": err,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("已写入", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
