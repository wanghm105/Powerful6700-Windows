"""FAT12 / FAT16 只读解析：用于 A6700 的 nflasha 分区镜像。

最早只为 nflasha2 写死过几何（bps=512 / spc=32 / fatsz16=4 / rootent=512），后来要在其它
分区（nflasha1/3/7/10/11/12/13/18）上找设置文件，改成从 BPB 读几何，FAT12 与 FAT16 都支持。

用法：
    python tools/nflasha2.py --list ../firmware/parts/nflasha2-def.bin
    python tools/nflasha2.py --extract ../firmware/parts/nflasha2-def.bin --out ../firmware/psd
    python tools/nflasha2.py --get BACKUP.BIN ../firmware/parts/nflasha2-def.bin --out ../firmware/psd

只读工具：不会修改镜像。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


class Fat12:
    """通用 FAT12 / FAT16 只读解析。"""

    def __init__(self, image: bytes) -> None:
        self.image = image
        self.bps = struct.unpack_from("<H", image, 11)[0]
        self.spc = image[13]
        self.rsvd = struct.unpack_from("<H", image, 14)[0]
        self.nfats = image[16]
        self.rootent = struct.unpack_from("<H", image, 17)[0]
        fatsz16 = struct.unpack_from("<H", image, 22)[0]
        fatsz32 = struct.unpack_from("<I", image, 36)[0]
        self.fatsz = fatsz16 or fatsz32
        if not self.bps or not self.spc or not self.fatsz:
            raise ValueError("不是 FAT 卷（BPB 无效）")
        total16 = struct.unpack_from("<H", image, 19)[0]
        total32 = struct.unpack_from("<I", image, 32)[0]
        self.total = total16 or total32
        self.root_off = (self.rsvd + self.nfats * self.fatsz) * self.bps
        self.data_off = self.root_off + self.rootent * 32
        self.cluster_bytes = self.spc * self.bps
        fat_start = self.rsvd * self.bps
        self.fat = image[fat_start : fat_start + self.fatsz * self.bps]
        reserved_sectors = self.rsvd + self.nfats * self.fatsz + self.rootent * 32 // self.bps
        data_clusters = max(0, (self.total - reserved_sectors)) // self.spc
        self.fat16 = data_clusters >= 4085

    def next_cluster(self, cluster: int) -> int:
        if self.fat16:
            offset = cluster * 2
            if offset + 2 > len(self.fat):
                return 0xFFF8
            return struct.unpack_from("<H", self.fat, offset)[0]
        index = cluster * 3 // 2
        if index + 1 >= len(self.fat):
            return 0xFFF8
        value = self.fat[index] | (self.fat[index + 1] << 8)
        return (value >> 4) if cluster & 1 else (value & 0xFFF)

    def entries(self) -> list[dict]:
        rows: list[dict] = []
        long_name = ""
        for i in range(self.rootent):
            entry = self.image[self.root_off + i * 32 : self.root_off + (i + 1) * 32]
            if not entry or entry[0] == 0x00:
                break
            if entry[0] == 0xE5:
                long_name = ""
                continue
            attr = entry[11]
            if attr == 0x0F:
                chunk = entry[1:11] + entry[14:26] + entry[28:32]
                long_name = chunk.decode("utf-16-le", "replace").split(chr(0))[0] + long_name
                continue
            if attr & 0x08:
                long_name = ""
                continue
            name = entry[:8].decode("ascii", "replace").rstrip()
            ext = entry[8:11].decode("ascii", "replace").rstrip()
            cluster, size = struct.unpack_from("<HI", entry, 26)
            rows.append(
                {
                    "name": f"{name}.{ext}" if ext else name,
                    "long_name": long_name,
                    "cluster": cluster,
                    "size": size,
                    "attr": attr,
                }
            )
            long_name = ""
        return rows

    def read(self, cluster: int, size: int) -> bytes:
        out = bytearray()
        seen = 0
        while cluster and cluster < 0xFFF8 and seen < 200000:
            off = self.data_off + (cluster - 2) * self.cluster_bytes
            if off >= len(self.image):
                break
            out += self.image[off : off + self.cluster_bytes]
            cluster = self.next_cluster(cluster)
            seen += 1
        return bytes(out[:size])


def open_image(path: Path) -> Fat12:
    return Fat12(path.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读取 A6700 nflasha 分区（FAT12 / FAT16）镜像")
    parser.add_argument("image", nargs="?", type=Path, help="分区镜像")
    parser.add_argument("--image", dest="image_opt", type=Path, help="分区镜像（等价写法）")
    parser.add_argument("--list", action="store_true", help="列出文件")
    parser.add_argument("--extract", action="store_true", help="导出全部文件")
    parser.add_argument("--get", metavar="NAME", help="只导出指定文件")
    parser.add_argument("--out", type=Path, help="导出目录")
    args = parser.parse_args(argv)

    image = args.image_opt or args.image
    if image is None:
        parser.error("需要分区镜像路径")
    volume = open_image(image)
    rows = volume.entries()
    if args.list or not (args.extract or args.get):
        for row in rows:
            print(f"{row['name']:14s} {row['size']:>10d}  cluster={row['cluster']:5d}  {row['long_name']}")
        print(f"共 {len(rows)} 个文件 · {'FAT16' if volume.fat16 else 'FAT12'} · "
              f"{volume.bps}B/sector · {volume.spc} sectors/cluster · {volume.rootent} root entries")
        return 0

    if args.out is None:
        parser.error("导出需要 --out")
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    selected = rows if args.extract else [r for r in rows if r["name"] == args.get or r["long_name"] == args.get]
    if args.get and not selected:
        print(f"没有找到 {args.get}", file=sys.stderr)
        return 1
    for row in selected:
        data = volume.read(row["cluster"], row["size"])
        target = args.out / row["name"].replace("/", "_")
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        manifest[row["name"]] = {"size": len(data), "sha256": digest}
        print(f"{row['name']:14s} {len(data):>10d}  {digest[:16]}")
    if args.extract:
        (args.out / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
