"""只读读取协议（dump.py）的离线测试：不连接任何真实设备。"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from a6700win import dump


def _result(status=0, mode=0, size=0, data=b"", length=None):
    return (
        struct.pack(
            "<4sIIIQI", dump.MAGIC, dump.VERSION, status, mode, size,
            len(data) if length is None else length,
        )
        + data
    )


class FakeBackend:
    """按 dump 载荷的协议回放结果，用来验证主机侧编解码与循环。"""

    def __init__(self, files, chunk_result=None):
        self.files = files
        self.config = None
        self.payload = None
        self.executed = 0
        self.chunk_result = chunk_result

    def _file(self, command, ident, data):
        if command == 0x4010:
            self.config = data
        elif command == 0x4007:
            self.payload = data
        else:  # pragma: no cover - 协议只用到这两条
            raise AssertionError(command)

    def _command(self, command, payload):
        assert command == 0x4008
        self.executed += 1
        magic, version, mode, path_len, offset, length = struct.unpack_from("<4sIIIQI", self.config)
        path = self.config[dump.HEADER: dump.HEADER + path_len].decode()
        data = self.files[path]
        if mode == 1:
            return b"\0" * 4 + _result(status=0, mode=1, size=len(data))
        if self.chunk_result is not None:
            return b"\0" * 4 + self.chunk_result
        return b"\0" * 4 + _result(mode=0, length=length, data=data[offset: offset + length])


def test_request_layout_matches_payload_header():
    request = dump._request("/dev/nflasha15", 0x1000, 0x200, 0)
    magic, version, mode, path_len, offset, length = struct.unpack_from("<4sIIIQI", request)
    assert (magic, version, mode, offset, length) == (b"A67D", 1, 0, 0x1000, 0x200)
    assert path_len == len("/dev/nflasha15")
    assert request[dump.HEADER:].decode() == "/dev/nflasha15"
    assert len(request) == dump.HEADER + path_len


def test_request_rejects_oversized_and_empty_length():
    with pytest.raises(dump.DumpError):
        dump._request("/dev/nflasha15", 0, dump.DATA_MAX + 1, 0)
    with pytest.raises(dump.DumpError):
        dump._request("/dev/nflasha15", 0, 0, 0)
    with pytest.raises(dump.DumpError):
        dump._request("", 0, 1, 0)


def test_parse_result_reports_payload_problem():
    with pytest.raises(dump.DumpError, match="打开目标失败"):
        dump._parse_result(_result(status=2))
    with pytest.raises(dump.DumpError, match="结果头无效"):
        dump._parse_result(b"XXXX" + b"\0" * 40)


def test_stat_and_read_range_round_trip():
    backend = FakeBackend({"/dev/nflasha15": bytes(range(256)) * 8})
    assert dump.stat(backend, "/dev/nflasha15") == 2048
    chunk = dump.read_range(backend, "/dev/nflasha15", 16, 32)
    assert chunk["data"] == (bytes(range(256)) * 8)[16:48]
    assert backend.payload is not None and len(backend.payload) == dump.payload_dir().joinpath("dump_range.elf").stat().st_size


def test_dump_writes_file_and_hash(tmp_path: Path):
    payload = bytes(((i * 7) % 251) for i in range(5000))
    backend = FakeBackend({"/usr/lib/appFw.so": payload})
    output = tmp_path / "appFw.so"
    report = dump.dump(backend, "/usr/lib/appFw.so", output, chunk=1024)
    assert output.read_bytes() == payload
    assert report["size"] == report["bytes"] == 5000
    assert report["sha256"] == hashlib.sha256(payload).hexdigest()
    sidecar = json.loads(Path(str(output) + ".json").read_text(encoding="utf-8"))
    assert sidecar["path"] == "/usr/lib/appFw.so"
    assert not Path(str(output) + ".part").exists()


def test_dump_stops_on_empty_chunk(tmp_path: Path):
    backend = FakeBackend({"/dev/nflasha15": b"x" * 4096}, chunk_result=_result(length=0, data=b""))
    with pytest.raises(dump.DumpError, match="空数据"):
        dump.dump(backend, "/dev/nflasha15", tmp_path / "x.bin", chunk=4096)


def test_payload_matches_manifest():
    elf = dump.payload()
    manifest = json.loads((dump.payload_dir() / "dump_manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(elf).hexdigest() == manifest["sha256"]
    assert len(elf) == manifest["bytes"]
    assert elf[:4] == b"\x7fELF"


def test_camera_file_uses_traversal_path():
    seen = {}

    class Channel:
        def send(self, pfunc, body):
            seen["pfunc"] = pfunc
            command = struct.unpack_from("<H", body, 2)[0]
            seen.setdefault("commands", []).append(command)
            seen["payload"] = body[4:]
            return 0, struct.pack("<I", 0) + b"data"

    assert dump.camera_file(Channel(), "/usr/lib/appFw.so") == b"data"
    assert seen["commands"] == [15, 17]
    assert seen["payload"] == b"\0\xff\0"
    assert dump.JIRITSU_DIR + "../.." == "/tmp/jiritsu/../.." 



def test_dump_supports_offset_and_limit(tmp_path: Path):
    payload_bytes = bytes(range(256)) * 4
    backend = FakeBackend({"/dev/nflasha15": payload_bytes})
    output = tmp_path / "part.bin"
    report = dump.dump(backend, "/dev/nflasha15", output, chunk=64, offset=100, limit=200)
    assert output.read_bytes() == payload_bytes[100:300]
    assert report["bytes"] == 200 and report["offset"] == 100


def test_dump_requires_bytes_when_device_reports_zero_size(tmp_path: Path):
    class Zero(FakeBackend):
        def _command(self, command, payload):
            self.executed += 1
            return b"\0" * 4 + _result(status=0, mode=1, size=0)

    with pytest.raises(dump.DumpError, match="报不出长度"):
        dump.dump(Zero({}), "/dev/nflasha15", tmp_path / "z.bin")

