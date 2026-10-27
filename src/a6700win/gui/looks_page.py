# -*- coding: utf-8 -*-
"""自定义外观页：把四个菜单项换成 CC / NC / 理光正片 / 理光负片 的配色与名字。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from .. import bundle, cp, looknames, looks as looks_mod
from . import theme
from .pages import Page
from .widgets import Card, Divider, LabeledCheck, LogBox, Pill, WrapLabel, reset_layout

STATE_TEXT = {
    "installed": ("已写入颜色", theme.SUCCESS),
    "factory": ("出厂外观", theme.TEXT_FAINT),
    "other": ("已被其它改动", theme.WARNING),
}

NAMES_STATE_TEXT = {
    "installed": ("已是本程序改的", theme.SUCCESS),
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

WRITE_RULES = "拔数据线、关相机、拔电池或断电、让电脑睡眠 / 休眠 / 关机、切走 USB 模式"

# 确认框要摆清楚「写哪里 / 多少字节 / 怎么回滚」：这是变砖前的最后一道门，数字必须是真值。
COLOR_RECORDS = 4                              # 只改 bank 1/4/6/14 各一条记录
COLOR_RECORD_BYTES = looks_mod.STRIDE          # 每条 64 字节
COLOR_UNIT_BYTES = cp.CP_KEYS[cp.CHROMA_UNIT]  # 8,192：整块一起重写
COLOR_PERSIST = "/setting/BACKUP.BIN"          # 正常关机时相机自己把 RAM 存到这里


class LooksPage(Page):
    title = "自定义外观"
    step = 5
    subtitle = ("把 PT / NT / VV / VV2 四个外观换成富士和理光的胶片配色；颜色和菜单名字分开写，"
                "各自都能还原。")

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.names_report: dict | None = None
        self.names_error: str | None = None
        self.names_preset = looknames.load_preset()

        self.intro = Card("这一页改什么")
        body = WrapLabel(
            "相机里有 16 个外观槽位。本页改的是其中 4 个内建槽位的配色，换成富士和理光的四款胶片外观"
            "（CC、NC、PF、NF）。只改颜色，不改明暗过渡。"
        )
        body.setObjectName("Muted")
        self.intro.add(body)
        self.intro.add(Divider())
        self.intro.add_layout(self._mapping_table())
        note = WrapLabel(
            "名字先选一套：英文原名还是中文简称，颜色一点不受影响。名字和颜色是两回事，"
            "也可以只改一件。动手前把相机的 USB 连接方式选成「海量存储器(MSC)」："
            "MENU → 设置 → USB → USB 连接模式。只连这一台相机，全程别拔线。"
        )
        note.setObjectName("Faint")
        self.intro.add(note)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        preset_caption = QLabel("名字用哪一套")
        preset_caption.setObjectName("Faint")
        preset_row.addWidget(preset_caption)
        self.names_preset_box = QComboBox()
        for item in looknames.preset_labels():
            self.names_preset_box.addItem(item["label"], item["key"])
        self.names_preset_box.setToolTip("只决定菜单里写成哪一套叫法，颜色一点不受影响。")
        current = self.names_preset_box.findData(self.names_preset)
        self.names_preset_box.setCurrentIndex(max(0, current))
        self.names_preset_box.currentIndexChanged.connect(self._preset_changed)
        preset_row.addWidget(self.names_preset_box)
        self.preset_hint = QLabel("")
        self.preset_hint.setObjectName("Faint")
        preset_row.addWidget(self.preset_hint)
        preset_row.addStretch(1)
        self.intro.add_layout(preset_row)
        self._sync_preset_hint()
        self.root.addWidget(self.intro)

        # ------------------------------------------------------------ 一次写入
        self.bundle_card = Card("一次做完：颜色 + 名字",
                                "两次连接，中间等相机自己复位，约 2 分钟 · 中途不能拔线断电")
        bundle_note = WrapLabel(
            "颜色和名字在相机里是两套东西。实测一次连起来写会让相机掉线，所以这里拆成两次："
            "先写颜色，等相机自己复位（约 1 分钟）再写名字，全程约 2 分钟，中途别拔线。"
            "选一档名字点下去，颜色和名字就按同一套对齐。"
        )
        bundle_note.setObjectName("Muted")
        self.bundle_card.add(bundle_note)
        warn = WrapLabel(
            "这一步改的是相机固件里的文件，不是 SD 卡。0.3.5 写坏过一次菜单名字，2026-10-26 又有一台"
            "相机因为写错位置变成黑屏、开不了机，两次都只能靠硬件手段救回来，所以这个按钮默认锁着，"
            "勾下面的确认才解开。"
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {theme.DANGER};")
        self.bundle_card.add(warn)
        rules = WrapLabel(
            "写入过程中绝对不能做：拔数据线、关相机、拔电池或断电、让电脑睡眠 / 休眠 / 关机、"
            "切走 USB 模式。任何一步被打断，相机都可能连不上电脑、重复重启变砖。"
        )
        rules.setWordWrap(True)
        rules.setStyleSheet(f"color: {theme.DANGER}; font-weight: 600;")
        self.bundle_card.add(rules)
        self.bundle_ack = LabeledCheck("我知道这一步会改相机固件里的文件，写入途中不能拔线、断电、关相机；被打断可能变砖，仍然要解锁")
        self.bundle_ack.toggled.connect(self._bundle_unlock)
        self.bundle_card.add(self.bundle_ack)
        bundle_row = QHBoxLayout()
        bundle_row.setSpacing(8)
        caption = QLabel("将写入")
        caption.setObjectName("Faint")
        bundle_row.addWidget(caption)
        self.bundle_preset_label = QLabel("")
        bundle_row.addWidget(self.bundle_preset_label)
        bundle_row.addStretch(1)
        self.bundle_restore_button = QPushButton("一次还原（颜色 + 名字）")
        self.bundle_restore_button.setObjectName("Ghost")
        self.bundle_restore_button.setToolTip("先把颜色改回出厂，再把菜单名字改回原来的；两段各连一次相机。")
        self.bundle_restore_button.clicked.connect(self._bundle_restore)
        bundle_row.addWidget(self.bundle_restore_button)
        self.bundle_apply_button = QPushButton("一次做完（颜色 + 名字）")
        self.bundle_apply_button.setObjectName("Ghost")
        self.bundle_apply_button.setEnabled(False)
        self.bundle_apply_button.setToolTip("锁着：先勾上上面的确认。它会改相机固件里的文件。")
        self.bundle_apply_button.clicked.connect(self._bundle_apply)
        bundle_row.addWidget(self.bundle_apply_button)
        self.bundle_card.add_layout(bundle_row)
        self.root.addWidget(self.bundle_card)

        self.restore_card = Card("改坏了能改回来吗")
        verdict = WrapLabel("能：这 4 个外观的颜色逐字节写回出厂值，不留下固件改动。")
        verdict.setObjectName("Verdict")
        self.restore_card.add(verdict)
        self._facts(self.restore_card, (
            ("还原做什么", "把这 4 个外观的颜色逐字节写回出厂值，写完再读一遍核对；"
                     "其它记录一个字节都不动。"),
            ("不写什么", "「还原颜色」不碰固件分区，刷不坏固件，也不需要固件包。"
                    "注意上面「一次做完」里的名字是另一条路：它确实会改固件里的文件。"),
            ("怎么算完成", "点「还原颜色」→ 再点「检查现状」，4 个都显示「出厂外观」→ "
                     "正常关机一次再开机（相机会在关机时把当前状态存下来）。"),
            ("什么会白做", "写完或还原后直接拔电池、断电，改动会丢掉，"
                     "开机看到的还是旧样子。"),
        ))
        self.root.addWidget(self.restore_card)

        self.fit_card = Card("和原厂有多像")
        self._facts(self.fit_card, (
            ("拿来对照的样张", "A7C2 项目的 19 张真实直出样张（6 个场景 × 3 组），"
                    "只做过缩放和拼接，没有调过曝光、白平衡或颜色。"),
            ("怎么凑出来的", "按 12 个色相档取中间值，跟同一场景的样张对齐，再拟合出一组参数。"
                 "下面的「误差」就是这 12 档实测值和目标值的平均偏差，越小越接近。"),
            ("凑得怎么样", "CC 0.183、NC 0.173（中间八档 0.03–0.09）；PF 0.189、NF 0.330 —— "
                 "PF / NF 只做到低饱和近似，不是逐像素复刻。"),
            ("做不到的地方", "① 蓝色那一端压不下来（CC 实测 0.95 / 1.06，目标 0.77 / 0.53）；"
                  "② 这台机器能调的参数不够，做不出 NC 那条窄的品红缺口，也做不出 PF / NF 的局部反向；"
                  "③ 富士的明暗过渡没有对应项，只复刻了颜色。"),
        ))
        self.root.addWidget(self.fit_card)

        self.state_card = Card("现在的样子", "连上相机读一次就能看到")
        self.pills = QHBoxLayout()
        self.pills.setSpacing(8)
        self.pill_camera = Pill("还没检查")
        self.pill_dirty = Pill("")
        self.pills.addWidget(self.pill_camera)
        self.pills.addWidget(self.pill_dirty)
        self.pills.addStretch(1)
        self.state_card.add_layout(self.pills)

        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(10)
        self.state_card.add_layout(self.rows_box)
        self.empty = QLabel("点下面的「检查现状」，连上相机读一次。")
        self.empty.setObjectName("Muted")
        self.rows_box.addWidget(self.empty)
        self.rows: dict[str, dict] = {}
        self.root.addWidget(self.state_card)

        # ------------------------------------------------------------ 菜单名字
        self.names_card = Card("菜单名字", "改相机菜单里显示的外观名字，可以逐字节改回来")
        names_note = WrapLabel(
            "名字和颜色不一样：写进去就一直留在相机里，关机也不掉。所以程序写之前会把相机里"
            "原来的文字整份存一份（约 142 KB），还原时整份写回并核对；本地没有这份底稿时，"
            "只能把名字改回出厂短名（PT / NT / VV / VV2）——下面「底稿」一行会说明现在能用到"
            "哪一档。写哪一套叫法（上面选的英文原名或中文简称）都能改回来。"
        )
        names_note.setObjectName("Muted")
        self.names_card.add(names_note)

        self.names_card.add(Divider())
        self.names_card.add_layout(self._names_table())
        baseline_row = QHBoxLayout()
        baseline_row.setSpacing(8)
        caption = QLabel("底稿")
        caption.setObjectName("Faint")
        baseline_row.addWidget(caption)
        self.baseline_pill = Pill("还没检查")
        baseline_row.addWidget(self.baseline_pill)
        self.baseline_detail = QLabel("")
        self.baseline_detail.setObjectName("Faint")
        baseline_row.addWidget(self.baseline_detail)
        baseline_row.addStretch(1)
        self.names_card.add_layout(baseline_row)
        name_actions = QHBoxLayout()
        name_actions.setSpacing(10)
        self.names_import_button = QPushButton("导入底稿…")
        self.names_import_button.setObjectName("Ghost")
        self.names_import_button.clicked.connect(self._import_baseline)
        name_actions.addWidget(self.names_import_button)
        name_actions.addStretch(1)
        self.names_restore_button = QPushButton("把名字改回去")
        self.names_restore_button.clicked.connect(self._restore_names)
        name_actions.addWidget(self.names_restore_button)
        self.names_apply_button = QPushButton("写入名字")
        self.names_apply_button.setObjectName("Primary")
        self.names_apply_button.clicked.connect(self._apply_names)
        name_actions.addWidget(self.names_apply_button)
        self.names_card.add_layout(name_actions)
        self.root.addWidget(self.names_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        self.detect_button = QPushButton("检查现状")
        self.detect_button.setObjectName("Ghost")
        self.detect_button.clicked.connect(self._detect)
        actions.addWidget(self.detect_button)
        self.restore_button = QPushButton("还原颜色")
        self.restore_button.clicked.connect(self._restore)
        actions.addWidget(self.restore_button)
        self.apply_button = QPushButton("写入颜色")
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
        for column, text in enumerate(("相机里的外观", "改成", "误差")):
            head = QLabel(text)
            head.setObjectName("Faint")
            table.addWidget(head, 0, column)
        try:
            items = looks_mod.profile()
        except looks_mod.LooksError:
            items = []
        for row, item in enumerate(items, start=1):
            table.addWidget(QLabel(str(item.get("slot") or item.get("menu") or "")), row, 0)
            table.addWidget(QLabel(str(item.get("label") or item["name"])), row, 1)
            rms = item.get("rms")
            fit = QLabel(f"{rms:.3f}" if isinstance(rms, (int, float)) else "近似")
            fit.setObjectName("Faint")
            fit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.addWidget(fit, row, 2)
        table.setColumnStretch(1, 1)
        return table

    def _names_table(self) -> QGridLayout:
        """菜单名字的四行：槽位、相机上现在显示什么、要写成什么、状态。"""
        table = QGridLayout()
        table.setHorizontalSpacing(20)
        table.setVerticalSpacing(8)
        for column, text in enumerate(("相机里的外观", "现在是", "改成", "")):
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
            current = QLabel("还没读")
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
            missing = QLabel("程序里的外观清单读不出来——文件可能损坏或被改过。")
            missing.setObjectName("Warning")
            table.addWidget(missing, 1, 0, 1, 4)
        return table

    def _sync_preset_hint(self) -> None:
        meta = looknames.PRESETS.get(self.names_preset) or {}
        self.preset_hint.setText(str(meta.get("note") or ""))
        if hasattr(self, "bundle_preset_label"):
            self.bundle_preset_label.setText(
                f"颜色 4 个 + 菜单名字「{meta.get('label') or self.names_preset}」")

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
        self.log.log(f"名字改成「{(looknames.PRESETS.get(key) or {}).get('label', key)}」；"
                     "点「写入名字」才会真正改到相机上。")

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
            self.pill_camera.set_state("还没检查", theme.TEXT_FAINT)
            self.pill_dirty.set_state("", theme.TEXT_FAINT)
        else:
            installed = sum(1 for row in report.get("looks", []) if row.get("state") == "installed")
            self.pill_camera.set_state(
                f"已写入 {installed}/{len(report.get('looks', []))}", theme.SUCCESS if installed else theme.TEXT_MUTED)
            moved = report.get("moved") or []
            self.pill_dirty.set_state(
                f"别的记录也被改过：{moved}" if moved else "其它记录没动",
                theme.WARNING if moved else theme.TEXT_FAINT)
            self._render_rows(report.get("looks") or [])
        self._render_names()
        enabled = not busy and not simulation
        for button in (self.apply_button, self.restore_button, self.detect_button,
                       self.names_apply_button, self.names_restore_button, self.names_import_button,
                       self.bundle_restore_button):
            button.setEnabled(enabled)
        # 「一次写入」是这一页唯一会写 /usr 固件侧文件的按钮，中途断掉会停在半截：
        # 默认锁着，必须先勾上面那句确认（见 _bundle_unlock）。
        self._bundle_ready = enabled
        self.bundle_ack.box.setEnabled(enabled)
        unlocked = self.bundle_ack.box.isChecked()
        self.bundle_apply_button.setEnabled(enabled and unlocked)
        if simulation:
            hint = "演示模式下不会接触相机，请用真实设备模式。"
        else:
            hint = "需要相机处于海量存储（MSC）模式。"
        self.bundle_apply_button.setToolTip(
            hint if simulation else
            ("颜色和名字一起写：两次连接，中间等相机自己复位，约 2 分钟。"
             if unlocked else
             "锁着：先勾上上面的确认。它会改相机固件里的文件。"))
        self.bundle_restore_button.setToolTip(
            hint if simulation else "颜色改回出厂、名字改回原来的；两次连接，约 2 分钟。")
        self.apply_button.setToolTip(hint if simulation else "写入 4 个外观的颜色，写完读回来核对。")
        self.restore_button.setToolTip(hint if simulation else "把这 4 个外观的颜色改回出厂值，其它记录不动。")
        self.detect_button.setToolTip(hint if simulation else "只看不改。")
        self.names_apply_button.setToolTip(
            hint if simulation else "把菜单里的名字改成选中的那一套（会改相机固件里的文件，写完就留着）。")
        self.names_restore_button.setToolTip(
            hint if simulation else "有底稿就整份写回；没有就只把名字改回出厂短名。")
        self.names_import_button.setToolTip("导入一份出厂文字文件当底稿；不用连相机。")

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
                rms = row.get("rms")
                fit = QLabel(f"误差 {rms:.3f}" if isinstance(rms, (int, float)) else "")
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
                holder["current"].setText("读不出来" if self.names_error else "还没读")
                holder["pill"].set_state("", theme.TEXT_FAINT)
            if self.names_error:
                self.baseline_pill.set_state("读不出来", theme.WARNING)
                self.baseline_detail.setText(self.names_error)
            else:
                self.baseline_pill.set_state("还没检查", theme.TEXT_FAINT)
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
            kind = KIND_TEXT.get(str(best.get("kind")), "底稿")
            self.baseline_pill.set_state("可整份还原", theme.SUCCESS)
            self.baseline_detail.setText(
                f"{kind} · {int(best.get('bytes') or 0):,} 字节 · 存于 {best.get('saved_at') or ''}"
                f" · sha256 {str(best.get('sha256') or '')[:12]}…")
        else:
            self.baseline_pill.set_state("无出厂底稿：只能改回短名", theme.WARNING)
            self.baseline_detail.setText(
                f"共 {baseline.get('count') or 0} 份 · {baseline.get('dir') or ''}")

    # ---------------------------------------------------------------- 动作
    def _write_targets(self, action: str) -> list[str]:
        """确认框里的三行硬信息：写哪个分区、多少字节、靠什么回滚。"""
        both = action.startswith("一次做完")
        wants_color = both or action == "写入颜色"
        lines: list[str] = []
        if wants_color:
            lines.append("写哪里：相机机身里的颜色参数区，不是 SD 卡；关机时相机自己把它写进 "
                         + COLOR_PERSIST)
            lines.append(f"多少字节：改 {COLOR_RECORDS} 条记录、共 "
                         f"{COLOR_RECORDS * COLOR_RECORD_BYTES} 字节，整块 {COLOR_UNIT_BYTES:,} 字节一起重写")
            lines.append("怎么回滚：同一页「还原颜色」把这 4 个外观逐字节写回出厂值，"
                         "前提是相机还能开机、插上数据线还能认出海量存储器（MSC）模式")
        if both or not wants_color:
            size = int((self.names_report or {}).get("bytes") or 0)
            amount = f"整份 {size:,} 字节" if size else "整份约 14.5 万字节"
            lines.append("写哪里：机身固件分区里的简体中文文字包 " + looknames.BLOB_PATH + "，不是 SD 卡")
            lines.append(f"多少字节：{amount}，分块写入，写完逐块读回来核对")
            lines.append("怎么回滚：同一页「把名字改回去」，按本地存的出厂底稿整份写回，"
                         "前提是底稿还在、相机还能开机、插上数据线还能认出海量存储器（MSC）模式")
        return lines

    def _confirm_write(self, action: str) -> bool:
        """写入前的最后一道门：先摊开写哪里、多少字节、怎么回滚，再摆一次中断后果。"""
        targets = "\n".join("· " + line for line in self._write_targets(action))
        text = (f"「{action}」\n{targets}\n\n"
                "中断后果：写到一半被打断，相机可能连不上电脑、重复重启变砖，"
                "只能拔电池等满 1 分钟再试；仍然黑屏就只剩硬件恢复。\n"
                f"写入过程中绝对不能做：{WRITE_RULES}。\n\n"
                "准备好了再点「知道了，开始」。")
        ask = getattr(self.app, "confirm_write", None)
        if callable(ask):
            return bool(ask(action, text))
        box = QMessageBox(QMessageBox.Warning, "开始前再确认一次", text,
                          QMessageBox.Cancel | QMessageBox.Ok, self)
        box.setDefaultButton(QMessageBox.Cancel)
        box.button(QMessageBox.Ok).setText("知道了，开始")
        box.button(QMessageBox.Cancel).setText("先不写")
        return box.exec() == QMessageBox.Ok

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
        """一次认证同时读颜色与菜单名字（两次认证会让相机来回切模式）。"""
        with cp.session(progress) as channel:
            colors = looks_mod.read_state(progress, channel=channel)
            names = None
            error = None
            try:
                names = looknames.read(progress, channel=channel, preset=self.names_preset)
            except Exception as exc:  # noqa: BLE001 - 文字读取失败不影响颜色凑得怎么样
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
        self.log.log(f"检查完成：{installed}/{len(rows)} 个外观已经是改过的颜色。")
        moved = (colors or {}).get("moved") or []
        if moved:
            self.log.log(f"注意：这几条也不是出厂值了：{moved}")
        if self.names_error:
            self.log.log(f"菜单名字没读出来：{self.names_error}")
        elif self.names_report:
            kind = KIND_TEXT.get(str(self.names_report.get("kind")), "未知")
            self.log.log(f"名字文件 {int(self.names_report.get('bytes') or 0):,} 字节，"
                         f"现在是「{kind}」。")
        self.app.refresh()

    def _apply(self) -> None:
        if not self._confirm_write("写入颜色"):
            self.log.log("先不写：这次什么都没动。")
            return
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
        self.log.log("现在的样子：" + "，".join(parts))
        moved = (report or {}).get("moved") or []
        if moved:
            self.log.log(f"注意：这几条跟本页无关，但也变了：{moved}")
        if (report or {}).get("wrote"):
            if restoring:
                self.log.log("已还原，读回来核对过了。请正常关机一次，再开机让相机把它存下来。")
            else:
                self.log.log("已写入，读回来核对过了。请正常关机一次再开机确认。")
        elif restoring:
            self.log.log("4 条记录已经是出厂状态，这次没有写入。")
        else:
            self.log.log("4 条记录已经是目标状态，这次没有写入。")
        self._detect()

    def _bundle_unlock(self, value: bool) -> None:
        """「一次写入」的确认门：勾上才解锁，取消立刻锁回去。"""
        ready = bool(getattr(self, "_bundle_ready", False))
        self.bundle_apply_button.setEnabled(ready and bool(value))
        if value:
            self.log.log("已解锁「一次做完」：它会改相机固件里的文件，每写一次都要重新确认。")

    def _bundle_apply(self) -> None:
        if not self.bundle_ack.box.isChecked():
            self.log.log("「一次做完」还锁着：先勾上上面的确认，再点一次。")
            return
        if not self._confirm_write("一次做完（颜色 + 名字）"):
            self.log.log("先不写：这次什么都没动。")
            return
        self._release_controller_session()
        preset = self.names_preset
        label = (looknames.PRESETS.get(preset) or {}).get("label", preset)
        self.log.log(f"一次做完：颜色 + 名字（{label}）。分两次连接，中间等相机自己复位，"
                     "大约 2 分钟，中途别拔线。")
        self.app.run_task("一次做完（颜色 + 名字）",
                          lambda progress: bundle.apply(progress, preset=preset),
                          lambda report: self._bundle_done(report, restoring=False))
        self.bundle_ack.setChecked(False)  # 每写一次都要重新确认，不留在解锁状态

    def _bundle_restore(self) -> None:
        self._release_controller_session()
        preset = self.names_preset
        self.log.log("一次还原：颜色 + 名字。同样分两次连接，中间等相机自己复位。")
        self.app.run_task("一次还原（颜色 + 名字）",
                          lambda progress: bundle.restore(progress, preset=preset),
                          lambda report: self._bundle_done(report, restoring=True))

    def _bundle_done(self, report, restoring: bool = False) -> None:
        report = report or {}
        colors = report.get("colors")
        if colors is not None:
            self.app.looks_state = colors
            rows = colors.get("looks") or []
            if rows:
                parts = [f"{row.get('name')}={STATE_TEXT.get(str(row.get('state')), ('未知',))[0]}"
                         for row in rows]
                self.log.log("颜色现在的样子：" + "，".join(parts))
        if report.get("names"):
            self.names_report = report.get("names")
            self.names_error = None
        if report.get("error"):
            self.log.log(f"停在这里：{report['error']}")
        names = report.get("names")
        if names:
            preset = (looknames.PRESETS.get(str(names.get("preset") or "")) or {}).get("label")
            if preset:
                self.log.log(f"菜单名字已按「{preset}」写进去。")
            for change in (names.get("changes") or [])[:8]:
                self.log.log(f"  0x{change['rid']:08x}：{change['old']!r} → {change['new']!r}")
        if not report.get("error"):
            if report.get("wrote"):
                if restoring:
                    self.log.log("两段都读回来核对过：颜色和名字都回到出厂状态。"
                                 "颜色要正常关机再开机才真正存住。")
                else:
                    self.log.log("两段都读回来核对过。颜色要正常关机再开机才真正存住；"
                                 "菜单名字退出 USB 后开机就能看到。")
            else:
                self.log.log("两段内容都已经是目标状态，这次没有写入。")
        self.app.refresh()
        self._detect()

    def _apply_names(self) -> None:
        if not self._confirm_write("写入菜单名字"):
            self.log.log("先不写：这次什么都没动。")
            return
        preset = self.names_preset
        label = (looknames.PRESETS.get(preset) or {}).get("label", preset)
        self._release_controller_session()
        self.log.log(f"按「{label}」写入菜单名字…")
        self.app.run_task("写入菜单名字",
                          lambda progress: looknames.apply(progress, preset=preset),
                          lambda report: self._names_done(report, "写入"))

    def _restore_names(self) -> None:
        preset = self.names_preset
        self._release_controller_session()
        self.app.run_task("还原菜单名字",
                          lambda progress: looknames.restore(progress, preset=preset),
                          lambda report: self._names_done(report, "还原"))

    def _names_done(self, report, action: str) -> None:
        report = report or {}
        self.names_report = report
        self.names_error = None
        changes = report.get("changes") or []
        chosen = (looknames.PRESETS.get(str(report.get("preset") or "")) or {}).get("label")
        if chosen:
            self.log.log(f"名字用哪一套：{chosen}。")
        if report.get("wrote"):
            self.log.log(f"{action}完成，整份读回来核对过：{len(changes)} 条记录，"
                         f"共 {int(report.get('bytes') or 0):,} 字节。")
            if action == "写入":
                self.log.log("菜单名字已生效：正常退出 USB 再开机就能看到新名字（这类改动不用关机写盘）。")
            elif report.get("mode") == "baseline":
                self.log.log("用出厂底稿整份写回，读回来和底稿一模一样，属于逐字节还原。")
            elif report.get("mode") == "labels-factory":
                self.log.log("本地没有底稿，但写回短名之后和出厂文件一致——已按出厂底稿登记，"
                             "这次是逐字节还原。")
            else:
                self.log.log("没有出厂底稿，只把文字改回了出厂短名；文件字节与出厂不完全相同，"
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
        self.log.log(f"底稿已导入：{KIND_TEXT.get(str(item.get('kind')), '底稿')} · "
                     f"{int(item.get('bytes') or 0):,} 字节 · sha256 {str(item.get('sha256'))[:12]}…")
        self.baseline_pill.set_state("可整份还原", theme.SUCCESS)
        self.baseline_detail.setText(f"已导入 {item.get('file')}（{item.get('saved_at')}）")
        self.app.refresh()
