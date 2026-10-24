# -*- coding: utf-8 -*-
"""Build the explicit-write payload for the camera with zig cc (no camera needed)."""
from __future__ import annotations
import hashlib, json, os, pathlib, subprocess, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZIG = ROOT / ".venv/Lib/site-packages/ziglang/zig.exe"
SOURCE = ROOT / "native/flash_write.c"
OUT = ROOT / "native/flash_write.elf"
MANIFEST = ROOT / "native/flash_manifest.json"
TARGET = "aarch64-freestanding"
CACHE = ROOT / ".data/zig-cache"
ENV = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(CACHE / "global"), ZIG_LOCAL_CACHE_DIR=str(CACHE / "local"))


def build() -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="a6700-flash-build-") as temp:
        obj = pathlib.Path(temp) / "flash_write.o"
        subprocess.run([str(ZIG), "cc", "-target", TARGET, "-fPIC", "-O2", "-ffreestanding",
                        "-fno-builtin", "-fno-stack-protector", "-c", str(SOURCE), "-o", str(obj)],
                       check=True, env=ENV)
        subprocess.run([str(ZIG), "ld.lld", "-shared", "-Bsymbolic", "-z", "noexecstack",
                        "-o", str(OUT), str(obj)], check=True, env=ENV)
    data = OUT.read_bytes()
    if data[:4] != b"\x7fELF":
        raise SystemExit("built payload is not an ELF")
    manifest = dict(payload="flash_write.elf", sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data), source="flash_write.c",
                    compiler="zig 0.13.0 (aarch64-freestanding + ld.lld)",
                    mode="write-capable: pwrite64 path, refuses targets outside /usr/ and /cp/, "
                         "fsync + read-back verify, remounts read-only afterwards")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
