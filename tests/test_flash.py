# -*- coding: utf-8 -*-
"""写入链路的纯静态测试：不接触相机。"""
from __future__ import annotations

import hashlib
import json

import pytest

from a6700win import flash


def test_payload_manifest_matches():
    data = flash.payload()
    manifest = json.loads((flash.payload_dir() / "flash_manifest.json").read_text(encoding="utf-8"))
    assert len(data) == manifest["bytes"]
    assert hashlib.sha256(data).hexdigest() == manifest["sha256"]


def test_allowed_paths():
    assert flash.allowed("/usr/lib/appFw.so")
    assert flash.allowed("/cp/cpapp-b.bin")
    for bad in ("/dev/nflasha15", "/etc/passwd", "/usr/../dev/nflasha8",
                "/usr/share/app/x.uxc/../../dev/x", "usr/lib/appFw.so"):
        assert not flash.allowed(bad), bad


def test_request_rejects_foreign_targets():
    with pytest.raises(flash.FlashError):
        flash._request("/dev/nflasha15", 0, 16, flash.MODE_WRITE)
    with pytest.raises(flash.FlashError):
        flash._request("/usr/lib/appFw.so", 0, 0, flash.MODE_WRITE)
    with pytest.raises(flash.FlashError):
        flash._request("/usr/lib/appFw.so", 0, flash.DATA_MAX + 1, flash.MODE_WRITE)


def test_request_layout():
    blob = flash._request("/cp/cpapp-b.bin", 0x1234, 0x200, flash.MODE_WRITE)
    assert blob[:4] == b"A67D"
    assert len(blob) == flash.HEADER + len("/cp/cpapp-b.bin")


def test_parse_reports_status():
    head = (flash.MAGIC
            + (1).to_bytes(4, "little")
            + (9).to_bytes(4, "little")
            + (flash.MODE_WRITE).to_bytes(4, "little")
            + (0).to_bytes(8, "little")
            + (0).to_bytes(4, "little"))
    with pytest.raises(flash.FlashError) as error:
        flash._parse(head)
    assert "回读校验失败" in str(error.value)


def test_block_limit():
    with pytest.raises(flash.FlashError):
        flash.write_block(object(), "/cp/cpapp-b.bin", 0, b"\x00" * (flash.WRITE_BLOCK + 1))
    with pytest.raises(flash.FlashError):
        flash.write_block(object(), "/cp/cpapp-b.bin", 0, b"")
    # 写入块比读块大：145 KB 语言资源只要两次写，命令往返次数才是掉线的关键。
    assert flash.WRITE_BLOCK == 0x20000
    assert flash.WRITE_BLOCK > flash.BLOCK


def test_targets_recorded():
    assert flash.TARGETS["appfw"]["size"] == 89027992
    assert flash.TARGETS["cpapp"]["size"] == 17892024
    assert flash.TARGETS["appfw"]["sha256"].startswith("721fceae")
