"""对一组相机路径做 stat + 头部探测（只读，不写入）。

用法：python tools/probe_path.py /usr/share /usr/share/app /usr/lib/appFw.so
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from a6700win import dump  # noqa: E402
from a6700win.research import ResearchError, ServiceSession  # noqa: E402


def main(argv=None):
    paths = list(argv or sys.argv[1:])
    if not paths:
        paths = ["/", "/usr", "/usr/lib", "/usr/share", "/usr/share/app", "/usr/lib/appFw.so"]

    def progress(message):
        print(message, flush=True)

    with ServiceSession(progress=progress) as session:
        for path in paths:
            try:
                size = session.stat(path)
                head = ""
                if size and size < (1 << 20):
                    try:
                        data = session.read_range(path, 0, min(16, size))["data"]
                        head = data.hex(" ")
                    except (dump.DumpError, ResearchError) as exc:
                        head = f"<读取失败 {exc}>"
                print(f"OK   {path}  size={size:,}  {head}", flush=True)
            except (dump.DumpError, ResearchError) as exc:
                print(f"FAIL {path}  {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
