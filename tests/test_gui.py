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
        self.confirms: list[str] = []
        self.confirm_texts: list[str] = []
        self.urls: list[str] = []
        self.controller = _StubController()

    def call_controller(self, fn):
        return True

    def goto(self, key):
        return None

    def open_url(self, url):
        self.urls.append(url)
        return None

    def confirm_write(self, action, text):
        self.confirms.append(action)
        self.confirm_texts.append(text)
        return True

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


def test_driver_page_blocks_next_until_bound(app):
    """没装驱动就放行下一步，只读检查只会报“找不到 MSC 相机”。"""
    from a6700win.gui.driver_page import DriverPage

    stub = _StubApp()
    page = DriverPage(stub)
    assert "查找相机" in page.step_reason({})

    stub.driver_report = dict(devices=[dict(pid=0x0E76, winusb=False)])
    assert "驱动" in page.step_reason({})

    stub.driver_report = dict(devices=[dict(pid=0x0E76, winusb=True)])
    assert page.step_reason({}) is None


def test_looks_page_releases_controller_session(app):
    """只读检查的会话还开着时，外观页必须先退掉它，否则会撞设备锁。"""
    from a6700win.gui.looks_page import LooksPage

    stub = _StubApp()
    ended = []
    stub.controller = type("C", (), {
        "service": type("S", (), {"connected": True})(),
        "end_session": lambda self: ended.append(True),
    })()
    stub.call_controller = lambda fn: fn()
    page = LooksPage(stub)
    page._release_controller_session()
    assert ended == [True]


def test_bundle_apply_is_locked_until_acknowledged(app):
    """「一次做完」会写相机固件里的文件：不勾确认点不动，运行前再弹一次确认，之后自动锁回去。"""
    from a6700win.gui.looks_page import LooksPage

    stub = _StubApp()
    started = []
    stub.run_task = lambda title, task, done: started.append(title)
    stub.looks_state = None
    page = LooksPage(stub)
    page.render(dict(busy=False, simulation=False))
    assert not page.bundle_apply_button.isEnabled(), "默认必须是锁着的"
    assert page.bundle_apply_button.objectName() == "Ghost", "不该再是主按钮的样子"
    assert page.bundle_restore_button.isEnabled(), "还原是退路，不能一起锁死"

    page._bundle_apply()
    assert started == [], "锁着的时候不能真去写"

    page.bundle_ack.setChecked(True)
    assert page.bundle_apply_button.isEnabled()

    page._bundle_apply()
    assert started == ["一次做完（颜色 + 名字）"]
    assert stub.confirms == ["一次做完（颜色 + 名字）"], "真写之前必须再确认一次"
    assert not page.bundle_apply_button.isEnabled(), "写一次之后要重新确认，不留在解锁状态"


def test_confirm_write_states_target_bytes_and_rollback(app):
    """写入前的确认框必须说清楚写哪里、多少字节、怎么回滚，不能只讲不能拔线。"""
    from a6700win.gui.looks_page import LooksPage

    stub = _StubApp()
    page = LooksPage(stub)
    page.names_report = dict(bytes=145612)

    assert page._confirm_write("写入颜色")
    color = stub.confirm_texts[-1]
    assert "颜色参数区" in color and "8,192" in color, color
    assert "还原颜色" in color, "回滚方式要写清楚怎么退回去"
    assert "中断后果" in color and "拔数据线" in color

    assert page._confirm_write("写入菜单名字")
    names = stub.confirm_texts[-1]
    assert "string_simplifiedchinese_f.uxc" in names and "145,612" in names, names
    assert "把名字改回去" in names

    assert page._confirm_write("一次做完（颜色 + 名字）")
    both = stub.confirm_texts[-1]
    assert "8,192" in both and "145,612" in both, both


def test_failed_result_gives_three_step_rescue(app):
    """失败结果页先给三步自救，而不是让用户自己猜着再试一遍。"""
    from a6700win.gui import pages

    page = pages.ResultPage(_StubApp())
    page.render({"result": {"status": "失败", "success": False, "write_attempted": True}})
    assert not page.rescue_card.isHidden(), "失败时必须出现自救卡"
    texts = [page.rescue_body.itemAt(i).widget().text()
             for i in range(page.rescue_body.count())
             if page.rescue_body.itemAt(i).widget() is not None]
    assert any("拔掉数据线" in text for text in texts)
    assert any("1 分钟" in text for text in texts)
    assert any("不要连续重试" in text for text in texts)
    assert page.rescue_link.text() == "硬件说明（救砖）↗"

    page.render({"result": {"status": "完成", "success": True}})
    assert page.rescue_card.isHidden(), "成功时不该出现自救卡"


def test_notice_gates_check_on_acknowledgement(app):
    """勾选阅读确认之前不能启动检查；确认后提示变成「先跑一次启动检查」。"""
    from a6700win.gui.pages import NoticePage

    page = NoticePage(_StubApp())
    page.key = "notice"
    base = dict(notice={}, busy=False, checked=False, notice_acknowledged=False, environment={})
    page.render(dict(base))
    assert page.ack.text() == "上面的说明我都看过，知道有风险，仍然继续"
    assert not page.check_button.isEnabled(), "未勾选阅读确认时不应能启动检查"
    assert page.step_reason(base).startswith("先勾上")

    acked = dict(base, notice_acknowledged=True)
    page.render(acked)
    assert page.check_button.isEnabled()
    assert page.step_reason(acked) == "先跑一次启动检查。"

    ready = dict(acked, checked=True, environment={"ready": True, "checks": []})
    assert page.step_reason(ready) is None


def test_notice_links_the_upstream_hardware_recovery_guide(app):
    """连电脑都认不出来时软件这边没有退路，首屏必须给出上游的硬件说明入口。"""
    from a6700win.gui.pages import NoticePage
    from a6700win.gui.widgets import DocLink
    from a6700win.notices import HARDWARE_RECOVERY_URL

    stub = _StubApp()
    page = NoticePage(stub)
    page.key = 'notice'
    page.render(dict(notice={}, busy=False, checked=False,
                     notice_acknowledged=False, environment={}))
    links = [w for w in page.findChildren(DocLink) if '硬件' in w.text()]
    assert links, '首屏没有硬件恢复说明的链接'
    links[0].clicked.emit()
    assert stub.urls == [HARDWARE_RECOVERY_URL]


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
    card_right = page.env_card.mapTo(page, page.env_card.rect().topRight()).x()
    margin = card_right - right
    assert 0 <= margin <= 24, f"阅读确认应贴住卡片内容右缘，实际留白 {margin}"
    page.close()


def test_blocked_result_shows_issue_offsets_and_can_be_copied(app):
    """被结构守卫拦下时，界面要能说出偏移；之前只有一个 status=blocked。"""
    from a6700win.gui import window as window_module

    issues = [
        {"kind": "sector-guard-mismatch", "index": 9, "device": "0",
         "offset": 0x02844000, "role": "guard"},
        {"kind": "unknown-field", "edit_id": "ftp", "image": "appFw",
         "offset": 0x00100004, "actual": "ff"},
    ]
    result = {"status": "blocked", "device_access": True, "write_attempted": False,
              "run_directory": "C:/runs/x",
              "plan": {"compatible": False, "read_sectors": 260, "read_bytes": 133120,
                       "issues": issues}}
    main = window_module.MainWindow("physical")
    try:
        main.show()
        pages = main.pages
        pages["result"].render({"result": result})
        app.processEvents()
        card = pages["result"].issues_card
        assert not card.isHidden()
        assert "2 处" in card.title_label.text()
        texts = [pages["result"].issues_body.itemAt(i).widget().text()
                 for i in range(pages["result"].issues_body.count())
                 if pages["result"].issues_body.itemAt(i).widget() is not None]
        assert any("0x02844000" in text for text in texts)
        assert any("C:/runs/x" in text for text in texts)

        pages["home"].render({"result": result, "features": [], "busy": False})
        app.processEvents()
        assert not pages["home"].blocked_hint.isHidden()
        assert "2 处对不上" in pages["home"].blocked_hint.text()
    finally:
        main.controller.end_session()
        main.close()


def test_home_backup_dir_button_opens_the_folder(app, tmp_path):
    """「打开备份目录」：按 render 里给的目录打开，不用用户自己找路径。"""
    from PySide6.QtCore import QUrl

    from a6700win.gui import pages

    stub = _StubApp()
    target = tmp_path / "backups"
    page = pages.HomePage(stub)
    page.render(dict(backup_dir=str(target), backups=[], busy=False, connected=False,
                     compatible=False))
    assert page.open_backup_button.isEnabled()
    page._open_backup_dir()
    assert stub.urls == [QUrl.fromLocalFile(str(target)).toString()]
    assert target.is_dir(), "先建好目录再打开，否则资源管理器会弹一个找不到路径的框"
