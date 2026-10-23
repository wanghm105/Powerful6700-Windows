"""关于与诊断页。"""
from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..version import APP_TITLE, APP_VERSION, UPSTREAM_NOTE
from . import theme
from .pages import Page
from .widgets import Card, DocLink, LogBox


class AboutPage(Page):
    title = "关于"
    subtitle = f"{APP_TITLE} · {APP_VERSION}"

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        root = self.root

        self.info_card = Card("项目说明")
        note = QLabel(UPSTREAM_NOTE)
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.info_card.add(note)
        links = QHBoxLayout()
        links.setSpacing(18)
        upstream = DocLink("上游项目 sony-a6700-powerful ↗")
        upstream.clicked.connect(lambda: self.app.open_url(
            "https://github.com/xyzhangxin/sony-a6700-powerful"))
        links.addWidget(upstream)
        license_link = DocLink("GPL-3.0 许可证 ↗")
        license_link.clicked.connect(lambda: self.app.open_url(
            "https://www.gnu.org/licenses/gpl-3.0.html"))
        links.addWidget(license_link)
        links.addStretch(1)
        self.info_card.add_layout(links)
        root.addWidget(self.info_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.diag_button = QPushButton("环境诊断")
        self.diag_button.clicked.connect(self._diagnose)
        actions.addWidget(self.diag_button)
        self.selftest_button = QPushButton("运行离线自检")
        self.selftest_button.setObjectName("Primary")
        self.selftest_button.clicked.connect(self._selftest)
        actions.addWidget(self.selftest_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.output_card = Card("诊断输出")
        self.output = LogBox(max_lines=800)
        self.output_card.add(self.output)
        root.addWidget(self.output_card, 1)

    def render(self, snapshot: dict) -> None:
        return

    def _diagnose(self) -> None:
        from .. import patches

        try:
            status = patches.status()
        except Exception as exc:  # noqa: BLE001 - 诊断不应抛界面异常
            self.output.log(f"诊断失败：{exc}")
            return
        self.output.log(json.dumps(status, ensure_ascii=False, indent=2, default=str))

    def _selftest(self) -> None:
        from .. import selftest

        try:
            report = selftest.run()
        except Exception as exc:  # noqa: BLE001 - 自检失败要展示而不是崩溃
            self.output.log(f"自检异常：{exc}")
            return
        for item in report.get("checks", []):
            mark = "OK  " if item.get("ok") else ("SKIP" if item.get("optional") else "FAIL")
            self.output.log(f"{mark} {item.get('id', ''):<12} {item.get('detail', '')}")
        self.output.log(f"结果：{'通过' if report.get('ok') else '未通过'}")
