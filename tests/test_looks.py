# -*- coding: utf-8 -*-
"""自定义外观配方与记录改写的纯逻辑测试（不接触相机）。"""
from __future__ import annotations

import pytest

from a6700win import cp, looks


def test_profile_has_the_four_looks_with_unique_banks():
    items = looks.profile()
    assert len(items) == 4
    assert [item["bank"] for item in items] == [6, 4, 1, 14]
    menus = [item["menu"] for item in items]
    assert "Classic Chrome" in menus[0]
    assert "Classic Negative" in menus[1]


def test_profile_records_are_64_bytes_and_differ_from_factory():
    for item in looks.profile():
        assert len(item["record_hex"]) == looks.STRIDE
        assert len(item["factory_hex"]) == looks.STRIDE
        assert item["record_hex"] != item["factory_hex"]


def test_classify_reports_three_states():
    item = looks.profile()[0]
    assert looks.classify(item["record_hex"], item) == "installed"
    assert looks.classify(item["factory_hex"], item) == "factory"
    assert looks.classify(bytes(looks.STRIDE), item) == "other"


def test_record_points_at_the_bank_window():
    unit = bytes(cp.CP_KEYS[cp.CHROMA_UNIT])
    item = looks.profile()[0]
    offset = looks.CHROMA_BASE + item["bank"] * looks.STRIDE
    assert looks.record(unit, item["bank"]) == unit[offset:offset + looks.STRIDE]


def test_splice_only_touches_its_own_record():
    unit = bytearray(cp.CP_KEYS[cp.CHROMA_UNIT])
    item = looks.profile()[1]
    after = looks._splice(unit, item, "record_hex")
    assert looks.record(after, item["bank"]) == item["record_hex"]
    targets = {row["bank"] for row in looks.profile()}
    assert looks.changed_banks(bytes(unit), after, targets) == []


def test_changed_banks_finds_unrelated_edits():
    unit = bytearray(cp.CP_KEYS[cp.CHROMA_UNIT])
    targets = {row["bank"] for row in looks.profile()}
    unit[looks.CHROMA_BASE + 5 * looks.STRIDE] = 0x7F
    assert looks.changed_banks(bytes(bytearray(cp.CP_KEYS[cp.CHROMA_UNIT])), bytes(unit), targets) == [5]


def test_changed_banks_rejects_length_mismatch():
    with pytest.raises(looks.LooksError):
        looks.changed_banks(bytes(16), bytes(32), set())
