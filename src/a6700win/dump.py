"""机身文件只读读取（参考 A7C2 的 Jiritsu 文件读取方式）。

两条通道：
1. `jiritsu` / `select` / `read_file`：直接用服务通道的文件命令（A7C2 的
   transport.Session.jiritsu/select/read）。cmd 15 选中路径，cmd 17 读整个文件。
   受主机侧单次 Senser 响应上限限制，适合小文件。
2. `read_range` / `dump`：把只读载荷 native/dump_range.elf 送进相机，由它用
   pread64 分块读任意路径（含 /dev/nflasha15 等设备节点），主机按 <=1 MiB 分块收。
   载荷只以 O_RDONLY 打开文件，没有 pwrite64 调用路径。
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
from pathlib import Path

JIRITSU_DIR = "/tmp/jiritsu/"
# Senser 的文件传输（0x4010 配置写入）和我们自己的载荷共用这两个名字：
# 上一次会话没干净结束时它们会留在相机里，导致下一次配置写入被拒（0x10000004）。
TEMP_PATHS = ("/tmp/jiritsu/tmmc.jit", "/tmp/jiritsu/tmmc.dat")
CMD_SELECT = 15
CMD_WRITE = 16
CMD_READ = 17
CMD_REMOVE = 18
STATUS_MISSING = 0x10000006
SERVICE_FUNCTION = 0x40

MAGIC = b"A67D"
VERSION = 1
HEADER = 28
PATH_MAX = 192
DATA_MAX = 0x100000
# legacy.SenserChannel 拒绝声明长度超过 SENSER_MAX_SIZE(0x100000) 的响应，而执行
# 响应 = 4 字节状态 + 结果文件（28 字节头 + 数据），所以单块留出余量。
SENSER_RESPONSE_MAX = 0x100000
# 相机侧 Jiritsu 服务对单次回复可能另有上限；先取 256 KiB，实测后再调大。
CHUNK = 0x40000

STATUS_TEXT = {
    0: "ok",
    1: "bad request",
    2: "打开目标失败",
    3: "读取目标失败",
    4: "路径过长或长度越界",
    5: "定位目标长度失败",
}


class DumpError(RuntimeError):
    """读取机身文件失败，或返回内容不符合协议。"""


def payload_dir() -> Path:
    from . import paths

    for candidate in (paths.bundled_root() / "native", paths.project_root() / "native"):
        if (candidate / "dump_range.elf").is_file():
            return candidate
    raise DumpError("缺少只读读取载荷 native/dump_range.elf；请重新获取完整安装包。")


def payload() -> bytes:
    """读取载荷并校验清单哈希，损坏时立即拒绝。"""
    folder = payload_dir()
    manifest = json.loads((folder / "dump_manifest.json").read_text(encoding="utf-8"))
    data = (folder / manifest["payload"]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest["sha256"] or len(data) != manifest["bytes"]:
        raise DumpError("只读读取载荷与清单不一致，已停止（不会向相机发送任何数据）。")
    return data


def _status(payload_bytes: bytes) -> int:
    if len(payload_bytes) < 4:
        raise DumpError("Jiritsu 响应过短，无法读取状态码")
    return struct.unpack_from("<I", payload_bytes)[0]


def jiritsu(channel, command: int, data: bytes = b"", missing: bool = False):
    """发送一条 Jiritsu 文件命令，返回去掉状态码后的数据。"""
    if command not in (CMD_SELECT, CMD_WRITE, CMD_READ, CMD_REMOVE):
        raise DumpError(f"不允许的 Jiritsu 命令 {command}")
    code, out = channel.send(
        SERVICE_FUNCTION, struct.pack("<HH", 0x1001, command) + data
    )
    if code:
        raise DumpError(f"Jiritsu 命令 {command} 返回码 {code}")
    status = _status(out)
    if missing and status == STATUS_MISSING:
        return None
    if status:
        raise DumpError(f"Jiritsu 状态 0x{status:08x}")
    return out[4:]


def _checked_path(path: str) -> bytes:
    if not path.startswith(JIRITSU_DIR):
        raise DumpError(f"Jiritsu 只接受 {JIRITSU_DIR} 下的路径：{path}")
    if "\0" in path:
        raise DumpError("路径包含 NUL")
    encoded = path.encode("ascii", "strict")
    if len(encoded) > 510:
        raise DumpError("路径过长")
    return encoded


def select(channel, path: str) -> None:
    jiritsu(channel, CMD_SELECT, b"\0" + _checked_path(path) + b"\0")


def read_file(channel, path: str, missing: bool = False):
    """读整个文件（A7C2 的做法）。大文件请改用 read_range。"""
    select(channel, path)
    return jiritsu(channel, CMD_READ, b"\0\xff\0", missing)


def remove(channel, path: str, missing: bool = True) -> bool:
    """删除 /tmp/jiritsu 下的临时文件；文件本来不在就算成功。

    Senser 的文件传输（0x4010 配置写入）与我们的载荷共用 /tmp/jiritsu/tmmc.jit
    这条约定，上一次会话没干净结束时它会留在那里，下一次配置写入就会被相机拒绝
    （状态 0x10000004）。写之前清一遍能避免这种连锁失败。

    报文与 A7C2 一致（refs/a7c2-fl23 src/camera_runtime/transport.py:417-420）：
    先 select 目标路径，再发 CMD_REMOVE 且正文只有 b"\\0\\xff"。
    路径直接塞进 CMD_REMOVE 会被相机拒成 0x10000201。
    """
    select(channel, path)
    return jiritsu(channel, CMD_REMOVE, b"\0\xff", missing=missing) is not None


def camera_file(channel, absolute_path: str, missing: bool = False):
    """用 /tmp/jiritsu/../.. 穿越读取绝对路径（A7C2 app.py:110 同款）。"""
    if not absolute_path.startswith("/"):
        raise DumpError("需要绝对路径")
    return read_file(channel, JIRITSU_DIR + "../.." + absolute_path, missing)


def _request(path: str, offset: int = 0, length: int = 0, mode: int = 0) -> bytes:
    encoded = path.encode("utf-8", "strict")
    if not encoded or len(encoded) > PATH_MAX:
        raise DumpError(f"路径长度必须在 1..{PATH_MAX} 字节")
    if mode == 0 and not 0 < length <= DATA_MAX:
        raise DumpError(f"单次长度必须在 1..{DATA_MAX} 字节")
    return (
        struct.pack("<4sIIIQI", MAGIC, VERSION, mode, len(encoded), offset, length)
        + encoded
    )


def _parse_result(blob: bytes) -> dict:
    if len(blob) < HEADER or blob[:4] != MAGIC:
        raise DumpError("只读载荷返回的结果头无效")
    _, version, status, mode, size, length = struct.unpack_from("<4sIIIQI", blob)
    if version != VERSION:
        raise DumpError(f"只读载荷协议版本 {version} 不受支持")
    data = blob[HEADER:]
    if status:
        raise DumpError(f"读取机身文件失败：{STATUS_TEXT.get(status, status)}（状态 {status}）")
    if length and len(data) < length:
        raise DumpError(f"返回长度不足：{len(data)} < {length}")
    return {
        "status": status,
        "mode": mode,
        "size": size,
        "length": length,
        "data": data[:length] if length else b"",
    }


def _execute(backend, elf: bytes, config: bytes) -> bytes:
    """SET_FILE(0) 请求 → SET_FILE(2) 载荷 → EXECUTE，返回结果文件内容。"""
    backend._file(0x4010, 0, config)
    backend._file(0x4007, 2, elf)
    body = backend._command(0x4008, bytes([0, 0, 0]))
    if len(body) < 4 or body[:4] != b"\0" * 4:
        raise DumpError("载荷执行失败，相机没有返回结果文件")
    return body[4:]


def read_range(backend, path: str, offset: int = 0, length: int = CHUNK, elf: bytes | None = None) -> dict:
    return _parse_result(_execute(backend, elf if elf is not None else payload(),
                                  _request(path, offset, length, 0)))


def list_dir(backend, path: str, elf: bytes | None = None) -> list[str]:
    """列出相机上的一个目录（mode 2）；目录名以 / 结尾，其余为文件名。"""
    result = _parse_result(_execute(backend, elf if elf is not None else payload(),
                                    _request(path, 0, 0, 2)))
    text = result["data"].decode("utf-8", "replace")
    return [line for line in text.split(chr(10)) if line]


def stat(backend, path: str, elf: bytes | None = None) -> int:
    return _parse_result(_execute(backend, elf if elf is not None else payload(),
                                  _request(path, 0, 0, 1)))["size"]


def dump(backend, path: str, output: Path, progress=lambda message: None, chunk: int = CHUNK,
         offset: int = 0, limit: int | None = None) -> dict:
    """把相机上的一个文件/设备节点读回本机，边读边算哈希。

    设备节点往往报不出长度（lseek 返回 0），此时用 limit 指定读取字节数。
    """
    elf = payload()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    progress(f"正在读取 {path} 的长度…")
    size = stat(backend, path, elf)
    if size <= 0:
        if not limit:
            raise DumpError(
                f"{path} 报不出长度（lseek 返回 {size}）；设备节点请用 --bytes 指定读取字节数。"
            )
        size = offset + limit
    if limit:
        size = min(size, offset + limit)
    if offset:
        progress(f"从偏移 {offset:,} 开始读取，目标 {max(size - offset, 0):,} 字节")
    progress(f"{path} 大小 {size:,} 字节，开始分块读取…")
    digest = hashlib.sha256()
    written = 0
    started = time.monotonic()
    position = offset
    temporary = output.with_name(output.name + ".part")
    with temporary.open("wb") as handle:
        while position < size:
            want = min(chunk, size - position)
            result = read_range(backend, path, position, want, elf)
            data = result["data"]
            if not data:
                raise DumpError(f"在偏移 {written:,} 处读到空数据，已停止（不要重复发送写入器）")
            handle.write(data)
            digest.update(data)
            written += len(data)
            position += len(data)
            if written % (chunk * 8) < chunk or position >= size:
                progress(f"已读取 {written:,}/{max(size - offset, 0):,} 字节")
        handle.flush()
    temporary.replace(output)
    elapsed = max(time.monotonic() - started, 0.001)
    report = {
        "path": path,
        "offset": offset,
        "output": str(output),
        "size": size,
        "bytes": written,
        "sha256": digest.hexdigest(),
        "seconds": round(elapsed, 1),
        "bytes_per_second": int(written / elapsed),
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    progress(f"读取完成：{written:,} 字节，SHA-256 {report['sha256']}")
    return report

