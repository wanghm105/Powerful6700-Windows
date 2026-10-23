# -*- coding: utf-8 -*-
"""Build the read-only range payload for the camera with zig cc (no camera needed)."""
from __future__ import annotations
import hashlib, json, os, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZIG = ROOT / ".venv/Lib/site-packages/ziglang/zig.exe"
SOURCE = ROOT / "native/dump_range.c"
OUT = ROOT / "native/dump_range.elf"
MANIFEST = ROOT / "native/dump_manifest.json"
TARGET = "aarch64-freestanding"
CACHE = ROOT / ".data/zig-cache"
ENV = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(CACHE / "global"), ZIG_LOCAL_CACHE_DIR=str(CACHE / "local"))

def build() -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="a6700-dump-build-") as temp:
        obj = pathlib.Path(temp) / "dump_range.o"
        subprocess.run([str(ZIG), "cc", "-target", TARGET, "-fPIC", "-O2", "-ffreestanding",
                        "-fno-builtin", "-fno-stack-protector", "-c", str(SOURCE), "-o", str(obj)],
                       check=True, env=ENV)
        subprocess.run([str(ZIG), "ld.lld", "-shared", "-Bsymbolic", "-z", "noexecstack",
                        "-o", str(OUT), str(obj)], check=True, env=ENV)
    data = OUT.read_bytes()
    if data[:4] != b"\x7fELF":
        raise SystemExit("built payload is not an ELF")
    manifest = dict(payload="dump_range.elf", sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data), source="dump_range.c",
                    compiler="zig 0.13.0 (aarch64-freestanding + ld.lld)",
                    mode="read-only: opens O_RDONLY, no pwrite64 path")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
