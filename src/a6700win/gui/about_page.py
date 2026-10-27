"""关于与诊断页。"""
from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..notices import HARDWARE_RECOVERY_URL
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
        hardware = DocLink("硬件说明（救砖）↗")
        hardware.clicked.connect(lambda: self.app.open_url(HARDWARE_RECOVERY_URL))
        links.addWidget(hardware)
        license_link = DocLink("GPL-3.0 许可证 ↗")
        license_link.clicked.connect(lambda: self.app.open_url(
            "https://www.gnu.org/licenses/gpl-3.0.html"))
        links.addWidget(license_link)
        links.addStretch(1)
        self.info_card.add_layout(links)
        root.addWidget(self.info_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        self.diag_button = QPushButton("环境诊断")
        self.diag_button.setObjectName("Ghost")
        self.diag_button.clicked.connect(self._diagnose)
        actions.addWidget(self.diag_button)
        self.export_button = QPushButton("导出诊断包")
        self.export_button.setObjectName("Ghost")
        self.export_button.clicked.connect(self._export_bundle)
        actions.addWidget(self.export_button)
        self.selftest_button = QPushButton("不接相机自检")
        self.selftest_button.setObjectName("Primary")
        self.selftest_button.clicked.connect(self._selftest)
        actions.addWidget(self.selftest_button)
        root.addLayout(actions)

        self.output_card = Card("诊断输出")
        self.output = LogBox(max_lines=800)
        self.output_card.add(self.output)
        root.addWidget(self.output_card, 1)

    def render(self, snapshot: dict) -> None:
        return

    def _export_bundle(self) -> None:
        """把版本、电脑环境、最近的结论和运行目录打成一个 zip；发 issue 时直接拖进去，不用来回问路径。"""
        from datetime import datetime
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        from .. import diagnostics, paths

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default = paths.documents_dir() / ("Powerful6700-诊断-%s.zip" % stamp)
        target, _ = QFileDialog.getSaveFileName(self, "保存诊断包", str(default), "Zip (*.zip)")
        if not target:
            return
        result = dict(self.app.snapshot.get("result") or {})
        try:
            path = diagnostics.export_bundle(result, Path(target))
        except OSError as exc:
            self.output.log("导出失败：%s" % exc)
            return
        self.output.log("已导出诊断包：%s" % path)
        self.output.log("里面有 diagnostics.txt、environment.json，还有这次运行的原始记录，可以直接拖进 issue。")

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
