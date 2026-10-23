"""直接从 PyPI 下载 wheel 到 wheelhouse/。

本机 pip 走阿里云镜像时会长时间挂住（换 pypi.org 索引也会卡在建索引阶段），
而直接对 files.pythonhosted.org 取文件是秒级的，因此依赖准备走这条路：
先取 wheel，再 pip install --no-index --find-links wheelhouse。

用法：
    python tools/fetch_wheels.py pyinstaller==6.16.0 altgraph pefile
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

WHEELHOUSE = Path(__file__).resolve().parent.parent / "wheelhouse"
JSON_URL = "https://pypi.org/pypi/%s/json"
JSON_VERSION_URL = "https://pypi.org/pypi/%s/%s/json"


def _rank(filename: str) -> int:
    """越小越优先：本机 cp312 win_amd64 > 纯 Python > 其他平台。"""
    name = filename.lower()
    if not name.endswith(".whl"):
        return 9
    if "cp312-cp312-win_amd64" in name:
        return 0
    if "py3-none-any" in name or "py2.py3-none-any" in name:
        return 1
    if "none-win_amd64" in name or "none-any" in name:
        return 2
    return 8


def resolve(spec: str) -> tuple[str, dict]:
    project, _, version = spec.partition("==")
    url = JSON_VERSION_URL % (project, version) if version else JSON_URL % project
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    candidates = sorted(payload["urls"], key=lambda item: _rank(item["filename"]))
    for item in candidates:
        if _rank(item["filename"]) < 9:
            return project, item
    raise SystemExit("no wheel for %s (packagetype=%s)" % (spec, [u["packagetype"] for u in payload["urls"]]))


def download(item: dict) -> Path:
    WHEELHOUSE.mkdir(parents=True, exist_ok=True)
    destination = WHEELHOUSE / item["filename"]
    if destination.exists() and destination.stat().st_size == item["size"]:
        print("cached     %s" % destination.name)
        return destination
    started = time.time()
    with urllib.request.urlopen(item["url"], timeout=180) as source, open(destination, "wb") as handle:
        while True:
            chunk = source.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
    print("downloaded %s %.1f MB in %.1fs" % (destination.name, item["size"] / 1e6, time.time() - started))
    return destination


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for spec in argv:
        project, item = resolve(spec)
        print("%-28s %s" % (project, item["filename"]))
        download(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
