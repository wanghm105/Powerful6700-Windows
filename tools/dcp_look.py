"""从 A7C2 的 DCP 里提取「外观色彩变换」的逐色相行为。

DCP 的 ProfileHueSatMap（这里 dims 90x30x1）与 ProfileLookTable（72x12x16）是 Adobe
在 PCS 线性 RGB 的 HSV 上做的 ({hueShift, satScale, valScale}) 三元组修正。
本工具按 Adobe 语义把它们作用到合成色上，输出逐色相的饱和度乘子与色相旋转目标值。
"""
from __future__ import annotations
import argparse, struct
from pathlib import Path
import numpy as np

TYPE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
FMT = {1: "B", 3: "H", 4: "I", 5: "II", 9: "i", 10: "ii", 11: "f"}


def read_dcp(path):
    data = Path(path).read_bytes()
    if data[:2] != b"II":
        raise SystemExit("只支持小端 DCP")
    ifd = struct.unpack("<I", data[4:8])[0]
    n = struct.unpack("<H", data[ifd:ifd + 2])[0]
    tags = {}
    for i in range(n):
        e = ifd + 2 + i * 12
        tag, typ, cnt = struct.unpack("<HHI", data[e:e + 8])
        size = TYPE[typ] * cnt
        if size <= 4:
            payload = data[e + 8:e + 8 + size]
        else:
            off = struct.unpack("<I", data[e + 8:e + 12])[0]
            payload = data[off:off + size]
        tags[tag] = (typ, cnt, payload)
    return tags


def float_triplets(tags, dims_tag, data_tag):
    dims = struct.unpack("<3I", tags[dims_tag][2])
    vals = np.frombuffer(tags[data_tag][2], dtype="<f4").astype(np.float64).reshape(-1, 3)
    expect = int(np.prod(dims))
    if vals.shape[0] != expect:
        raise SystemExit("表长度 %d 与 dims %s 不符" % (vals.shape[0], dims))
    return dims, vals.reshape(dims[2], dims[1], dims[0], 3)  # (v, s, h, 3)


def lut_sample(table, dims, h, s, v):
    nh, ns, nv = dims
    xh, xs, xv = h * nh, s * ns, v * nv
    ih = np.clip(xh.astype(int), 0, nh - 1)
    fh = xh - ih
    ih1 = (ih + 1) % nh
    is_ = np.clip(xs.astype(int), 0, ns - 1)
    fs = xs - is_
    is1 = np.minimum(is_ + 1, ns - 1)
    iv = np.clip(xv.astype(int), 0, nv - 1)
    fv = xv - iv
    iv1 = np.minimum(iv + 1, nv - 1)
    out = np.zeros((h.size, 3))
    for dv, wv in ((iv, 1 - fv), (iv1, fv)):
        for ds, ws in ((is_, 1 - fs), (is1, fs)):
            for dh, wh in ((ih, 1 - fh), (ih1, fh)):
                out += table[dv, ds, dh] * (wv * ws * wh)[:, None]
    return out


def rgb_to_hsv_linear(rgb):
    mx = rgb.max(1); mn = rgb.min(1)
    v = mx
    s = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    d = np.maximum(mx - mn, 1e-12)
    h = np.zeros_like(v)
    m = (mx == r); h[m] = ((g[m] - b[m]) / d[m]) % 6
    m = (mx == g) & (mx != r); h[m] = (b[m] - r[m]) / d[m] + 2
    m = (mx == b) & (mx != r) & (mx != g); h[m] = (r[m] - g[m]) / d[m] + 4
    return (h / 6.0) % 1.0, s, v


def hsv_to_rgb_linear(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
    out = np.zeros((h.size, 3))
    for k, (rr, gg, bb) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[m] = np.stack([rr[m], gg[m], bb[m]], 1)
    return out


def apply_dcp_look(rgb, hsm, look):
    dh, hsm_t = hsm
    dl, look_t = look
    h, s, v = rgb_to_hsv_linear(rgb)
    for (dims, table) in ((dh, hsm_t), (dl, look_t)):
        d = lut_sample(table, dims, h, s, np.zeros_like(v))
        h = (h + d[:, 0]) % 1.0
        s = np.clip(s * d[:, 1], 0, 1)
        v = v * d[:, 2]
    return hsv_to_rgb_linear(h, s, v)


W = np.array([0.2126, 0.7152, 0.0722])


def opp(rgb):
    y = (rgb * W).sum(1)
    return y, rgb[:, 2] - y, rgb[:, 0] - y


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dcp", nargs="+", required=True, help="一个或多个 DCP")
    p.add_argument("--s", type=float, default=0.35)
    p.add_argument("--v", type=float, default=0.5)
    p.add_argument("--json")
    a = p.parse_args(argv)
    import json
    hues = np.arange(0, 360, 15)
    print("%-22s %s" % ("色相", " ".join("%6d" % x for x in hues)))
    result = {}
    for path in a.dcp:
        name = Path(path).stem.replace("Sony_ILCE-7CM2_", "")
        tags = read_dcp(path)
        hsm = float_triplets(tags, 0xc6f9, 0xc6fa)
        look = float_triplets(tags, 0xc725, 0xc726)
        src = hsv_to_rgb_linear((hues / 360.0), np.full(hues.size, a.s), np.full(hues.size, a.v))
        out = apply_dcp_look(src, hsm, look)
        y0, cb0, cr0 = opp(src)
        y1, cb1, cr1 = opp(out)
        m0 = np.hypot(cb0, cr0); m1 = np.hypot(cb1, cr1)
        ratio = m1 / np.maximum(m0, 1e-9)
        rot = ((np.degrees(np.arctan2(cr1, cb1)) - np.degrees(np.arctan2(cr0, cb0)) + 180) % 360) - 180
        print("%-22s %s" % (name[:22] + " 比", " ".join("%6.2f" % x for x in ratio)))
        print("%-22s %s" % (name[:22] + " 转", " ".join("%6.1f" % x for x in rot)))
        result[name] = {"ratio": ratio.round(3).tolist(), "rot": rot.round(1).tolist()}
    if a.json:
        Path(a.json).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写", a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
