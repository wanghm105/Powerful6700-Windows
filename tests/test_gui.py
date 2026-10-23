"""离屏渲染：至少证明窗口能构造、六个页面都能画出来、快照能驱动界面。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="需要 PySide6")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application


def test_window_renders_every_page(app):
    from a6700win.gui import window as window_module
    from a6700win.gui.pages import Page

    main = window_module.MainWindow("physical")
    try:
        main.resize(1180, 800)
        main.show()
        app.processEvents()

        snapshot = main.controller.snapshot()
        assert snapshot["phase"] == "notice"
        for key in ("notice", "preparation", "home", "result", "driver", "about"):
            main.goto(key)
            app.processEvents()
            page = main.stack.currentWidget()
            assert isinstance(page, Page)
            assert page.width() > 400 and page.height() > 300
            assert not page.grab().isNull()
    finally:
        main.controller.end_session()
        main.close()


def test_feature_rows_refresh_state_in_place(app):
    """写入后同一批功能的状态会变，行必须就地更新，不能只按 id 重建。"""
    from a6700win.gui.pages import HomePage

    class Stub:
        controller = None

        def call_controller(self, fn):
            return None

        def goto(self, key):
            return None

        def operate(self, *args, **kwargs):
            return None

        def select_features(self, mode):
            return None

        def refresh(self):
            return None

    page = HomePage(Stub())

    def snapshot(state):
        return dict(phase="home", compatible=True, busy=False, connected=True, backups=[],
                    backup_dir="x", simulation=False,
                    inspect_summary=dict(compatible=True, read_sectors=260, read_bytes=133120, features=[]),
                    features=[dict(id="sound", name="电子快门声音", state=state, available=True,
                                   selected=False, limits=[])])

    page.render(snapshot("enabled"))
    row = page.feature_rows["sound"]
    assert "已开启" in row.pill.text()
    page.render(snapshot("disabled"))
    assert page.feature_rows["sound"] is row, "同一批功能不应重建行"
    assert "已关闭" in row.pill.text()
