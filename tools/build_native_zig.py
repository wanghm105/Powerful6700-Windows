# -*- coding: utf-8 -*-
"""Rebuild A6700 transaction.c with zig cc and compare to the shipped payloads."""
import hashlib, json, os, subprocess, sys, tempfile, pathlib
ROOT = pathlib.Path(os.environ.get("POWERFUL6700_ROOT", pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "third_party"))
from a6700_unlock.catalog import load_catalog
from a6700_unlock.device_profile import load_device_profile
profile = load_device_profile(load_catalog())
rows = []
for row, mask in zip(profile.entries, profile.masks(writable_only=True)):
    rows.append("{%dUL,%d,{%s}}" % (row["device_offset"], row["device"], ",".join(str(v) for v in mask)))
header = ("struct Entry { unsigned long offset; unsigned char device; unsigned char mask[64]; };\n"
          f"#define ENTRY_COUNT {len(rows)}u\n"
          "static const unsigned char PROFILE_DIGEST[32]={" + ",".join(str(v) for v in bytes.fromhex(profile.digest)) + "};\n"
          "static const struct Entry ENTRIES[ENTRY_COUNT]={" + ",\n".join(rows) + "};\n")
src = ROOT / "third_party/a6700_unlock/native/transaction.c"
zig = ROOT / ".venv/Lib/site-packages/ziglang/zig.exe"
TARGET = "aarch64-linux-musl"
CACHE = ROOT / ".data" / "zig-cache"
CACHE.mkdir(parents=True, exist_ok=True)
ENV = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(CACHE / "global"), ZIG_LOCAL_CACHE_DIR=str(CACHE / "local"))
out = {}
with tempfile.TemporaryDirectory(prefix="zgbuild-") as t:
    work = pathlib.Path(t)
    (work / "profile.h").write_text(header)
    print("entries", len(rows), "header bytes", len(header))
    for name, mode in (("reader", 0), ("writer", 1)):
        obj = work / (name + ".o"); elf = work / (name + ".elf")
        cc = [str(zig), "cc", "-target", TARGET, "-fPIC", "-O2", "-ffreestanding", "-fno-builtin",
              "-fno-stack-protector", "-I", str(work), f"-DBUILD_WRITER={mode}", "-c", str(src), "-o", str(obj)]
        subprocess.run(cc, check=True, env=ENV)
        subprocess.run([str(zig), "cc", "-target", TARGET, "-nostdlib", "-shared", "-Bsymbolic",
                        "-z", "noexecstack", "-o", str(elf), str(obj)], check=True, env=ENV)
        data = elf.read_bytes()
        shipped = (ROOT / "third_party/a6700_unlock/data/native" / (name + ".elf")).read_bytes()
        out[name] = dict(built_len=len(data), built_sha=hashlib.sha256(data).hexdigest(),
                         shipped_len=len(shipped), shipped_sha=hashlib.sha256(shipped).hexdigest(),
                         identical=(data == shipped))
print(json.dumps(out, indent=2))
