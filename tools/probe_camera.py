"""只读探针：认证一次，列出相机上候选路径的存在性与大小，再读几个小文件。

不写相机：只做 Jiritsu select/read 与只读载荷的 stat/read。
用法：python tools/probe_camera.py [--read /proc/mounts]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from a6700win import dump  # noqa: E402
from a6700win.research import ResearchError, ServiceSession  # noqa: E402

CANDIDATES = [
    "/usr/lib/appFw.so",
    "/dev/nflasha15",
    "/dev/nflasha5",
    "/dev/nflasha8",
    "/proc/mounts",
    "/etc/version",
    "/tmp/jiritsu/tmmc.jit",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A6700 只读探针（不写相机）")
    parser.add_argument("--read", action="append", default=[], metavar="PATH",
                        help="额外完整读取的文件（默认只读大小）")
    parser.add_argument("--bytes", type=int, default=4096, help="完整读取时的最大字节数")
    args = parser.parse_args(argv)

    with ServiceSession(progress=lambda message: print(message, flush=True)) as session:
        print("连接成功，开始只读探测。", flush=True)
        for path in CANDIDATES:
            try:
                size = session.stat(path)
                print(f"  stat {path} -> {size:,} 字节", flush=True)
            except dump.DumpError as exc:
                print(f"  stat {path} -> 失败：{exc}", flush=True)
        print("--- Jiritsu 文件命令（A7C2 同款：cmd 15 选中 + cmd 17 整读）", flush=True)
        for path in ("/etc/version", "/proc/mounts"):
            try:
                data = dump.camera_file(session.channel, path, missing=True)
            except dump.DumpError as exc:
                print(f"  jiritsu {path} -> 失败：{exc}", flush=True)
                continue
            if data is None:
                print(f"  jiritsu {path} -> 不存在", flush=True)
            else:
                print(f"  jiritsu {path} -> {len(data)} 字节", flush=True)
                print(data[:512].decode("utf-8", "replace"), flush=True)

        for path in args.read:
            try:
                data = session.read_range(path, 0, args.bytes)["data"]
            except dump.DumpError as exc:
                print(f"  read {path} -> 失败：{exc}", flush=True)
                continue
            print(f"  read {path} -> {len(data)} 字节", flush=True)
            text = data[:2048].decode("utf-8", "replace")
            print(text, flush=True)
    print("服务模式退出状态见下方。", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ResearchError as exc:
        print(f"失败：{exc}", flush=True)
        raise SystemExit(1)

