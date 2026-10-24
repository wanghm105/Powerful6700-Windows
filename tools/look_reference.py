"""用 A7C2 的 .a7look 编译表算出目标外观的渲染，跟机身实拍对比逐色相响应。

表结构见 refs/a7c2-fl23/src/looks/looktool/native.py：405 节点 x 3 通道有符号 7bit 修正，
坐标 = BT.601 limited YCbCr，三线性插值，delta/256 加到源色上。
"""
from __future__ import annotations
import argparse
import base64
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from look_loop import jpeg_rgb  # noqa: E402

KR, KB = 0.299, 0.114
KG = 1 - KR - KB
MAT = np.array([[KR, KG, KB],
                [-KR / (2 * (1 - KB)), -KG / (2 * (1 - KB)), 0.5],
                [0.5, -KG / (2 * (1 - KR)), -KB / (2 * (1 - KR))]])


def decode_table(doc):
    raw = base64.b64decode(doc["table_base64"], validate=True)
    if len(raw) != 1215:
        raise SystemExit("table bytes %d != 1215" % len(raw))
    return np.frombuffer(raw, dtype="i1").reshape(3, 405).T.astype(float)


def coordinates(flat):
    return (flat @ MAT.T - np.array([16 / 255, 0.0, 0.0])) * 255 / np.array([219.0, 224.0, 224.0])


def apply_look(rgb, coeff, response=None):
    resp = np.eye(3) if response is None else np.asarray(response, float)
    flat = rgb.reshape(-1, 3).astype(float)
    c = coordinates(flat)
    at = np.clip(c * [4, 8, 8] + [0, 4, 4], [0, 0, 0], [4, 8, 8])
    lo = np.minimum(at.astype(int), [3, 7, 7])
    f = at - lo
    acc = np.zeros((flat.shape[0], 3))
    for dy in (0, 1):
        for d1 in (0, 1):
            for d2 in (0, 1):
                ids = (lo[:, 0] + dy) * 81 + (lo[:, 1] + d1) * 9 + lo[:, 2] + d2
                w = (f[:, 0] if dy else 1 - f[:, 0])
                w = w * (f[:, 1] if d1 else 1 - f[:, 1])
                w = w * (f[:, 2] if d2 else 1 - f[:, 2])
                acc += coeff[ids] * w[:, None]
    out = np.clip(flat + (acc / 256.0) @ resp, 0, 1)
    return out.reshape(rgb.shape)


def save_png(arr, path):
    from PySide6.QtGui import QImage
    u8 = np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)
    h, w, _ = u8.shape
    img = QImage(u8.tobytes(), w, h, w * 3, QImage.Format_RGB888)
    if not img.save(str(path)):
        raise SystemExit("保存失败 %s" % path)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--look", required=True)
    p.add_argument("--base", required=True, help="机身的 ST 样张（sRGB JPEG）")
    p.add_argument("--out", required=True, help="参考渲染输出 PNG")
    p.add_argument("--step", type=int, default=2)
    a = p.parse_args(argv)
    doc = json.loads(Path(a.look).read_text(encoding="utf-8-sig"))
    coeff = decode_table(doc)
    print("外观: %s | 基: %s | 方法: %s" % (doc.get("name"), doc.get("base"), doc.get("method")))
    base = jpeg_rgb(a.base, a.step)
    out = apply_look(base, coeff)
    save_png(out, a.out)
    print("参考渲染已存 %s (%dx%d)" % (a.out, out.shape[1], out.shape[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
