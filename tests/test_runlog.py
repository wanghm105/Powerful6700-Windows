"""runlog：日志落盘、轮转、坏目录不许把主流程带崩。"""

from __future__ import annotations

from a6700win import runlog


def test_start_writes_header_and_messages(tmp_path):
    path = runlog.start("unit", directory=tmp_path)
    try:
        assert path is not None
        assert path.parent == tmp_path
        runlog.write("正在读取补丁目标和结构守卫…")
        assert runlog.path() == path
    finally:
        runlog.close()
    text = path.read_text(encoding="utf-8")
    assert "Powerful6700Win" in text
    assert "日志文件：" in text
    assert "正在读取补丁目标和结构守卫…" in text


def test_write_after_close_is_a_noop(tmp_path):
    runlog.start("unit", directory=tmp_path)
    runlog.close()
    runlog.write("这句不该写进任何文件")
    runlog.close()
    assert runlog.path() is None


def test_start_keeps_only_recent_files(tmp_path):
    for index in range(runlog.MAX_FILES + 3):
        (tmp_path / ("run-%02d.log" % index)).write_text("x", encoding="utf-8")
    runlog.start("trim", directory=tmp_path)
    runlog.close()
    assert len(list(tmp_path.glob("run-*.log"))) == runlog.MAX_FILES


def test_start_never_raises_when_directory_is_unusable(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("我是文件不是目录", encoding="utf-8")
    assert runlog.start("unit", directory=blocker / "logs") is None
    runlog.write("不许抛")
