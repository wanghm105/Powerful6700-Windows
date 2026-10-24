# -*- coding: utf-8 -*-
"""自定义外观页：把四个菜单项换成 CC / NC / 理光正片 / 理光负片 的配色。"""
from __future__ import annotations

from PySide6.QtCore import Qt
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
    step = 5
    subtitle = "把 PT / NT / VV / VV2 四个槽位换成富士与理光的胶片配色；只改颜色记录，可逐字节还原。"

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)

        self.intro = Card("这一页会做什么")
        body = WrapLabel(
            "相机里有 16 个外观槽位（10 个内建 + 6 个自定义）。本页改写其中四个内建槽位的颜色记录 —— "
            "CP 色度单元 0x02A40001 里的 bank 1 / 4 / 6 / 14，每条 64 字节 —— "
            "把它们的配色换成富士与理光的四款胶片外观。只改「颜色浓度与色相分布」，"
            "不改影调曲线，也不改菜单文字。"
        )
        body.setObjectName("Muted")
        self.intro.add(body)
        self.intro.add(Divider())
        self.intro.add_layout(self._mapping_table())
        note = WrapLabel(
            "菜单里显示的文字由 /usr 的语言资源决定，改名是单独的一步，本页不碰；"
            "写入前请把相机切到「USB 存储（MSC）」模式，只连这一台相机，全程不断线。"
        )
        note.setObjectName("Faint")
        self.intro.add(note)
        self.root.addWidget(self.intro)

        self.restore_card = Card("能不能无损还原")
        verdict = WrapLabel("能：四条颜色记录逐字节写回出厂值，不留下任何固件改动。")
        verdict.setObjectName("Verdict")
        self.restore_card.add(verdict)
        self._facts(self.restore_card, (
            ("还原做什么", "把 bank 1 / 4 / 6 / 14 写回配方文件里的出厂 64 字节（factory_hex），"
                     "随后整单元回读校验；其余 28 条记录一个字节都不动。"),
            ("不写什么", "全程只写 CP 运行时单元，不碰任何固件分区（/cp、/usr、appFw 都不写），"
                    "所以不存在刷坏固件的风险，也不需要固件包。"),
            ("怎么算完成", "点「还原本页外观」→ 再点「检测当前状态」，四条都显示「出厂外观」→ "
                     "正常关机一次再开机（相机会在关机时把当前 RAM 写进 /setting/BACKUP.BIN）。"),
            ("什么会白做", "写入或还原后直接拔电池、断电，RAM 会丢回上一次落盘的副本，"
                     "开机看到的仍是旧状态。"),
        ))
        self.root.addWidget(self.restore_card)

        self.fit_card = Card("拟合到什么程度")
        self._facts(self.fit_card, (
            ("参考数据", "A7C2 项目的 19 张真实直出对照图（6 个场景 × 3 组四宫格，"
                    "只做过缩放与拼接，没有任何曝光、白平衡或色彩调整）。"),
            ("做法", "每个外观按 12 个 30° 色相档取色度中位数，与本机同场景样张对齐，再用"
                 "「基底记录 × 系数 + 第 2 组 (Cb,Cr) 缩放」拟合。RMS 是 12 档「实测 / 目标」的"
                 "均方根误差，越低越接近。"),
            ("结果", "CC 0.183、NC 0.173（中段八档误差 0.03–0.09）；PF 0.189、NF 0.330 —— "
                 "PF / NF 只做到低饱和近似，不是逐像素复刻。"),
            ("硬边界", "① 蓝端 0–30° 与 330–360° 压不下来（CC 实测 0.95 / 1.06，目标 0.77 / 0.53）；"
                  "② 本机型只有 12 组 (Cb,Cr) 和一个宽把手，做不出 NC 的窄品红缺口与 PF / NF 的局部反向；"
                  "③ 富士的 S 形影调曲线没有对应图层，只复刻颜色浓度与色相分布。"),
        ))
        self.root.addWidget(self.fit_card)

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
        actions.addStretch(1)
        self.detect_button = QPushButton("检测当前状态")
        self.detect_button.setObjectName("Ghost")
        self.detect_button.clicked.connect(self._detect)
        actions.addWidget(self.detect_button)
        self.restore_button = QPushButton("还原本页外观")
        self.restore_button.clicked.connect(self._restore)
        actions.addWidget(self.restore_button)
        self.apply_button = QPushButton("写入配方")
        self.apply_button.setObjectName("Primary")
        self.apply_button.clicked.connect(self._apply)
        actions.addWidget(self.apply_button)
        self.root.addLayout(actions)

        self.log_card = Card("进度")
        self.log = LogBox()
        self.log_card.add(self.log)
        self.root.addWidget(self.log_card, 1)

    # ---------------------------------------------------------------- 渲染
    def _facts(self, card: Card, rows) -> None:
        """键值式的说明列表：左侧名称、右侧正文，正文按列宽自动换行。"""
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0, 76)
        for row, (name, text) in enumerate(rows):
            label = QLabel(name)
            label.setObjectName("Faint")
            label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            body = WrapLabel(text)
            body.setObjectName("Muted")
            grid.addWidget(label, row, 0, Qt.AlignTop)
            grid.addWidget(body, row, 1)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)

    def _mapping_table(self) -> QGridLayout:
        table = QGridLayout()
        table.setHorizontalSpacing(20)
        table.setVerticalSpacing(8)
        for column, text in enumerate(("相机菜单槽位", "改写为", "颜色记录", "拟合 RMS")):
            head = QLabel(text)
            head.setObjectName("Faint")
            if column >= 2:
                head.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.addWidget(head, 0, column)
        try:
            items = looks_mod.profile()
        except looks_mod.LooksError:
            items = []
        for row, item in enumerate(items, start=1):
            slot = QLabel(str(item.get("slot") or item.get("menu") or ""))
            slot.setStyleSheet("font-weight: 600;")
            table.addWidget(slot, row, 0)
            table.addWidget(QLabel(str(item.get("label") or item["name"])), row, 1)
            bank = QLabel(f"bank {item['bank']}")
            bank.setObjectName("Faint")
            bank.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.addWidget(bank, row, 2)
            rms = item.get("rms")
            fit = QLabel(f"RMS {rms:.3f}" if isinstance(rms, (int, float)) else "近似")
            fit.setObjectName("Faint")
            fit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.addWidget(fit, row, 3)
        table.setColumnStretch(1, 1)
        return table

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
                slot = str(row.get("slot") or "")
                label = str(row.get("label") or row.get("name") or "")
                menu = QLabel(f"{slot} → {label}" if slot else label)
                menu.setMinimumWidth(300)
                menu.setStyleSheet("font-weight: 600;")
                grid.addWidget(menu, 0, 0)
                bank = QLabel(f"bank {row.get('bank')}")
                bank.setObjectName("Faint")
                grid.addWidget(bank, 0, 1)
                rms = row.get("rms")
                fit = QLabel(f"RMS {rms:.3f}" if isinstance(rms, (int, float)) else "")
                fit.setObjectName("Faint")
                grid.addWidget(fit, 0, 2)
                pill = Pill("")
                grid.addWidget(pill, 0, 3)
                grid.setColumnStretch(0, 1)
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
        self.app.run_task("写入自定义外观", lambda progress: looks_mod.apply(progress),
                          lambda report: self._written(report, restoring=False))

    def _restore(self) -> None:
        self.app.run_task("还原自定义外观", lambda progress: looks_mod.restore(progress),
                          lambda report: self._written(report, restoring=True))

    def _written(self, report, restoring: bool = False) -> None:
        rows = (report or {}).get("looks") or []
        parts = [f"{row.get('name')}={STATE_TEXT.get(str(row.get('state')), ('未知',))[0]}" for row in rows]
        self.log.log("结果：" + "，".join(parts))
        moved = (report or {}).get("moved") or []
        if moved:
            self.log.log(f"注意：这些与本页无关的记录也变了：bank {moved}")
        if (report or {}).get("wrote"):
            if restoring:
                self.log.log("已还原并回读通过。请正常关机一次，再开机让相机把它写进 BACKUP.BIN。")
            else:
                self.log.log("写入并回读通过。请正常关机一次，让它写进 BACKUP.BIN，再开机确认。")
        elif restoring:
            self.log.log("四条记录已经是出厂状态，本次没有写入。")
        else:
            self.log.log("四条记录已经是目标状态，本次没有写入。")
        self._detect()
