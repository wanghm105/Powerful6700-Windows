
"""生成「结构守卫里哪些扇区其实是 ext2 inode 元数据」的覆盖表。

上游 device-profile 把固件版本钉得很死：结构守卫扇区按 sha256 全字节比对。
/usr 分区（nflasha15）上有几个守卫扇区正好落在 ext2 的 inode 表里，相机自己
读写文件时会把 atime/ctime/mtime 写进去，于是守卫每次开机都可能“不匹配”，
工具就停在 blocked。这里把这类扇区识别出来，并记下「抹掉 3 个时间戳字段之后」
的期望哈希，运行期只对这类扇区放行时间戳漂移，其余字节仍然逐字节校验。

用法：
    python tools/gen_guard_overlay.py --image ../firmware/parts/nflasha15-full.bin
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import a6700win.paths as paths  # noqa: E402

paths.ensure_vendor_on_path()

from a6700_unlock.catalog import load_catalog  # noqa: E402
from a6700_unlock.device_profile import load_device_profile  # noqa: E402

INODE_SIZE = 256
# ext2 inode 记录里会随时间变化、且与固件内容无关的字段：atime(8)、ctime(12)、mtime(16)。
VOLATILE = ((0x08, 0x14),)
VALID_MODES = {0x1000, 0x2000, 0x4000, 0x6000, 0x8000, 0xA000, 0xC000}


def normalize(sector: bytes) -> bytes:
    buf = bytearray(sector)
    for base in range(0, len(buf), INODE_SIZE):
        for start, end in VOLATILE:
            buf[base + start:base + end] = b"\0" * (end - start)
    return bytes(buf)


def inode_like(sector: bytes) -> bool:
    for base in range(0, len(sector), INODE_SIZE):
        mode, _uid, size = struct.unpack_from("<HHI", sector, base)
        links = struct.unpack_from("<H", sector, base + 0x1A)[0]
        if (mode & 0xF000) not in VALID_MODES or not mode & 0o777:
            return False
        if size >= 1 << 32 or links > 1024:
            return False
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成守卫 inode 豁免表")
    parser.add_argument("--image", required=True, help="nflasha15 全分区镜像")
    parser.add_argument("--out", default=str(ROOT / "src" / "a6700win" / "data" / "guard-overlay.json"))
    args = parser.parse_args(argv)

    profile = load_device_profile(load_catalog())
    image = Path(args.image)
    records = {}
    with image.open("rb") as fh:
        for row in profile.entries:
            if row["role"] != "guard" or row["device"] != 0:
                continue
            fh.seek(row["device_offset"])
            sector = fh.read(512)
            if len(sector) != 512:
                continue
            if hashlib.sha256(sector).hexdigest() != row["sha256"]:
                print(f"skip {row['index']}: 镜像里的扇区与 profile 不一致")
                continue
            if not inode_like(sector):
                continue
            records[str(row["index"])] = dict(
                device=row["device"],
                device_offset=row["device_offset"],
                normalized_sha256=hashlib.sha256(normalize(sector)).hexdigest(),
            )
    payload = dict(
        schema="a6700win/guard-overlay/1",
        description="结构守卫里落在 ext2 inode 表中的扇区；只放行 atime/ctime/mtime 漂移",
        inode_size=INODE_SIZE,
        volatile=[[start, end] for start, end in VOLATILE],
        records=records,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{out}: {len(records)} 个 inode 守卫扇区 {sorted(int(k) for k in records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
