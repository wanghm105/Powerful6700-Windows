# -*- coding: utf-8 -*-
"""菜单文字改写与还原的纯逻辑测试（合成 UXC 资源，不接触相机）。"""
from __future__ import annotations

import hashlib
import struct

import pytest

from a6700win import looknames, uxc


def _rid_offset(rid: int) -> tuple[int, int]:
    return (rid - 0x02000000) >> 13, (rid - 0x02000000) & 0x1FFF


def _build(texts: dict[int, str]) -> bytes:
    """按 UXC-v7 布局拼一份最小资源：只放给定 rid 的记录，其余槽位填 0xffff。"""
    group = _rid_offset(next(iter(texts)))[0]
    by_index = {_rid_offset(rid)[1]: rid for rid in texts}
    count = max(by_index) + 1
    base = (16 + count * 2 + 3) & ~3
    head = bytearray(uxc.MAGIC + struct.pack("<HHI", 8, group,
                                            count | (((count + 1) & ~1) << 12)))
    table = bytearray(b"\xff\xff" * count)
    body = bytearray()
    for index in range(count):
        rid = by_index.get(index)
        if rid is None:
            continue
        struct.pack_into("<H", table, index * 2, len(body) // 4)
        block = struct.pack("<I", 0x1E000000 | (rid & 0xFFFFFF)) + texts[rid].encode() + b"\0"
        block += b"\0" * ((-len(block)) % 4)
        body += block
    raw = bytes(head + table)
    return raw + b"\0" * (base - len(raw)) + bytes(body)


def _labels() -> dict[int, str]:
    return {rid: slot for slot, rids in looknames.SLOT_RIDS.items() for rid in rids}


def test_decode_reads_the_layout_back():
    raw = _build(_labels())
    resource = uxc.decode(raw)
    assert uxc.texts(raw, looknames.ALL_RIDS) == _labels()
    assert all(record.capacity >= len(record.text) for record in resource.records)


def test_classify_recognises_factory_labels_and_renamed():
    raw = _build(_labels())
    assert looknames.classify(raw) == "factory-labels"
    renamed, _ = uxc.rename_all(raw, looknames._edits(looknames.targets()))
    assert looknames.classify(renamed) == "renamed"
    other = _build({**_labels(), looknames.SLOT_RIDS["PT"][1]: "Half-done"})
    assert looknames.classify(other) == "other"


def test_rename_all_is_idempotent():
    raw = _build(_labels())
    rows = looknames.targets("zh")
    first, changes = uxc.rename_all(raw, looknames._edits(rows))
    assert len(changes) == 8
    names = uxc.texts(first, looknames.ALL_RIDS)
    assert names[looknames.SLOT_RIDS["PT"][0]] == "富士CC"
    assert names[looknames.SLOT_RIDS["PT"][1]] == "富士CC"
    again, changes2 = uxc.rename_all(first, looknames._edits(rows))
    assert changes2 == []
    assert again == first


def test_longer_texts_grow_the_file_and_shortening_undoes_it():
    raw = _build(_labels())
    grown, _ = uxc.rename_all(raw, looknames._edits(looknames.targets()))
    assert len(grown) > len(raw)
    assert len(grown) % 4 == 0
    back, _ = uxc.rename_all(grown, _labels())
    assert len(back) == len(raw)
    # 重排是确定性的：缩回短名后与原文件逐字节一致（实测行为，界面不把它当承诺）
    assert back == raw


def test_patch_text_refuses_text_longer_than_the_record():
    raw = _build(_labels())
    record = uxc.decode(raw).by_rid()[looknames.SLOT_RIDS["ST"][0]]
    assert uxc.patch_text(raw, record, "ST").__len__() == len(raw)
    with pytest.raises(uxc.UxcError):
        uxc.patch_text(raw, record, "非常非常长的名字")


def test_rename_unknown_rid_and_empty_text_are_rejected():
    raw = _build(_labels())
    with pytest.raises(uxc.UxcError):
        uxc.grow(raw, 0x021C9999, "X")
    with pytest.raises(uxc.UxcError):
        uxc.grow(raw, looknames.SLOT_RIDS["ST"][0], "")


def test_baseline_capture_dedupes_and_picks_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(looknames, "store_dir", lambda: tmp_path)
    raw = _build(_labels())
    first = looknames.capture(raw, source="测试")
    second = looknames.capture(raw, source="又存一次")
    assert first["sha256"] == second["sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(looknames.baseline_items()) == 1
    assert second["bytes"] == len(raw)
    best = looknames.best_baseline()
    assert best is not None and best["sha256"] == first["sha256"]
    summary = looknames.baseline_summary()
    assert summary["ready"] and summary["count"] == 1


def test_baseline_rejects_unknown_resource_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(looknames, "store_dir", lambda: tmp_path)
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"not a uxc")
    with pytest.raises(looknames.LookNamesError):
        looknames.import_file(bad)
    tiny = tmp_path / "tiny.uxc.bin"
    tiny.write_bytes(_build({looknames.SLOT_RIDS["ST"][0]: "ST"}) + b"\0" * 4096)
    with pytest.raises(looknames.LookNamesError):
        looknames.import_file(tiny)


def test_targets_come_from_the_profile_with_menu_slot_and_text():
    rows = looknames.targets("official")
    assert [row["slot"] for row in rows] == ["PT", "NT", "VV", "VV2"]
    assert [row["text"] for row in rows] == ["Classic Chrome", "Classic Neg.", "Positive Film", "Negative Film"]
    edits = looknames._edits(rows)
    assert edits[looknames.SLOT_RIDS["VV2"][1]] == "Negative Film"
    # 两套命名都从同一份配方取，只是键不同；每行还带上全部变体供界面切换
    zh = looknames.targets("zh")
    assert [row["text"] for row in zh] == ["富士CC", "富士NC", "理光正片", "理光负片"]
    assert zh[0]["variants"] == {"official": "Classic Chrome", "zh": "富士CC"}
    assert looknames.load_preset() in looknames.PRESETS


class _FakeDevice:
    """只实现 flash 的四个函数（stat / read_range / write_block / truncate）的假设备。"""

    def __init__(self, blob: bytes):
        self.blob = blob

    def stat(self, backend, path):
        assert path == looknames.BLOB_PATH
        return len(self.blob)

    def read_range(self, backend, path, offset, size):
        assert path == looknames.BLOB_PATH
        return self.blob[offset:offset + size]

    def write_block(self, backend, path, offset, data):
        assert path == looknames.BLOB_PATH
        if offset > len(self.blob):
            raise AssertionError("分块写入越过了文件末尾")
        self.blob = self.blob[:offset] + data + self.blob[offset + len(data):]

    def truncate(self, backend, path, size):
        assert path == looknames.BLOB_PATH
        self.blob = self.blob[:size]


def test_apply_then_restore_through_a_fake_device(tmp_path, monkeypatch):
    from contextlib import contextmanager

    monkeypatch.setattr(looknames, "store_dir", lambda: tmp_path)
    original = _build(_labels())
    device = _FakeDevice(original)
    for name in ("stat", "read_range", "write_block", "truncate"):
        monkeypatch.setattr(looknames.flash, name, getattr(device, name))

    @contextmanager
    def fake_scope(progress=lambda message: None, channel=None):
        yield None, device

    monkeypatch.setattr(looknames, "_scope", fake_scope)
    messages: list[str] = []

    report = looknames.apply(messages.append)
    assert report["wrote"] is True
    assert report["kind"] == "renamed"
    assert [row["state"] for row in report["looks"]] == ["installed"] * 4
    assert device.blob == uxc.rename_all(original, looknames._edits(looknames.targets()))[0]
    assert report["captured"]["bytes"] == len(original)  # 写前自动存了基线

    # 再点一次「写入」：幂等，不写盘
    again = looknames.apply(messages.append)
    assert again["wrote"] is False and again["changes"] == []

    restored = looknames.restore(messages.append)
    assert restored["mode"] == "baseline"
    assert restored["wrote"] is True
    assert device.blob == original  # 逐字节回到出厂
    assert restored["kind"] == "factory-labels"  # 合成资源哈希不等于真机出厂资源

    # 已经出厂时再还原：不写盘
    third = looknames.restore(messages.append)
    assert third["wrote"] is False
    assert any("无需写入" in message or "一致" in message for message in messages)


def test_restore_without_baseline_falls_back_to_labels(tmp_path, monkeypatch):
    from contextlib import contextmanager

    monkeypatch.setattr(looknames, "store_dir", lambda: tmp_path)
    original = _build(_labels())
    renamed, _ = uxc.rename_all(original, looknames._edits(looknames.targets()))
    device = _FakeDevice(renamed)
    for name in ("stat", "read_range", "write_block", "truncate"):
        monkeypatch.setattr(looknames.flash, name, getattr(device, name))

    @contextmanager
    def fake_scope(progress=lambda message: None, channel=None):
        yield None, device

    monkeypatch.setattr(looknames, "_scope", fake_scope)
    assert looknames.best_baseline() is None
    report = looknames.restore(lambda message: None)
    # 合成资源没有写进 FACTORY_SHA256，所以走 labels 档，但字节恰好回到原样
    assert report["mode"] == "labels"
    assert device.blob == original
    assert report["kind"] == "factory-labels"
