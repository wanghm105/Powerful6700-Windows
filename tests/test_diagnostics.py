"""差异翻译与取证：blocked 时能拿出偏移，而不是一句「内容或布局不匹配」。"""
from __future__ import annotations

import json
import zipfile

from a6700win import diagnostics


GUARD = {"kind": "sector-guard-mismatch", "index": 9, "device": "0",
         "offset": 0x02844000, "role": "guard"}
FIELD = {"kind": "unknown-field", "edit_id": "ftp", "image": "appFw",
         "offset": 0x00100004, "actual": "ff"}
REQUIREMENT = {"kind": "feature-requirement", "feature": "shutter",
               "detail": "先关掉 FTP"}


def test_describe_guard_carries_offset_and_role():
    text = diagnostics.describe(GUARD)
    assert "结构守卫不匹配" in text
    assert "0x02844000" in text
    assert "role=guard" in text


def test_describe_unknown_kind_is_passed_through():
    text = diagnostics.describe({"kind": "brand-new", "index": 3})
    assert text.startswith("brand-new")
    assert "index=3" in text


def test_issue_lines_truncates_and_says_how_many_left():
    rows = diagnostics.issue_lines([GUARD, FIELD, REQUIREMENT], limit=2)
    assert len(rows) == 3
    assert "0x02844000" in rows[0]
    assert "还有 1 处" in rows[-1]
    assert "plan.json" in rows[-1]


def test_issue_lines_on_empty_list():
    assert diagnostics.issue_lines([]) == []
    assert diagnostics.issue_lines(None) == []


def test_issue_hint_names_the_guard_case_and_says_read_only():
    hint = diagnostics.issue_hint([GUARD])
    assert "结构守卫" in hint
    assert "只读检查不写任何东西" in hint
    assert diagnostics.issue_hint([]) == ""


def test_issue_hint_mentions_ftp_residue_for_unknown_field():
    assert "FTP" in diagnostics.issue_hint([FIELD])


def test_read_interrupted_recognises_a_dropped_cable():
    assert diagnostics.read_interrupted("[Errno 32] Pipe error")
    assert diagnostics.read_interrupted("libusb_error: No such device")
    assert diagnostics.read_interrupted("") is False
    assert diagnostics.read_interrupted("内容或布局不匹配") is False


def test_report_is_pasteable_and_counts_issues():
    result = {"status": "blocked", "device_access": True, "write_attempted": False,
              "run_directory": "C:/runs/1",
              "plan": {"compatible": False, "read_sectors": 260, "read_bytes": 133120,
                       "issues": [GUARD, FIELD]}}
    text = diagnostics.report(result, {"version": "0.3.8", "platform": "Windows"})
    assert "0.3.8" in text
    assert "结论：blocked" in text
    assert "问题：2 处" in text
    assert "0x02844000" in text
    assert "C:/runs/1" in text


def test_export_bundle_keeps_plan_json_and_drops_sectors(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "plan.json").write_text(json.dumps({"issues": [GUARD]}), encoding="utf-8")
    (run_dir / "native-result.json").write_text("{}", encoding="utf-8")
    target = tmp_path / "bundle.zip"
    result = {"status": "blocked", "run_directory": str(run_dir),
              "sectors": ["x" * 100], "plan": {"compatible": False, "issues": [GUARD]}}
    path = diagnostics.export_bundle(result, target, {"version": "0.3.8"})
    assert path == target
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        assert {"diagnostics.txt", "result.json", "environment.json"} <= names
        assert "run/plan.json" in names
        assert "run/native-result.json" in names
        assert "0x02844000" in archive.read("diagnostics.txt").decode("utf-8")
        slim = json.loads(archive.read("result.json").decode("utf-8"))
        assert "sectors" not in slim
        assert slim["plan"]["issues"][0]["kind"] == "sector-guard-mismatch"


def test_environment_survives_a_broken_probe(monkeypatch):
    monkeypatch.setattr(diagnostics, "_safe", lambda call: {"error": "boom"})
    data = diagnostics.environment()
    assert data["version"]
    assert data["paths"] == {"error": "boom"}
    assert data["patches"] == {"error": "boom"}
