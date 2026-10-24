
import hashlib

import pytest

from a6700win import guards


def _sector(fill: int = 0x11) -> bytes:
    return bytes([fill]) * 512


def _with_times(record_seed: bytes, atime: int, ctime: int, mtime: int) -> bytes:
    import struct

    buf = bytearray(record_seed)
    struct.pack_into("<III", buf, 0x08, atime, ctime, mtime)
    return bytes(buf)


def test_overlay_lists_inode_guards():
    data = guards.overlay()
    assert data["schema"] == "a6700win/guard-overlay/1"
    assert data["inode_size"] == 256
    table = guards.records()
    assert table, "豁免表不能为空"
    assert 18 in table
    for entry in table.values():
        assert entry["device"] == 0
        assert len(entry["normalized_sha256"]) == 64


def test_normalize_zeroes_only_timestamps():
    record = bytearray(_sector(0x22))
    record[0x00:0x02] = b"\xa4\x81"  # mode
    sector = _with_times(bytes(record), 1748034598, 1748034598, 1748034169)
    out = guards.normalize(sector)
    assert out[0x08:0x14] == b"\x00" * 12
    assert out[256 + 0x08:256 + 0x14] == b"\x00" * 12
    assert out[0x00:0x08] == sector[0x00:0x08]
    assert out[0x14:256] == sector[0x14:256]
    assert guards.digest(sector) == guards.digest(_with_times(bytes(record), 1, 2, 3))


def test_normalize_needs_full_records():
    odd = b"\x01" * 300
    assert guards.normalize(odd) == odd


class _Row(dict):
    pass


class _Profile:
    def __init__(self, rows):
        self.entries = rows


def test_wrap_inspect_normalizes_registered_guard(monkeypatch):
    pinned = _with_times(bytes(_sector(0x33)), 1748034598, 1748034598, 1748034169)
    drifted = _with_times(bytes(_sector(0x33)), 1748034598, 1062, 1062)
    monkeypatch.setattr(guards, "_cache", dict(
        schema="a6700win/guard-overlay/1",
        inode_size=256,
        volatile=[[8, 20]],
        records={"0": dict(device=0, device_offset=0x600D200,
                           normalized_sha256=hashlib.sha256(guards.normalize(pinned)).hexdigest())},
    ))
    profile = _Profile([_Row(role="guard", sha256=hashlib.sha256(pinned).hexdigest())])
    seen = {}

    def original(profile_arg, sectors, action="inspect", features=None):
        seen["sector"] = sectors[0]
        seen["sha"] = profile_arg.entries[0]["sha256"]
        return {"ok": hashlib.sha256(sectors[0]).hexdigest() == profile_arg.entries[0]["sha256"]}, sectors

    plan, _ = guards.wrap_inspect(original)(profile, [drifted])
    assert plan["ok"] is True
    assert seen["sector"][0x08:0x14] == b"\x00" * 12
    assert seen["sha"] == hashlib.sha256(guards.normalize(pinned)).hexdigest()


def test_wrap_inspect_keeps_content_changes(monkeypatch):
    pinned = _with_times(bytes(_sector(0x33)), 1, 2, 3)
    tampered = bytearray(_with_times(bytes(_sector(0x33)), 1, 999, 1000))
    tampered[0x20] ^= 0xFF  # 内容区被改
    monkeypatch.setattr(guards, "_cache", dict(
        schema="a6700win/guard-overlay/1",
        inode_size=256,
        volatile=[[8, 20]],
        records={"0": dict(device=0, device_offset=0,
                           normalized_sha256=hashlib.sha256(guards.normalize(pinned)).hexdigest())},
    ))
    profile = _Profile([_Row(role="guard", sha256=hashlib.sha256(pinned).hexdigest())])
    plan, _ = guards.wrap_inspect(lambda p, s, a="inspect", f=None: (
        {"ok": hashlib.sha256(s[0]).hexdigest() == p.entries[0]["sha256"]}, s))(
            profile, [bytes(tampered)])
    assert plan["ok"] is False


def test_prepare_skips_unknown_indices(monkeypatch):
    monkeypatch.setattr(guards, "_cache", dict(
        schema="a6700win/guard-overlay/1", inode_size=256, volatile=[[8, 20]],
        records={"7": dict(device=0, device_offset=0, normalized_sha256="0" * 64)},
    ))
    profile = _Profile([_Row(role="guard", sha256="a" * 64)])
    sector = _with_times(bytes(_sector(0x44)), 5, 6, 7)
    out = guards.prepare(profile, [sector])
    assert out[0] == sector
    assert profile.entries[0]["sha256"] == "a" * 64


def test_status_reports_count():
    status = guards.status()
    assert status["ok"] is True
    assert status["count"] == len(guards.records())
