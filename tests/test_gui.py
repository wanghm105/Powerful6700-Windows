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


class _StubApp:
    """GUI 测试用的最小 app：控制器调用一律返回 True，不碰真实设备。"""

    def __init__(self):
        self.step_keys = ["notice", "driver", "preparation", "home", "looks", "result"]
        self.step_titles = {"notice": "操作前须知", "driver": "驱动准备", "preparation": "相机准备",
                            "home": "功能管理", "looks": "自定义外观", "result": "操作结果"}
        self.snapshot = {}
        self.controller = _StubController()

    def call_controller(self, fn):
        return True

    def goto(self, key):
        return None

    def operate(self, *args, **kwargs):
        return None

    def select_features(self, mode):
        return None

    def refresh(self):
        return None

    def check_environment(self):
        return None

    def notify(self, *args, **kwargs):
        return None


class _StubController:
    def acknowledge_notice(self, value):
        return True

    def begin_preparation(self):
        return True


def test_notice_gates_check_on_acknowledgement(app):
    """勾选阅读确认之前不能启动检查；确认后提示变成「请先运行启动检查」。"""
    from a6700win.gui.pages import NoticePage

    page = NoticePage(_StubApp())
    page.key = "notice"
    base = dict(notice={}, busy=False, checked=False, notice_acknowledged=False, environment={})
    page.render(dict(base))
    assert page.ack.text() == "我已阅读，并了解适用范围与真实设备操作风险"
    assert not page.check_button.isEnabled(), "未勾选阅读确认时不应能启动检查"
    assert page.step_reason(base).startswith("请先勾选")

    acked = dict(base, notice_acknowledged=True)
    page.render(acked)
    assert page.check_button.isEnabled()
    assert page.step_reason(acked) == "请先运行启动检查。"

    ready = dict(acked, checked=True, environment={"ready": True, "checks": []})
    assert page.step_reason(ready) is None


def test_footer_reads_back_hint_next(app):
    """页脚顺序固定为：← 上一步 / 提示 / 下一步（下一步贴最右）。"""
    from a6700win.gui.pages import NoticePage

    page = NoticePage(_StubApp())
    page.key = "notice"
    page.update_steps(dict(busy=False, checked=False, notice_acknowledged=False, environment={}))
    page.resize(900, 600)
    page.show()
    app.processEvents()
    bar = page.footer.layout()
    widgets = [bar.itemAt(i).widget() for i in range(bar.count())]
    order = [index for index, widget in enumerate(widgets) if isinstance(widget, type(page.back_button))]
    assert order == sorted(order), "页脚部件顺序必须与代码顺序一致"
    names = [widget.text() if hasattr(widget, "text") else "" for widget in widgets if widget is not None]
    assert names[0].startswith("←"), names
    assert names[-1].startswith("下一步：驱动准备"), names
    positions = [widget.mapTo(page, widget.rect().topLeft()).x() for widget in widgets if widget is not None]
    assert positions == sorted(positions), f"页脚从左到右应为 上一步 → 提示 → 下一步，实际 {positions}"
    page.close()


def test_notice_acknowledge_sits_on_the_right(app):
    """阅读确认放在内容列右端：左边留白，右边缘贴住页面右边距。"""
    from a6700win.gui.pages import NoticePage

    page = NoticePage(_StubApp())
    page.key = "notice"
    page.render(dict(notice={}, busy=False, checked=False, notice_acknowledged=False, environment={}))
    page.resize(900, 700)
    page.show()
    app.processEvents()
    left = page.ack.mapTo(page, page.ack.rect().topLeft()).x()
    right = left + page.ack.width()
    assert left > page.width() / 2, f"阅读确认应靠右，实际 x={left} 页宽={page.width()}"
    assert abs(right - (page.width() - 30)) <= 2, f"阅读确认右边缘应贴住右边距，实际 {right}"
    page.close()
