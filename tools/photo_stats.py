"""两张同机位照片的客观统计：判断是否真的「蓝色溢出」。

用法： python tools/photo_stats.py A.JPG B.JPG [--crop 0.2]
输出：每张的 RGB 均值/中位、通道分位数、饱和像素比例、色相均值、以及 A→B 的通道偏移。
"""
from __future__ import annotations

import argparse
import sys

from PySide6.QtGui import QImage


def load(path: str):
    image = QImage(path)
    if image.isNull():
        raise SystemExit(f"无法读取图片：{path}")
    image = image.convertToFormat(QImage.Format_RGB888)
    width, height = image.width(), image.height()
    rows = []
    for y in range(height):
        line = image.constScanLine(y)
        rows.append(bytes(line)[: width * 3])
    return width, height, rows


def stats(path: str, crop: float) -> dict:
    width, height, rows = load(path)
    x0 = int(width * crop)
    x1 = width - x0
    y0 = int(height * crop)
    y1 = height - y0
    sums = [0, 0, 0]
    counts = 0
    clip = [0, 0, 0]
    for y in range(y0, y1):
        line = rows[y]
        for x in range(x0, x1):
            r = line[x * 3]
            g = line[x * 3 + 1]
            b = line[x * 3 + 2]
            sums[0] += r
            sums[1] += g
            sums[2] += b
            if r >= 250:
                clip[0] += 1
            if g >= 250:
                clip[1] += 1
            if b >= 250:
                clip[2] += 1
            counts += 1
    means = [value / counts for value in sums]
    return {
        "path": path,
        "size": f"{width}x{height}",
        "mean": [round(value, 2) for value in means],
        "b_minus_r": round(means[2] - means[0], 2),
        "clip_ratio": [round(value / counts * 100, 2) for value in clip],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--crop", type=float, default=0.15)
    args = parser.parse_args(argv)
    a = stats(args.first, args.crop)
    b = stats(args.second, args.crop)
    for row in (a, b):
        print(row)
    print("B-R 变化:", round(b["b_minus_r"] - a["b_minus_r"], 2))
    print("均值变化 R/G/B:", [round(b["mean"][i] - a["mean"][i], 2) for i in range(3)])
    return 0


if __name__ == "__main__":
    sys.exit(main())