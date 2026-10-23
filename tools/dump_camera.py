"""把机身文件只读 dump 到本机（可断点续传、逐块哈希、只读）。

用法：
  python tools/dump_camera.py --path /usr/lib/appFw.so --out firmware/appFw-2.00.so
  python tools/dump_camera.py --path /usr/lib/appFw.so --out out.so --bytes 65536   # 试读

安全边界：只用只读载荷（openat 标志恒为 0）与 Jiritsu 的 select/read，不向相机写任何数据。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from a6700win import dump  # noqa: E402
from a6700win.research import ResearchError, ServiceSession  # noqa: E402

RETRIES = 4


def _dump_once(session, path, out, chunk, size, progress):
    part = out.with_suffix(out.suffix + ".part")
    digest = hashlib.sha256()
    done = part.stat().st_size if part.exists() else 0
    if done:
        with part.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        progress(f"续传：已有 {done:,} 字节（{done / size:.1%}）")
    started = time.monotonic()
    with part.open("ab") as handle:
        while done < size:
            length = min(chunk, size - done)
            data = session.read_range(path, done, length)["data"]
            if not data:
                raise dump.DumpError(f"偏移 {done:,} 处读到 0 字节，已停止。")
            handle.write(data)
            digest.update(data)
            done += len(data)
            elapsed = max(1e-6, time.monotonic() - started)
            rate = done / elapsed
            blocks = done // chunk
            if blocks <= 3 or blocks % 16 == 0 or done == size:
                progress(
                    f"{done:,}/{size:,} 字节（{done / size:.1%}，{rate / 1024:.0f} KiB/s，"
                    f"已用 {elapsed:.0f}s，预计还需 {max(size - done, 0) / max(rate, 1):.0f}s）"
                )
        handle.flush()
    part.replace(out)
    side = out.with_suffix(out.suffix + ".json")
    side.write_text(json.dumps({
        "path": path,
        "output": str(out),
        "size": size,
        "bytes": out.stat().st_size,
        "sha256": digest.hexdigest(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, indent=2), "utf-8")
    progress(f"完成：{out} sha256={digest.hexdigest()}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="A6700 机身文件只读 dump")
    parser.add_argument("--path", required=True, help="相机上的绝对路径")
    parser.add_argument("--out", required=True, help="本机输出文件")
    parser.add_argument("--chunk", type=int, default=dump.CHUNK, help="每块字节数（默认 256 KiB）")
    parser.add_argument("--bytes", type=int, default=0, help="只读前 N 字节（试读用）")
    parser.add_argument("--offset", type=int, default=0, help="起始偏移")
    parser.add_argument("--fresh", action="store_true", help="忽略已有 .part，从头开始")
    parser.add_argument("--probe", action="store_true", help="只读前 4 KiB 并打印头 16 字节")
    args = parser.parse_args(argv)

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(out.suffix + ".part")
    if args.fresh and part.exists():
        part.unlink()

    def progress(message):
        print(message, flush=True)

    for attempt in range(1, RETRIES + 1):
        try:
            with ServiceSession(progress=progress) as session:
                size = session.stat(args.path)
                if args.bytes:
                    size = min(args.offset + args.bytes, size)
                progress(f"{args.path} -> {size:,} 字节；块 {args.chunk:,}")
                if args.probe:
                    head = session.read_range(args.path, 0, 4096)["data"]
                    progress(f"头 16 字节：{head[:16].hex(' ')}  可打印：{head[:16]!r}")
                    return 0
                _dump_once(session, args.path, out, args.chunk, size, progress)
            return 0
        except (dump.DumpError, ResearchError, OSError) as exc:
            progress(f"第 {attempt}/{RETRIES} 次中断：{exc}")
            if attempt == RETRIES:
                progress("重试用尽；已下载的部分保留在 .part 里，重跑同一命令会续传。")
                return 1
            time.sleep(2.0)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
