"""在相机 ext2/ext4 卷上只读遍历目录、导出文件（不写入相机）。

用法：
  python tools/ext4_walk.py --device /dev/nflasha15 --list /usr/share/app
  python tools/ext4_walk.py --device /dev/nflasha15 --list / --depth 2
  python tools/ext4_walk.py --device /dev/nflasha15 --list /usr/share/app --grep string
  python tools/ext4_walk.py --device /dev/nflasha15 --get /usr/share/app/string_chinese_vertical.uxc --out ../firmware/ui
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from a6700win.research import ServiceSession  # noqa: E402

S_IFMT = 0o170000
S_IFDIR = 0o040000


class LocalImage:
    """把本机镜像文件包装成和 ServiceSession 一样的 read_range 接口。

    这样同一个 Ext2 解析器既能跑在真机上（服务模式读 /dev/nflashaXX），
    也能跑在已经 dump 下来的 firmware/parts/*.bin 上。
    """

    def __init__(self, path: Path) -> None:
        self.handle = path.open("rb")

    def read_range(self, _device, offset, length):
        self.handle.seek(offset)
        return {"data": self.handle.read(length)}


class Ext2:
    def __init__(self, session, device):
        self.session = session
        self.device = device
        raw = self.read(1024, 1024)
        self.u32 = lambda o: struct.unpack_from("<I", raw, o)[0]
        self.u16 = lambda o: struct.unpack_from("<H", raw, o)[0]
        self.inodes = self.u32(0)
        self.first_data_block = self.u32(20)
        self.block_size = 1024 << self.u32(24)
        self.blocks_per_group = self.u32(32)
        self.inodes_per_group = self.u32(40)
        self.inode_size = self.u16(88) or 128
        self.desc_size = 32
        self.gd_block = self.first_data_block + 1
        self._cache = {}

    # --- raw io ---------------------------------------------------------
    def read(self, offset, length):
        return self.session.read_range(self.device, offset, length)["data"]

    def block(self, number, count=1):
        key = (number, count)
        if key in self._cache:
            return self._cache[key]
        data = self.read(number * self.block_size, count * self.block_size)
        if len(data) < count * self.block_size:
            data = data + b"\0" * (count * self.block_size - len(data))
        self._cache[key] = data
        return data

    # --- inodes ---------------------------------------------------------
    def inode_table_block(self, ino):
        group = (ino - 1) // self.inodes_per_group
        desc = self.read(self.gd_block * self.block_size + group * self.desc_size, self.desc_size)
        return struct.unpack_from("<I", desc, 8)[0]

    def inode(self, ino):
        table = self.inode_table_block(ino)
        index = (ino - 1) % self.inodes_per_group
        raw = self.read(table * self.block_size + index * self.inode_size, self.inode_size)
        mode = struct.unpack_from("<H", raw, 0)[0]
        size = struct.unpack_from("<I", raw, 4)[0]
        blocks = struct.unpack_from("<15I", raw, 40)
        return dict(ino=ino, mode=mode, size=size, blocks=blocks)

    def data_blocks(self, node):
        base = self.block_size
        out = [b for b in node["blocks"][:12] if b]
        if node["blocks"][12]:
            for b in struct.unpack_from("<%dI" % (base // 4), self.block(node["blocks"][12])):
                if b:
                    out.append(b)
        if node["blocks"][13]:
            for mid in struct.unpack_from("<%dI" % (base // 4), self.block(node["blocks"][13])):
                if not mid:
                    continue
                for b in struct.unpack_from("<%dI" % (base // 4), self.block(mid)):
                    if b:
                        out.append(b)
        return out

    def read_file(self, node):
        remaining = node["size"]
        chunks = []
        for number in self.data_blocks(node):
            if remaining <= 0:
                break
            take = min(self.block_size, remaining)
            chunks.append(self.block(number)[:take])
            remaining -= take
        return b"".join(chunks)

    # --- directories ----------------------------------------------------
    def entries(self, node):
        data = self.read_file(node)
        out = []
        offset = 0
        while offset + 8 <= len(data):
            ino, rec_len, name_len, file_type = struct.unpack_from("<IHBB", data, offset)
            if rec_len <= 0:
                break
            name = data[offset + 8 : offset + 8 + name_len]
            if ino:
                out.append(dict(ino=ino, name=name.decode("utf-8", "replace"), type=file_type))
            offset += rec_len
        return out

    def lookup(self, path):
        node = self.inode(2)
        for part in [p for p in path.split("/") if p]:
            if node["mode"] & S_IFMT != S_IFDIR:
                raise SystemExit(f"{path}：{part} 之前不是目录")
            match = [e for e in self.entries(node) if e["name"] == part]
            if not match:
                raise SystemExit(f"{path}：找不到 {part}")
            node = self.inode(match[0]["ino"])
        return node


def main(argv=None):
    parser = argparse.ArgumentParser(description="相机 ext2/ext4 只读遍历")
    parser.add_argument("--local", type=Path, help="本机镜像文件（离线解析，不连相机）")
    parser.add_argument("--device", default="/dev/nflasha15")
    parser.add_argument("--list", default="")
    parser.add_argument("--get", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--grep", default="")
    args = parser.parse_args(argv)

    def progress(message):
        print(message, flush=True)

    import contextlib

    with contextlib.ExitStack() as stack:
        if args.local is not None:
            source = LocalImage(args.local)
            stack.callback(source.handle.close)
            device = "local"
        else:
            source = stack.enter_context(ServiceSession(progress=progress))
            device = args.device
        fs = Ext2(source, device)
        print(
            f"块大小 {fs.block_size} · inode {fs.inodes} · 每组 {fs.inodes_per_group} inode / "
            f"{fs.blocks_per_group} 块 · inode 大小 {fs.inode_size}",
            flush=True,
        )
        if args.list:
            node = fs.lookup(args.list)
            if node["mode"] & S_IFMT != S_IFDIR:
                print(f"{args.list} 不是目录"); return 1
            rows = fs.entries(node)
            print(f"{args.list} 下 {len(rows)} 项", flush=True)
            for row in sorted(rows, key=lambda r: r["name"]):
                if args.grep and args.grep not in row["name"]:
                    continue
                child = fs.inode(row["ino"])
                kind = "d" if child["mode"] & S_IFMT == S_IFDIR else "-"
                print(f"  {kind} {child['size']:>12,}  {row['name']}", flush=True)
        if args.get:
            node = fs.lookup(args.get)
            data = fs.read_file(node)
            out = Path(args.out or ".").expanduser()
            out.mkdir(parents=True, exist_ok=True)
            target = out / Path(args.get).name
            target.write_bytes(data)
            import hashlib
            print(f"保存 {target} {len(data):,} 字节 sha256={hashlib.sha256(data).hexdigest()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
