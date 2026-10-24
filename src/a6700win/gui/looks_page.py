# -*- coding: utf-8 -*-
"""自定义外观页：把四个菜单项换成 CC / NC / 理光正片 / 理光负片 的配色。"""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import looks as looks_mod
from . import theme
from .pages import Page
from .widgets import Card, Divider, LogBox, Pill, WrapLabel, reset_layout

STATE_TEXT = {
    "installed": ("已写入配方", theme.SUCCESS),
    "factory": ("出厂外观", theme.TEXT_FAINT),
    "other": ("已被其它改动", theme.WARNING),
}


class LooksPage(Page):
    title = "自定义外观"
    subtitle = "把 PT / NT / VV / VV2 四个菜单项换成富士与理光的配色；只改颜色记录，不碰固件。"

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)

        self.intro = Card("这一页会做什么")
        body = WrapLabel(
            "四个菜单项的色度记录会被换成下面这套配方：PT → Classic Chrome、"
            "NT → Classic Negative、VV → 理光正片、VV2 → 理光负片。"
            "配方只改「颜色浓度与色相分布」，做不出富士那条 S 形影调曲线，"
            "所以观感接近但不是逐像素复刻；实测逐色相 RMS：CC 0.18、NC 0.17。"
        )
        body.setObjectName("Muted")
        self.intro.add(body)
        self.intro.add(Divider())
        warn = WrapLabel(
            "写入前请把相机切到「USB 存储（MSC）」模式，并保证只连这一台相机。"
            "写入只改运行时参数，要让它在关机后仍然存在，必须让相机正常关机一次"
            "（它会自己把参数写进 BACKUP.BIN）。全程不写固件，随时可以在本页还原。"
        )
        warn.setObjectName("Faint")
        self.intro.add(warn)
        self.root.addWidget(self.intro)

        self.state_card = Card("当前状态", "读取 CP 色度单元 0x02A40001")
        self.pills = QHBoxLayout()
        self.pills.setSpacing(8)
        self.pill_camera = Pill("尚未检测")
        self.pill_dirty = Pill("")
        self.pills.addWidget(self.pill_camera)
        self.pills.addWidget(self.pill_dirty)
        self.pills.addStretch(1)
        self.state_card.add_layout(self.pills)

        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(10)
        self.state_card.add_layout(self.rows_box)
        self.empty = QLabel("点击下面的「检测当前状态」读取相机。")
        self.empty.setObjectName("Muted")
        self.rows_box.addWidget(self.empty)
        self.rows: dict[str, dict] = {}
        self.root.addWidget(self.state_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.apply_button = QPushButton("写入配方")
        self.apply_button.setObjectName("Primary")
        self.apply_button.clicked.connect(self._apply)
        actions.addWidget(self.apply_button)
        self.restore_button = QPushButton("还原本页外观")
        self.restore_button.clicked.connect(self._restore)
        actions.addWidget(self.restore_button)
        self.detect_button = QPushButton("检测当前状态")
        self.detect_button.clicked.connect(self._detect)
        actions.addWidget(self.detect_button)
        actions.addStretch(1)
        self.root.addLayout(actions)

        self.log_card = Card("进度")
        self.log = LogBox()
        self.log_card.add(self.log)
        self.root.addWidget(self.log_card, 1)

    # ---------------------------------------------------------------- 渲染
    def render(self, snapshot: dict) -> None:
        report = getattr(self.app, "looks_state", None)
        simulation = bool(snapshot.get("simulation"))
        busy = bool(snapshot.get("busy"))
        if report is None:
            self.pill_camera.set_state("尚未检测", theme.TEXT_FAINT)
            self.pill_dirty.set_state("", theme.TEXT_FAINT)
        else:
            installed = sum(1 for row in report.get("looks", []) if row.get("state") == "installed")
            self.pill_camera.set_state(
                f"已写入 {installed}/{len(report.get('looks', []))}", theme.SUCCESS if installed else theme.TEXT_MUTED)
            moved = report.get("moved") or []
            self.pill_dirty.set_state(
                f"其它记录有变化：bank {moved}" if moved else "其它记录未被改动",
                theme.WARNING if moved else theme.TEXT_FAINT)
            self._render_rows(report.get("looks") or [])
        enabled = not busy and not simulation
        for button in (self.apply_button, self.restore_button, self.detect_button):
            button.setEnabled(enabled)
        if simulation:
            hint = "演示模式下不会接触相机，请用真实设备模式。"
        else:
            hint = "需要相机处于 USB 存储（MSC）模式。"
        self.apply_button.setToolTip(hint if simulation else "写入四条色度记录并回读校验。")
        self.restore_button.setToolTip(hint if simulation else "把这四条记录还回出厂值，其它记录不动。")
        self.detect_button.setToolTip(hint if simulation else "只读读取，不改任何东西。")

    def _render_rows(self, rows: list[dict]) -> None:
        known = list(self.rows)
        if [str(row.get("name")) for row in rows] != known:
            for holder in self.rows.values():
                self.rows_box.removeWidget(holder["widget"])
                holder["widget"].setParent(None)
                holder["widget"].deleteLater()
            self.rows = {}
            for row in rows:
                widget = QWidget()
                grid = QGridLayout(widget)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setHorizontalSpacing(16)
                menu = QLabel(str(row.get("menu") or row.get("name")))
                menu.setMinimumWidth(210)
                menu.setStyleSheet("font-weight: 600;")
                grid.addWidget(menu, 0, 0)
                appearance = QLabel(str(row.get("name")))
                appearance.setObjectName("Muted")
                grid.addWidget(appearance, 0, 1)
                bank = QLabel(f"bank {row.get('bank')}")
                bank.setObjectName("Faint")
                grid.addWidget(bank, 0, 2)
                pill = Pill("")
                grid.addWidget(pill, 0, 3)
                grid.setColumnStretch(1, 1)
                self.rows_box.addWidget(widget)
                self.rows[str(row.get("name"))] = {"widget": widget, "pill": pill}
        self.empty.setVisible(not rows)
        for row in rows:
            holder = self.rows.get(str(row.get("name")))
            if holder is None:
                continue
            text, color = STATE_TEXT.get(str(row.get("state")), ("未知", theme.TEXT_FAINT))
            holder["pill"].set_state(text, color)

    # ---------------------------------------------------------------- 动作
    def _detect(self) -> None:
        self.app.run_task("检测外观状态", lambda progress: looks_mod.read_state(progress), self._detected)

    def _detected(self, report) -> None:
        self.app.looks_state = report or None
        rows = (report or {}).get("looks") or []
        installed = sum(1 for row in rows if row.get("state") == "installed")
        self.log.log(f"检测完成：{installed}/{len(rows)} 个外观已写入配方。")
        moved = (report or {}).get("moved") or []
        if moved:
            self.log.log(f"注意：这些记录不是出厂值：bank {moved}")
        self.app.refresh()

    def _apply(self) -> None:
        self.app.run_task("写入自定义外观", lambda progress: looks_mod.apply(progress), self._written)

    def _restore(self) -> None:
        self.app.run_task("还原自定义外观", lambda progress: looks_mod.restore(progress), self._written)

    def _written(self, report) -> None:
        rows = (report or {}).get("looks") or []
        parts = [f"{row.get('name')}={STATE_TEXT.get(str(row.get('state')), ('未知',))[0]}" for row in rows]
        self.log.log("结果：" + "，".join(parts))
        moved = (report or {}).get("moved") or []
        if moved:
            self.log.log(f"注意：这些与本页无关的记录也变了：bank {moved}")
        if (report or {}).get("wrote"):
            self.log.log("写入并回读通过。请正常关机一次，让它写进 BACKUP.BIN，再开机确认。")
        else:
            self.log.log("四条记录已经是目标状态，本次没有写入。")
        self._detect()
