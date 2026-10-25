# -*- coding: utf-8 -*-
"""一次写入（颜色 + 菜单文字）的编排测试：不接触相机，只验证两段会话的顺序与失败处理。"""
from __future__ import annotations

import pytest

from a6700win import bundle


class _Calls:
    def __init__(self):
        self.items: list[tuple[str, str | None]] = []

    def names(self):
        return [name for name, _ in self.items]


def _colors_report(wrote: bool) -> dict:
    return {"wrote": wrote, "moved": [],
            "looks": [{"name": "CC", "state": "installed"}, {"name": "NC", "state": "installed"},
                      {"name": "PF", "state": "installed"}, {"name": "NF", "state": "installed"}]}


def _names_report(preset: str | None, wrote: bool) -> dict:
    return {"wrote": wrote, "preset": preset or "official", "bytes": 145708,
            "kind": "renamed", "mode": None,
            "changes": [{"rid": 0x021C6654, "old": "PT", "new": "Classic Chrome"}]}


@pytest.fixture
def calls(monkeypatch):
    record = _Calls()
    monkeypatch.setattr(bundle.looks, "apply",
                        lambda progress=None, channel=None: (record.items.append(("colors", None)),
                                                             _colors_report(True))[1])
    monkeypatch.setattr(bundle.looks, "restore",
                        lambda progress=None, channel=None: (record.items.append(("colors-restore", None)),
                                                             _colors_report(True))[1])
    monkeypatch.setattr(bundle.looknames, "apply",
                        lambda progress=None, channel=None, preset=None: (
                            record.items.append(("names", preset)), _names_report(preset, True))[1])
    monkeypatch.setattr(bundle.looknames, "restore",
                        lambda progress=None, channel=None, preset=None: (
                            record.items.append(("names-restore", preset)), _names_report(preset, True))[1])
    monkeypatch.setattr(bundle.looknames, "load_preset", lambda: "zh")
    return record


def test_apply_runs_colors_then_names_in_separate_calls(calls):
    report = bundle.apply(preset="zh")
    # 两段是两次独立调用（也就是两次独立 USB 会话），顺序固定
    assert calls.names() == ["colors", "names"]
    assert calls.items[1] == ("names", "zh")
    assert report["steps"] == ["colors", "names"]
    assert report["wrote"] is True
    assert report["error"] is None
    assert report["colors"]["wrote"] and report["names"]["wrote"]


def test_apply_falls_back_to_saved_preset(calls):
    report = bundle.apply()
    assert report["preset"] == "zh"
    assert calls.items[1] == ("names", "zh")
    assert "中文简称" in report["label"]


def test_restore_calls_the_restore_variants(calls):
    report = bundle.restore(preset="official")
    assert calls.names() == ["colors-restore", "names-restore"]
    assert calls.items[1] == ("names-restore", "official")
    assert report["steps"] == ["colors", "names"]


def test_colors_failure_stops_before_names(monkeypatch, calls):
    def boom(progress=None, channel=None):
        raise RuntimeError("USBError: Pipe error")

    monkeypatch.setattr(bundle.looks, "apply", boom)
    with pytest.raises(bundle.BundleError) as caught:
        bundle.apply(preset="official")
    assert "菜单文字一个字都没动" in str(caught.value)
    assert "names" not in calls.names()


def test_names_failure_keeps_colors_and_explains(monkeypatch, calls):
    def boom(progress=None, channel=None, preset=None):
        raise RuntimeError("[Errno 19] No such device")

    monkeypatch.setattr(bundle.looknames, "apply", boom)
    report = bundle.apply(preset="official")
    assert report["steps"] == ["colors"]
    assert report["wrote"] is True
    assert "颜色已经写进相机了" in report["error"]
    assert "还原本页外观" in report["error"]
    assert report["seconds"] >= 0


def test_summary_mentions_both_steps(calls):
    report = bundle.apply(preset="official")
    text = "\n".join(bundle.summary(report))
    assert "颜色：CC=已写入" in text
    assert "菜单文字：改了 1 条记录（官方原名）" in text


def test_summary_of_partial_report_has_no_name_lines(monkeypatch, calls):
    monkeypatch.setattr(bundle.looknames, "apply",
                        lambda progress=None, channel=None, preset=None: (_ for _ in ()).throw(
                            RuntimeError("boom")))
    report = bundle.apply(preset="zh")
    text = "\n".join(bundle.summary(report))
    assert "菜单文字" not in text
    assert "颜色：CC=已写入" in text
