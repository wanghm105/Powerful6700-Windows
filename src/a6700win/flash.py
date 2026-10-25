# -*- coding: utf-8 -*-
"""机身文件写入（显式写载荷 native/flash_write.elf）。

与只读载荷 native/dump_range.elf 分成两份，是因为写入能力必须能被显式拒绝：
只读工具永远不会加载本模块的载荷，本模块的载荷也只会打开 /usr/、/cp/ 与
/setting/ 下的普通文件（/setting 只用 BACKUP.BIN，即 CP 单元的持久镜像），
碰到 /dev/* 或其它路径直接返回「拒绝写入」。

协议与 dump_range.c 完全一致（28 字节头 + 路径），额外多一个数据文件
/tmp/jiritsu/tmmc.dat：写入前先把这 length 字节传到相机，载荷会核对它的
长度是否恰好等于 length，长度不符就拒绝写入（防止陈旧或追加的数据被写进去）。

安全顺序（tools/flash_write.py 强制）：
  1 probe：载荷自己读出该范围的原字节再写回同样的字节，fsync 后回读比对。
     语义零变化，用来证明「挂载点可写 + pwrite64 可用 + 回读一致」这条链成立。
  2 verify：把相机上的现有字节与本地备份的同一范围比对，确认我们知道要改什么。
  3 write：真正写新字节，同样 fsync + 回读，失败即报告（不自动重试写入）。
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from . import dump

MAGIC = b"A67D"
VERSION = 1
HEADER = 28
PATH_MAX = 192
DATA_MAX = 0x100000
BLOCK = 0x8000
# 单次写入的大小上限。相机侧 Senser 写窗口是 133,120 字节，载荷内部按 0x20000 分块，
# 所以 0x20000 是「一次命令写进去」的安全上限。块越大，一次会话里的命令往返越少 ——
# 145 KB 语言资源从 5 次写压到 2 次，实测掉线点就在第 8~13 次往返上。
WRITE_BLOCK = 0x20000
DATA_PATH = "/tmp/jiritsu/tmmc.dat"
SERVICE_FUNCTION = 0x40

MODE_READ = 0
MODE_SIZE = 1
MODE_WRITE = 3
MODE_PROBE = 4
MODE_PROBE_SEQ = 5
MODE_WRITE_SEQ = 6
MODE_SCRATCH = 9
MODE_TRUNCATE = 10

WRITABLE_ROOTS = ("/usr/", "/cp/", "/setting/")

TARGETS = {
    "appfw": {"path": "/usr/lib/appFw.so", "size": 89027992,
              "sha256": "721fceaef26a46dabd538c4729b8c5a937b51887d4b127ba2832959b03c1144d"},
    "cpapp": {"path": "/cp/cpapp-b.bin", "size": 17892024,
              "sha256": "43c5d056ed9357957c5e7cd1ae24928b077d26b6761bf193eefb303b0b32510d"},
}

STATUS_TEXT = {
    0: "ok",
    1: "请求无效",
    2: "打开目标失败",
    3: "读取目标失败",
    4: "路径或长度越界",
    5: "定位目标长度失败",
    6: "拒绝写入：只允许 /usr/、/cp/ 与 /setting/ 下的普通文件，并且必须以 root 运行",
    7: "写入失败",
    8: "fsync 失败",
    9: "回读校验失败（写入的字节与预期不一致）",
    10: "数据文件缺失或长度不符",
    11: "无法把挂载点改为可写",
    12: "范围超出文件长度",
    13: "读取 I/O 失败",
    14: "截断失败",
}


class FlashError(RuntimeError):
    """写入链路失败；不包含任何「已重试」语义。"""


def payload_dir() -> Path:
    from . import paths

    for candidate in (paths.bundled_root() / "native", paths.project_root() / "native"):
        if (candidate / "flash_write.elf").is_file():
            return candidate
    raise FlashError("缺少写入载荷 native/flash_write.elf；请重新获取完整安装包。")


def payload() -> bytes:
    folder = payload_dir()
    manifest = json.loads((folder / "flash_manifest.json").read_text(encoding="utf-8"))
    data = (folder / manifest["payload"]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest["sha256"] or len(data) != manifest["bytes"]:
        raise FlashError("写入载荷与清单不一致，已停止（不会向相机发送任何数据）。")
    return data


READABLE_ROOTS = ("/usr/", "/cp/", "/setting/", "/system/")


def allowed(path: str) -> bool:
    """写入白名单：/usr/、/cp/ 与 /setting/ 可写，其它挂载点一律拒绝。"""
    if not path.startswith(WRITABLE_ROOTS):
        return False
    if "/../" in path or "/dev/" in path:
        return False
    return True


def allowed_read(path: str) -> bool:
    """读取白名单：比写入多出 /setting（nflasha2，含 BACKUP.BIN）与 /system。"""
    if not path.startswith(READABLE_ROOTS):
        return False
    if "/../" in path or "/dev/" in path:
        return False
    return True


def _request(path: str, offset: int, length: int, mode: int) -> bytes:
    writable = mode in (MODE_WRITE, MODE_PROBE, MODE_PROBE_SEQ, MODE_WRITE_SEQ, MODE_TRUNCATE)
    if writable and not allowed(path):
        raise FlashError(f"拒绝写入 {path}：只允许 /usr/、/cp/ 与 /setting/ 下的文件。")
    if not writable and not allowed_read(path):
        raise FlashError(f"拒绝读取 {path}：允许 /usr/、/cp/、/setting、/system。")
    encoded = path.encode("utf-8", "strict")
    if not encoded or len(encoded) > PATH_MAX:
        raise FlashError(f"路径长度必须在 1..{PATH_MAX} 字节")
    if mode == MODE_TRUNCATE:
        if length != 0:
            raise FlashError("截断请求的长度字段必须为 0")
    elif not 0 < length <= DATA_MAX:
        raise FlashError(f"单次长度必须在 1..{DATA_MAX} 字节")
    return struct.pack("<4sIIIQI", MAGIC, VERSION, mode, len(encoded), offset, length) + encoded


def _parse(blob: bytes) -> dict:
    if len(blob) < HEADER or blob[:4] != MAGIC:
        raise FlashError("写入载荷返回的结果头无效")
    _, version, status, mode, size, length = struct.unpack_from("<4sIIIQI", blob)
    if version != VERSION:
        raise FlashError(f"写入载荷协议版本 {version} 不受支持")
    if status:
        detail = f"，系统返回 {size}" if size else ""
        stage = f"，phase {length}" if length else ""
        raise FlashError(f"写入载荷失败：{STATUS_TEXT.get(status, status)}（状态 {status}{detail}{stage}）")
    return {"status": status, "mode": mode, "size": size, "length": length,
            "data": blob[HEADER:HEADER + length]}


def _execute(backend, elf: bytes, config: bytes) -> bytes:
    backend._file(0x4010, 0, config)
    backend._file(0x4007, 2, elf)
    body = backend._command(0x4008, bytes([0, 0, 0]))
    if len(body) < 4 or body[:4] != b"\x00" * 4:
        raise FlashError("写入载荷执行失败，相机没有返回结果文件")
    return body[4:]


def probe_scratch(backend, elf: bytes | None = None) -> int:
    """Mode 9: exercise open/write/fsync/pread on a scratch file in /tmp."""
    # the payload never touches the path in mode 9; keep it inside an allowed root
    body = _request("/usr/.scratch", 0, 1, MODE_SCRATCH)
    return _parse(_execute(backend, elf if elf is not None else payload(), body))["length"]


def stat(backend, path: str, elf: bytes | None = None) -> int:
    return _parse(_execute(backend, elf if elf is not None else payload(),
                           _request(path, 0, 1, MODE_SIZE)))["size"]


def read_range(backend, path: str, offset: int, length: int,
               elf: bytes | None = None) -> bytes:
    return _parse(_execute(backend, elf if elf is not None else payload(),
                           _request(path, offset, length, MODE_READ)))["data"]


def truncate(backend, path: str, size: int, elf: bytes | None = None) -> int:
    """Shrink `path` back to `size` bytes.

    Only used to undo an experiment that grew a file: the host writes the original
    bytes first, then truncates, so the file ends up byte-identical to the backup.
    """
    if not allowed(path):
        raise FlashError(f"拒绝写入 {path}：只允许 /usr/、/cp/ 与 /setting/ 下的文件。")
    actual = _parse(_execute(backend, elf or payload(),
                             _request(path, size, 0, MODE_TRUNCATE)))["size"]
    return actual


def probe(backend, path: str, offset: int = 0, length: int = 512,
          elf: bytes | None = None, sequential: bool = False) -> dict:
    """写入链路的零变化自检：载荷读出原字节，写回同样的字节，再回读比对。

    sequential=True 时改用 lseek + read/write（某些相机文件系统拒绝随机偏移）。
    """
    elf = elf if elf is not None else payload()
    mode = MODE_PROBE_SEQ if sequential else MODE_PROBE
    result = _parse(_execute(backend, elf, _request(path, offset, length, mode)))
    return {"path": path, "offset": offset, "length": result["length"],
            "sequential": sequential, "verified": True}


def write_block(backend, path: str, offset: int, data: bytes, elf: bytes | None = None,
                sequential: bool = False) -> dict:
    """写一个不超过 WRITE_BLOCK 的块：先传数据文件，再让载荷写入并回读。"""
    if not data:
        raise FlashError("空块不可写")
    if len(data) > WRITE_BLOCK:
        raise FlashError(f"单块最多 {WRITE_BLOCK} 字节（当前 {len(data)}）")
    elf = elf if elf is not None else payload()
    channel = backend.channel
    dump.select(channel, DATA_PATH)
    dump.jiritsu(channel, dump.CMD_WRITE, b"\x00\xff\x00" + data)
    mode = MODE_WRITE_SEQ if sequential else MODE_WRITE
    result = _parse(_execute(backend, elf, _request(path, offset, len(data), mode)))
    return {"path": path, "offset": offset, "length": result["length"], "sequential": sequential,
            "sha256": hashlib.sha256(data).hexdigest()}


def write_windows(backend, path: str, windows, progress=lambda message: None,
                  elf: bytes | None = None) -> list[dict]:
    """按 (offset, bytes) 顺序写入；每个块都自带 fsync 与回读校验。"""
    elf = elf if elf is not None else payload()
    done = []
    total = len(list(windows)) if not isinstance(windows, list) else len(windows)
    rows = windows if isinstance(windows, list) else list(windows)
    for index, (offset, data) in enumerate(rows, start=1):
        progress(f"正在写入 {path} 偏移 0x{offset:x}（{len(data)} 字节，{index}/{total}）…")
        done.append(write_block(backend, path, offset, data, elf))
    return done
