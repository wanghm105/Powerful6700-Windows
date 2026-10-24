"""主窗口：左侧导航 + 内容栈 + 状态条。"""
from __future__ import annotations

import traceback

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..app import build_controller
from ..version import APP_TITLE, APP_VERSION
from . import theme
from .about_page import AboutPage
from .driver_page import DriverPage
from .looks_page import LooksPage
from .pages import HomePage, NoticePage, PreparationPage, ResultPage
from .worker import Task

# 导航顺序即操作顺序：先把驱动绑好，再准备相机、做只读检查、改功能或外观，最后看结果。
# 编号是给第一次上手的人看的；关于与诊断不参与线性流程，所以没有编号。
NAV = [
    ("notice", "操作前须知", "1"),
    ("driver", "驱动准备", "2"),
    ("preparation", "相机准备", "3"),
    ("home", "功能管理", "4"),
    ("looks", "自定义外观", "5"),
    ("result", "操作结果", "6"),
    ("about", "关于与诊断", ""),
]


class NavButton(QPushButton):
    def __init__(self, key: str, text: str, index: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        prefix = f"{index}  " if index else ""
        self.setText(f"{prefix}{text}")
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 8px;"
            f" padding: 9px 12px; text-align: left; color: {theme.TEXT_MUTED}; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {theme.SURFACE}; color: {theme.TEXT}; }}"
            f"QPushButton:checked {{ background: {theme.ACCENT_SOFT}; color: {theme.ACCENT}; font-weight: 600; }}"
        )


class MainWindow(QMainWindow):
    def __init__(self, mode: str = "physical"):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.resize(1180, 800)
        self.setMinimumSize(1040, 720)
        self.setStyleSheet(theme.STYLESHEET)

        self.controller = build_controller(mode)
        self.snapshot: dict = {}
        self.driver_report: dict = {}
        self.looks_state: dict | None = None
        self.task: Task | None = None
        self._pending_done = None

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.pages = {
            "notice": NoticePage(self),
            "preparation": PreparationPage(self),
            "home": HomePage(self),
            "looks": LooksPage(self),
            "result": ResultPage(self),
            "driver": DriverPage(self),
            "about": AboutPage(self),
        }
        self.step_keys = [key for key, _text, index in NAV if index]
        self.step_titles = {key: text for key, text, _index in NAV}
        for key, page in self.pages.items():
            page.key = key
        for key, page in self.pages.items():
            self.stack.addWidget(page)
        right_layout.addWidget(self.stack, 1)
        right_layout.addWidget(self._build_status_bar())
        outer.addWidget(right, 1)

        self.refresh()
        self.goto("notice")

    # ---------------------------------------------------------------- 布局
    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(228)
        panel.setStyleSheet(f"QFrame {{ background: {theme.SURFACE}; border-right: 1px solid {theme.BORDER_SOFT}; }}")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 22, 16, 18)
        layout.setSpacing(6)

        brand = QLabel("Powerful6700")
        brand.setStyleSheet("font-size: 17px; font-weight: 700; color: #f2f4f8;")
        layout.addWidget(brand)
        sub = QLabel("Windows · A6700 工具")
        sub.setObjectName("Faint")
        layout.addWidget(sub)
        layout.addSpacing(16)

        self.nav_buttons: dict[str, NavButton] = {}
        for key, text, index in NAV:
            button = NavButton(key, text, index)
            button.clicked.connect(lambda _=False, k=key: self.goto(k))
            layout.addWidget(button)
            self.nav_buttons[key] = button
        layout.addStretch(1)
        self.side_mode = QLabel("")
        self.side_mode.setObjectName("Faint")
        self.side_mode.setWordWrap(True)
        layout.addWidget(self.side_mode)
        return panel

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"QFrame {{ background: {theme.SURFACE}; border-top: 1px solid {theme.BORDER_SOFT}; }}")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 18, 0)
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self.status_label, 1)
        self.revision_label = QLabel("")
        self.revision_label.setStyleSheet(f"color: {theme.TEXT_FAINT}; font-size: 12px;")
        layout.addWidget(self.revision_label)
        return bar

    # ---------------------------------------------------------------- 状态
    def refresh(self) -> None:
        self.snapshot = self.controller.snapshot()
        current = self.stack.currentWidget()
        busy = bool(self.snapshot.get("busy"))
        for key, button in self.nav_buttons.items():
            button.setEnabled(not busy or key == current)
        page = self.pages.get(self._current_key())
        if page is not None:
            try:
                page.render(self.snapshot)
                page.update_steps(self.snapshot)
            except Exception:  # noqa: BLE001 - 渲染问题不应崩溃
                traceback.print_exc()
        mode = "演示模式" if self.snapshot.get("simulation") else "真实设备模式"
        self.side_mode.setText(f"{mode}\n阶段：{self.snapshot.get('phase', '')}")
        self.revision_label.setText(f"rev {self.snapshot.get('revision', 0)}")
        if busy:
            self.status("操作进行中…", theme.WARNING)
        elif self.snapshot.get("compatible"):
            self.status("只读检查通过，可以选择功能", theme.SUCCESS)
        elif self.snapshot.get("ready"):
            self.status("相机准备就绪，可开始只读检查", theme.TEXT_MUTED)

    def _current_key(self) -> str:
        widget = self.stack.currentWidget()
        for key, page in self.pages.items():
            if page is widget:
                return key
        return "notice"

    def goto(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        if self.task is not None and self.task.isRunning() and key != self._current_key():
            self.notify("操作进行中，请等待完成。", error=True)
            return
        self.stack.setCurrentWidget(page)
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        self.refresh()

    def status(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def notify(self, message: str, error: bool = False) -> None:
        self.status(message, theme.DANGER if error else theme.ACCENT)
        page = self.stack.currentWidget()
        box = getattr(page, "log", None)
        if box is not None:
            box.log(("✕ " if error else "· ") + message)

    def _log_progress(self, message: str) -> None:
        self.status(message, theme.TEXT_MUTED)
        page = self.stack.currentWidget()
        box = getattr(page, "log", None)
        if box is not None:
            box.log(message)

    def open_url(self, url: str) -> None:
        if url:
            QDesktopServices.openUrl(QUrl(url))

    # ---------------------------------------------------------------- 控制器
    def call_controller(self, fn):
        try:
            result = fn()
        except ValueError as exc:
            self.notify(str(exc), error=True)
            return None
        except Exception as exc:  # noqa: BLE001 - 控制器异常统一提示
            traceback.print_exc()
            self.notify(f"{exc.__class__.__name__}: {exc}", error=True)
            return None
        self.refresh()
        return result

    def select_features(self, mode: str) -> None:
        self.call_controller(lambda: self.controller.select_features(mode))

    def check_environment(self) -> None:
        if self._busy():
            return
        self.goto("notice")
        self.run_task("启动检查", lambda progress: self.controller.check_environment(),
                      lambda _result: self._after_environment())

    def _after_environment(self) -> None:
        ready = bool(self.snapshot.get("environment", {}).get("ready"))
        if ready:
            self.notify("启动检查通过，请勾选阅读确认后进入相机准备。")
        else:
            self.notify("启动检查未通过，请按提示处理后重试。", error=True)

    def operate(self, action: str, backup_id: str | None = None) -> None:
        if self._busy():
            self.notify("已有操作在进行。", error=True)
            return
        try:
            self.controller.reserve(action, backup_id)
        except ValueError as exc:
            self.notify(str(exc), error=True)
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.notify(f"{exc.__class__.__name__}: {exc}", error=True)
            return
        self.refresh()
        label = {"inspect": "只读检查", "unlock": "解锁功能", "close": "关闭功能",
                 "backup": "功能状态备份", "restore": "功能状态恢复"}.get(action, action)
        self.run_task(label, lambda progress: self.controller.run_reserved(progress),
                      lambda _result: self._after_operation(action))

    def _after_operation(self, action: str) -> None:
        phase = self.snapshot.get("phase")
        if action == "inspect" and phase == "home":
            self.goto("home")
            self.notify("只读检查完成，可以管理功能。")
        elif phase == "result":
            self.goto("result")

    def _busy(self) -> bool:
        return bool(self.task is not None and self.task.isRunning())

    def run_task(self, label: str, fn, on_done=None) -> None:
        if self._busy():
            self.notify("已有任务在执行。", error=True)
            return
        task = Task(label, fn, parent=self, cancel=self.controller.cancel_operation)
        task.progressed.connect(self._log_progress)
        task.succeeded.connect(lambda result: self._task_done(task, on_done, result, None))
        task.failed.connect(lambda message: self._task_done(task, on_done, None, message))
        task.cancelled.connect(lambda: self._task_done(task, on_done, None, "操作已取消"))
        task.finished.connect(lambda: self._task_finished(task))
        self.task = task
        self.status(f"{label}…", theme.WARNING)
        task.start()

    def _task_done(self, task: Task, on_done, result, error: str | None) -> None:
        # 信号已经带着结果到达，任务逻辑上结束：先清 self.task，回调里才能 goto()
        # （goto 会拒绝“操作进行中”时的跳转，之前写入成功后就停在了功能管理页）。
        if self.task is task:
            self.task = None
        # 先刷新再回调：回调里的判断（例如环境是否就绪）必须读到本次操作的结果，
        # 否则 snapshot 还停在操作前的状态，提示会自相矛盾。
        self.refresh()
        if error is not None:
            self.notify(f"{task.label}：{error}", error=error != "操作已取消")
        if not error and on_done is not None:
            try:
                on_done(result)
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    def _task_finished(self, task: Task) -> None:
        if self.task is task:
            self.task = None
        self.refresh()

    # ---------------------------------------------------------------- 关闭
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._busy():
            answer = QMessageBox.question(
                self, "操作尚未结束", "当前操作仍在进行，关闭窗口可能中断写入。确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.task.request_cancel()
            self.task.wait(5000)
        try:
            self.controller.end_session()
        except Exception:  # noqa: BLE001 - 关闭时尽力释放
            traceback.print_exc()
        event.accept()


def run(mode: str = "physical") -> int:
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow(mode)
    window.show()
    return app.exec()
