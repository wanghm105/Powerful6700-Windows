# -*- coding: utf-8 -*-
"""自定义外观页：把四个菜单项换成 CC / NC / 理光正片 / 理光负片 的配色与名字。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .. import cp, looknames, looks as looks_mod
from . import theme
from .pages import Page
from .widgets import Card, Divider, LogBox, Pill, WrapLabel, reset_layout

STATE_TEXT = {
    "installed": ("已写入配方", theme.SUCCESS),
    "factory": ("出厂外观", theme.TEXT_FAINT),
    "other": ("已被其它改动", theme.WARNING),
}

NAMES_STATE_TEXT = {
    "installed": ("已是目标文字", theme.SUCCESS),
    "factory": ("出厂短名", theme.TEXT_FAINT),
    "other": ("其它改动", theme.WARNING),
    "mixed": ("两条记录不一致", theme.WARNING),
    "missing": ("资源里没有这条", theme.WARNING),
}

KIND_TEXT = {
    "factory": "出厂资源",
    "factory-labels": "出厂短名",
    "renamed": "本项目名字",
    "other": "其它改动",
}


class LooksPage(Page):
    title = "自定义外观"
    step = 5
    subtitle = ("把 PT / NT / VV / VV2 四个槽位换成富士与理光的胶片配色；颜色记录与菜单文字分开写、"
                "分别可还原。")

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.names_report: dict | None = None
        self.names_error: str | None = None
        self.names_preset = looknames.load_preset()

        self.intro = Card("这一页会做什么")
        body = WrapLabel(
            "相机里有 16 个外观槽位（10 个内建 + 6 个自定义）。本页改写其中四个内建槽位的颜色记录 —— "
            "CP 色度单元 0x02A40001 里的 bank 1 / 4 / 6 / 14，每条 64 字节 —— "
            "把它们的配色换成富士与理光的四款胶片外观。只改「颜色浓度与色相分布」，"
            "不改影调曲线。"
        )
        body.setObjectName("Muted")
        self.intro.add(body)
        self.intro.add(Divider())
        self.intro.add_layout(self._mapping_table())
        note = WrapLabel(
            "菜单里显示的文字是另一份东西（/usr 里的语言资源文件），在下面的「菜单文字」里单独改写；"
            "两部分可以只做一半。写入前请把相机切到「USB 存储（MSC）」模式，只连这一台相机，全程不断线。"
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

        # ------------------------------------------------------------ 菜单文字
        self.names_card = Card("菜单文字", "改写 /usr 语言资源里的外观短名，可逐字节还原")
        names_note = WrapLabel(
            "颜色是运行时的数据，关机才落盘；菜单文字是固件里的一个文件，写下去就持久。"
            "所以这一步单独算：写入前程序会把整份语言资源（约 142 KB）存一份基线，"
            "还原时整份逐字节写回并比对哈希。本地没有基线时只能把文字改回出厂短名"
            "（PT / NT / VV / VV2）—— 下面的「基线」一行会说明当前能用到哪一档。"
            "叫法有两套可选：官方原名（Classic Chrome / Classic Neg. / Positive Film / "
            "Negative Film）和中文简称，写哪一套都还原得回来。"
        )
        names_note.setObjectName("Muted")
        self.names_card.add(names_note)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        preset_caption = QLabel("命名方案")
        preset_caption.setObjectName("Faint")
        preset_row.addWidget(preset_caption)
        self.names_preset_box = QComboBox()
        for item in looknames.preset_labels():
            self.names_preset_box.addItem(item["label"], item["key"])
        self.names_preset_box.setToolTip("只影响「菜单文字」写成哪一套叫法，颜色记录不受影响。")
        current = self.names_preset_box.findData(self.names_preset)
        self.names_preset_box.setCurrentIndex(max(0, current))
        self.names_preset_box.currentIndexChanged.connect(self._preset_changed)
        preset_row.addWidget(self.names_preset_box)
        self.preset_hint = QLabel("")
        self.preset_hint.setObjectName("Faint")
        preset_row.addWidget(self.preset_hint)
        preset_row.addStretch(1)
        self.names_card.add_layout(preset_row)
        self._sync_preset_hint()

        self.names_card.add(Divider())
        self.names_card.add_layout(self._names_table())
        baseline_row = QHBoxLayout()
        baseline_row.setSpacing(8)
        caption = QLabel("基线")
        caption.setObjectName("Faint")
        baseline_row.addWidget(caption)
        self.baseline_pill = Pill("尚未检查")
        baseline_row.addWidget(self.baseline_pill)
        self.baseline_detail = QLabel("")
        self.baseline_detail.setObjectName("Faint")
        baseline_row.addWidget(self.baseline_detail)
        baseline_row.addStretch(1)
        self.names_card.add_layout(baseline_row)
        name_actions = QHBoxLayout()
        name_actions.setSpacing(10)
        self.names_import_button = QPushButton("导入基线…")
        self.names_import_button.setObjectName("Ghost")
        self.names_import_button.clicked.connect(self._import_baseline)
        name_actions.addWidget(self.names_import_button)
        name_actions.addStretch(1)
        self.names_restore_button = QPushButton("还原菜单文字")
        self.names_restore_button.clicked.connect(self._restore_names)
        name_actions.addWidget(self.names_restore_button)
        self.names_apply_button = QPushButton("写入菜单文字")
        self.names_apply_button.setObjectName("Primary")
        self.names_apply_button.clicked.connect(self._apply_names)
        name_actions.addWidget(self.names_apply_button)
        self.names_card.add_layout(name_actions)
        self.root.addWidget(self.names_card)

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

    def _names_table(self) -> QGridLayout:
        """菜单文字的四行：槽位、相机上现在显示什么、要写成什么、状态。"""
        table = QGridLayout()
        table.setHorizontalSpacing(20)
        table.setVerticalSpacing(8)
        for column, text in enumerate(("相机菜单槽位", "当前文字", "目标文字", "")):
            head = QLabel(text)
            head.setObjectName("Faint")
            table.addWidget(head, 0, column)
        self.name_rows: dict[str, dict] = {}
        try:
            rows = looknames.targets(self.names_preset)
        except (looknames.LookNamesError, looks_mod.LooksError):
            rows = []
        for index, row in enumerate(rows, start=1):
            slot = QLabel(str(row.get("label") or row["slot"]))
            slot.setStyleSheet("font-weight: 600;")
            table.addWidget(slot, index, 0)
            current = QLabel("未检测")
            current.setObjectName("Muted")
            current.setMinimumWidth(150)
            table.addWidget(current, index, 1)
            target = QLabel(row["text"])
            target.setObjectName("Muted")
            table.addWidget(target, index, 2)
            pill = Pill("")
            table.addWidget(pill, index, 3)
            self.name_rows[row["slot"]] = {"current": current, "target_label": target, "pill": pill,
                                           "variants": row.get("variants") or {}}
        table.setColumnStretch(1, 1)
        if not rows:
            missing = QLabel("读不到 docs/looks-profile.json 里的 menu_slot / menu_names。")
            missing.setObjectName("Warning")
            table.addWidget(missing, 1, 0, 1, 4)
        return table

    def _sync_preset_hint(self) -> None:
        meta = looknames.PRESETS.get(self.names_preset) or {}
        self.preset_hint.setText(str(meta.get("note") or ""))

    def _preset_changed(self, _index: int) -> None:
        key = str(self.names_preset_box.currentData() or looknames.DEFAULT_PRESET)
        if key == self.names_preset:
            return
        self.names_preset = key
        try:
            looknames.save_preset(key)
        except looknames.LookNamesError:
            pass
        self._sync_preset_hint()
        self._render_names()
        self.log.log(f"命名方案切成「{(looknames.PRESETS.get(key) or {}).get('label', key)}」；"
                     "点「写入菜单文字」才会真正改写。")

    def _preset_target(self, row: dict) -> str:
        variants = row.get("variants") or {}
        return str(variants.get(self.names_preset) or row.get("target") or "")

    def _name_state(self, row: dict) -> tuple[str, str]:
        """按当前方案重算这一行的状态；current 是相机上的原文。"""
        current = str(row.get("current") or "")
        target = self._preset_target(row)
        slot = str(row.get("slot") or "")
        if not current or current.startswith("（"):
            return "missing", current
        if current == target:
            return "installed", current
        if current == slot:
            return "factory", current
        if " / " in current:
            return "mixed", current
        return "other", current

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
        self._render_names()
        enabled = not busy and not simulation
        for button in (self.apply_button, self.restore_button, self.detect_button,
                       self.names_apply_button, self.names_restore_button, self.names_import_button):
            button.setEnabled(enabled)
        if simulation:
            hint = "演示模式下不会接触相机，请用真实设备模式。"
        else:
            hint = "需要相机处于 USB 存储（MSC）模式。"
        self.apply_button.setToolTip(hint if simulation else "写入四条色度记录并回读校验。")
        self.restore_button.setToolTip(hint if simulation else "把这四条记录还回出厂值，其它记录不动。")
        self.detect_button.setToolTip(hint if simulation else "只读读取，不改任何东西。")
        self.names_apply_button.setToolTip(
            hint if simulation else "把四条外观的菜单文字改成当前命名方案（写 /usr 文件，持久）。")
        self.names_restore_button.setToolTip(
            hint if simulation else "有出厂基线就整份写回；没有就只把文字改回出厂短名。")
        self.names_import_button.setToolTip("导入一份出厂语言资源作为基线；不连接相机。")

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

    def _render_names(self) -> None:
        report = self.names_report
        if report is None:
            for holder in self.name_rows.values():
                holder["current"].setText("读取失败" if self.names_error else "未检测")
                holder["pill"].set_state("", theme.TEXT_FAINT)
            if self.names_error:
                self.baseline_pill.set_state("读取失败", theme.WARNING)
                self.baseline_detail.setText(self.names_error)
            else:
                self.baseline_pill.set_state("尚未检查", theme.TEXT_FAINT)
                self.baseline_detail.setText("")
            return
        by_slot = {str(row.get("slot")): row for row in report.get("looks") or []}
        for slot, holder in self.name_rows.items():
            row = by_slot.get(slot)
            if row is None:
                continue
            if row.get("variants"):
                holder["variants"] = row["variants"]
            merged = {"current": row.get("current"), "slot": slot,
                      "variants": holder["variants"], "target": row.get("target")}
            state, current = self._name_state(merged)
            holder["current"].setText(current or "—")
            holder["target_label"].setText(self._preset_target(merged) or "—")
            text, color = NAMES_STATE_TEXT.get(state, ("未知", theme.TEXT_FAINT))
            holder["pill"].set_state(text, color)
        baseline = report.get("baseline") or {}
        best = baseline.get("best") or {}
        if best:
            kind = KIND_TEXT.get(str(best.get("kind")), "基线")
            self.baseline_pill.set_state("可整份还原", theme.SUCCESS)
            self.baseline_detail.setText(
                f"{kind} · {int(best.get('bytes') or 0):,} 字节 · 存于 {best.get('saved_at') or ''}"
                f" · sha256 {str(best.get('sha256') or '')[:12]}…")
        else:
            self.baseline_pill.set_state("无出厂基线：只能改回短名", theme.WARNING)
            self.baseline_detail.setText(
                f"共 {baseline.get('count') or 0} 份 · {baseline.get('dir') or ''}")

    # ---------------------------------------------------------------- 动作
    def _release_controller_session(self) -> None:
        """同一台相机只能有一个 USB 会话；外观读写会自己重连，先把旧会话退掉。"""
        controller = getattr(self.app, "controller", None)
        service = getattr(controller, "service", None)
        if service is None or not getattr(service, "connected", False):
            return
        self.log.log("先退出只读检查保持的 USB 会话，释放接口后再连接相机…")
        self.app.call_controller(controller.end_session)
        self.app.refresh()

    def _detect(self) -> None:
        self._release_controller_session()
        self.app.run_task("检测外观状态", self._probe, self._detected)

    def _probe(self, progress) -> dict:
        """一次认证同时读颜色与菜单文字（两次认证会让相机来回切模式）。"""
        with cp.session(progress) as channel:
            colors = looks_mod.read_state(progress, channel=channel)
            names = None
            error = None
            try:
                names = looknames.read(progress, channel=channel, preset=self.names_preset)
            except Exception as exc:  # noqa: BLE001 - 文字读取失败不影响颜色结果
                error = str(exc)
        return {"colors": colors, "names": names, "names_error": error}

    def _detected(self, result) -> None:
        result = result or {}
        colors = result.get("colors")
        self.app.looks_state = colors
        self.names_report = result.get("names")
        self.names_error = result.get("names_error")
        rows = (colors or {}).get("looks") or []
        installed = sum(1 for row in rows if row.get("state") == "installed")
        self.log.log(f"检测完成：{installed}/{len(rows)} 个外观已写入配方。")
        moved = (colors or {}).get("moved") or []
        if moved:
            self.log.log(f"注意：这些记录不是出厂值：bank {moved}")
        if self.names_error:
            self.log.log(f"菜单文字读取失败：{self.names_error}")
        elif self.names_report:
            kind = KIND_TEXT.get(str(self.names_report.get("kind")), "未知")
            self.log.log(f"语言资源 {int(self.names_report.get('bytes') or 0):,} 字节，"
                         f"当前是「{kind}」。")
        self.app.refresh()

    def _apply(self) -> None:
        self._release_controller_session()
        self.app.run_task("写入自定义外观", lambda progress: looks_mod.apply(progress),
                          lambda report: self._written(report, restoring=False))

    def _restore(self) -> None:
        self._release_controller_session()
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

    def _apply_names(self) -> None:
        preset = self.names_preset
        label = (looknames.PRESETS.get(preset) or {}).get("label", preset)
        self._release_controller_session()
        self.log.log(f"按「{label}」写入菜单文字…")
        self.app.run_task("写入菜单文字",
                          lambda progress: looknames.apply(progress, preset=preset),
                          lambda report: self._names_done(report, "写入"))

    def _restore_names(self) -> None:
        preset = self.names_preset
        self._release_controller_session()
        self.app.run_task("还原菜单文字",
                          lambda progress: looknames.restore(progress, preset=preset),
                          lambda report: self._names_done(report, "还原"))

    def _names_done(self, report, action: str) -> None:
        report = report or {}
        self.names_report = report
        self.names_error = None
        changes = report.get("changes") or []
        chosen = (looknames.PRESETS.get(str(report.get("preset") or "")) or {}).get("label")
        if chosen:
            self.log.log(f"命名方案：{chosen}。")
        if report.get("wrote"):
            self.log.log(f"{action}并整份回读通过：{len(changes)} 条记录，"
                         f"现在 {int(report.get('bytes') or 0):,} 字节。")
            if action == "写入":
                self.log.log("菜单文字已生效：正常退出 USB 后开机就能看到新名字（这类改动不需要关机写盘）。")
            elif report.get("mode") == "baseline":
                self.log.log("已用出厂基线整份写回，回读哈希与基线一致，属于逐字节还原。")
            elif report.get("mode") == "labels-factory":
                self.log.log("没有现成基线，但短名回写后的哈希与出厂资源一致——已经按出厂基线登记，"
                             "这次是逐字节还原。")
            else:
                self.log.log("没有出厂基线，只把文字改回了出厂短名；文件字节与出厂不完全相同，"
                             "但菜单显示已恢复。")
        else:
            self.log.log(f"{action}：相机上的内容已是目标状态，本次没有写入。")
        for change in changes[:8]:
            self.log.log(f"  0x{change['rid']:08x}：{change['old']!r} → {change['new']!r}")
        self.app.refresh()

    def _import_baseline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择一份出厂语言资源", "", "资源文件 (*.bin *.uxc);;所有文件 (*)")
        if not path:
            return
        try:
            item = looknames.import_file(path)
        except looknames.LookNamesError as exc:
            self.log.log(f"导入失败：{exc}")
            return
        self.log.log(f"已导入基线：{KIND_TEXT.get(str(item.get('kind')), '基线')} · "
                     f"{int(item.get('bytes') or 0):,} 字节 · sha256 {str(item.get('sha256'))[:12]}…")
        self.baseline_pill.set_state("可整份还原", theme.SUCCESS)
        self.baseline_detail.setText(f"已导入 {item.get('file')}（{item.get('saved_at')}）")
        self.app.refresh()
