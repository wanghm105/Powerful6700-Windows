"""在相机 /usr/share/app 下查找并导出菜单文字资源（.uxc），单次会话完成。

用法：
  python tools/ui_strings.py --scan
  python tools/ui_strings.py --get string_simplifiedchinese_vertical.uxc
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from a6700win import dump  # noqa: E402
from a6700win.research import ResearchError, ServiceSession  # noqa: E402

NAMES_JSON = ROOT / "refs" / "a7c2-fl23" / "src" / "looks" / "assets" / "resource-files.json"
OUT = ROOT / "firmware" / "ui"
MAGIC = b"uxc" + bytes([7, 0, 0, 0, 0])


def names():
    return json.loads(NAMES_JSON.read_text(encoding="utf-8"))


def decode(raw):
    if len(raw) < 16 or raw[:8] != MAGIC:
        raise ValueError("not UXC-v7: head=%s" % raw[:8].hex())
    kind, group, descriptor = struct.unpack_from("<HHI", raw, 8)
    count = descriptor & 0x1FFF
    base = (16 + count * 2 + 3) & ~3
    entries = {}
    for i in range(count):
        pointer = struct.unpack_from("<H", raw, 16 + 2 * i)[0]
        if pointer == 0xFFFF:
            continue
        at = base + pointer * 4
        rid = 0x02000000 | (group << 13) + i
        if at + 5 > len(raw):
            continue
        end = raw.find(bytes([0]), at + 4)
        entries[rid] = raw[at + 4:end]
    return dict(kind=kind, group=group, count=count, base=base, entries=entries)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--get", default="")
    parser.add_argument("--dir", default="/usr/share/app")
    args = parser.parse_args(argv)

    def progress(message):
        print(message, flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    found = {}
    with ServiceSession(progress=progress) as session:
        if args.scan:
            for name in names():
                path = args.dir + "/" + name
                try:
                    found[name] = session.stat(path)
                except Exception:
                    pass
            print("命中 %d/%d 个候选文件" % (len(found), len(names())), flush=True)
            for name, size in list(found.items())[:10]:
                print("  %9d  %s" % (size, name), flush=True)
            (OUT / "scan.json").write_text(json.dumps(found, indent=2), "utf-8")
        targets = []
        if args.get:
            targets = [args.get]
        elif found:
            want = ("string_simplifiedchinese_vertical.uxc",
                    "string_simplifiedchinese_horizontal.uxc",
                    "string_english_vertical.uxc")
            targets = [n for n in want if n in found][:2]
        for name in targets:
            path = args.dir + "/" + name
            size = found.get(name) or session.stat(path)
            data = b""
            offset = 0
            while offset < size:
                chunk = min(0x40000, size - offset)
                data += session.read_range(path, offset, chunk)["data"]
                offset += chunk
            target = OUT / name
            target.write_bytes(data)
            print("保存 %s %d 字节 sha256=%s" % (name, len(data), hashlib.sha256(data).hexdigest()), flush=True)
            try:
                parsed = decode(data)
                print("  UXC kind=%d group=%d count=%d data_base=%d 记录 %d 条"
                      % (parsed["kind"], parsed["group"], parsed["count"], parsed["base"], len(parsed["entries"])), flush=True)
                for rid in range(0x0200AB2C, 0x0200AB32):
                    print("    rid 0x%08x -> %r" % (rid, parsed["entries"].get(rid)), flush=True)
            except Exception as exc:
                print("  解码失败：%s" % exc, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
