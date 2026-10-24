"""四个主流程页面：须知、相机准备、功能管理、结果。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import (
    Badge, Card, CheckLine, Divider, DocLink, FeatureRow, LabeledCheck, LogBox, Pill, StepCard,
    WrapLabel, reset_layout,
)


class Page(QWidget):
    """页面基类：由主窗口注入自己并驱动渲染。"""

    title = ""
    subtitle = ""
    step = 0  # 线性流程里的步骤号；0 表示不参与步骤（关于与诊断）

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)
        self.content = QWidget()
        self.content.setObjectName("Content")
        self.scroll.setWidget(self.content)
        self.root = QVBoxLayout(self.content)
        self.root.setContentsMargins(30, 26, 30, 26)
        self.root.setSpacing(18)
        head = QVBoxLayout()
        head.setSpacing(6)
        self.step_label = QLabel("")
        self.step_label.setObjectName("StepChip")
        head.addWidget(self.step_label)
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("Title")
        head.addWidget(self.title_label)
        self.subtitle_label = WrapLabel(self.subtitle)
        self.subtitle_label.setObjectName("Subtitle")
        head.addWidget(self.subtitle_label)
        self.root.addLayout(head)

        self.footer = QFrame()
        self.footer.setObjectName("Footer")
        bar = QHBoxLayout(self.footer)
        bar.setContentsMargins(30, 10, 30, 12)
        bar.setSpacing(10)
        self.back_button = QPushButton("← 上一步")
        self.back_button.setObjectName("Ghost")
        self.back_button.clicked.connect(self._go_back)
        bar.addWidget(self.back_button)
        bar.addStretch(1)
        self.footer_hint = QLabel("")
        self.footer_hint.setObjectName("Faint")
        self.footer_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bar.addWidget(self.footer_hint)
        self.next_button = QPushButton("下一步")
        self.next_button.setObjectName("Primary")
        self.next_button.clicked.connect(self._go_next)
        bar.addWidget(self.next_button)
        outer.addWidget(self.footer)

        self.key = ""
        self._prev_key: str | None = None
        self._next_key: str | None = None
        self.footer.hide()

    def render(self, snapshot: dict) -> None:  # pragma: no cover - 由子类实现
        pass

    # ------------------------------------------------------------ 线性流程
    def step_reason(self, snapshot: dict) -> str | None:
        """返回阻止进入下一步的原因；返回 None 表示可以继续。"""
        return None

    def update_steps(self, snapshot: dict) -> None:
        order = list(getattr(self.app, "step_keys", []) or [])
        titles = getattr(self.app, "step_titles", {}) or {}
        if not self.step or self.key not in order:
            self.step_label.hide()
            self.footer.hide()
            return
        index = order.index(self.key)
        self.step_label.setText(f"第 {self.step} 步 · 共 {len(order)} 步")
        self.step_label.show()
        self.footer.show()
        self._prev_key = order[index - 1] if index > 0 else None
        self._next_key = order[index + 1] if index + 1 < len(order) else None
        self.back_button.setVisible(self._prev_key is not None)
        self.next_button.setVisible(self._next_key is not None)
        if self._next_key is None:
            self.footer_hint.setText("已是最后一步；需要继续时可以回到「功能管理」。")
            return
        self.next_button.setText(f"下一步：{titles.get(self._next_key, '')}")
        reason = self.step_reason(snapshot)
        busy = bool(snapshot.get("busy"))
        self.next_button.setEnabled(not reason and not busy)
        self.footer_hint.setText(reason or "")

    def _go_back(self) -> None:
        if self._prev_key:
            self.app.goto(self._prev_key)

    def _go_next(self) -> None:
        if self._next_key:
            self.app.goto(self._next_key)


class NoticePage(Page):
    title = "操作前须知"
    subtitle = "请先阅读适用范围、验证进度与操作风险，然后完成启动检查。"
    step = 1

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.sections_box = Card("须知内容")
        self.root.addWidget(self.sections_box)

        ack_row = QHBoxLayout()
        ack_row.setContentsMargins(0, 0, 0, 0)
        ack_row.addStretch(1)
        self.ack = LabeledCheck("我已阅读，并了解适用范围与真实设备操作风险")
        self.ack.toggled.connect(self._acknowledge)
        ack_row.addWidget(self.ack)
        self.root.addLayout(ack_row)

        self.env_card = Card("启动检查")
        self.env_rows = QVBoxLayout()
        self.env_rows.setSpacing(8)
        self.env_card.add_layout(self.env_rows)
        self.env_empty = QLabel("尚未运行启动检查。")
        self.env_empty.setObjectName("Muted")
        self.env_rows.addWidget(self.env_empty)
        self.env_card.add(Divider())
        meta = QGridLayout()
        meta.setHorizontalSpacing(24)
        meta.setVerticalSpacing(6)
        self.meta_labels = {}
        for row, key, name in ((0, "read_bytes", "检查读取范围"), (1, "feature_state_backup", "功能状态备份"),
                              (2, "full_backup", "完整备份"), (3, "integrated_hardware_validation", "整机验证")):
            key_label = QLabel(name)
            key_label.setObjectName("Faint")
            value_label = WrapLabel("—")
            value_label.setObjectName("Muted")
            meta.addWidget(key_label, row, 0)
            meta.addWidget(value_label, row, 1)
            self.meta_labels[key] = value_label
        self.env_card.add_layout(meta)

        self.status = Pill("")
        self.check_button = QPushButton("开始启动检查")
        self.check_button.setObjectName("Primary")
        self.check_button.clicked.connect(lambda: self.app.check_environment())
        self.env_card.header.addWidget(self.status)
        self.env_card.header.addWidget(self.check_button)
        self.root.addWidget(self.env_card)
        self.root.addStretch(1)
        self._rendered_sections = False

    def _acknowledge(self, value: bool) -> None:
        if getattr(self, "_syncing", False):
            return
        self.app.call_controller(lambda: self.app.controller.acknowledge_notice(bool(value)))

    def step_reason(self, snapshot: dict) -> str | None:
        if not snapshot.get("notice_acknowledged"):
            return "请先勾选「我已阅读」，再运行启动检查。"
        if not snapshot.get("checked"):
            return "请先运行启动检查。"
        if not (snapshot.get("environment") or {}).get("ready"):
            return "启动检查未全部通过，请按提示处理后重试。"
        return None

    def _go_next(self) -> None:
        if self.app.call_controller(lambda: self.app.controller.begin_preparation()):
            super()._go_next()

    def render(self, snapshot: dict) -> None:
        notice = snapshot.get("notice") or {}
        if not self._rendered_sections:
            self.sections_box.set_title(str(notice.get("title", "操作前须知")))
            intro = WrapLabel(str(notice.get("introduction", "")))
            intro.setObjectName("Muted")
            self.sections_box.add(intro)
            for section in notice.get("sections", []):
                self.sections_box.add(self._section(section))
            self._rendered_sections = True

        self._syncing = True
        acknowledged = bool(snapshot.get("notice_acknowledged"))
        self.ack.setChecked(acknowledged)
        self._syncing = False
        self.ack.setEnabled(not snapshot.get("busy"))

        environment = snapshot.get("environment") or {}
        checks = environment.get("checks") or []
        reset_layout(self.env_rows)
        if checks:
            for row in checks:
                self.env_rows.addWidget(CheckLine(row))
        else:
            empty = QLabel("尚未运行启动检查。")
            empty.setObjectName("Muted")
            self.env_rows.addWidget(empty)

        read_bytes = environment.get("read_bytes")
        self.meta_labels["read_bytes"].setText(
            f"{read_bytes:,} 字节（{read_bytes // 512} 个固定扇区）" if isinstance(read_bytes, int) else "—"
        )
        for key in ("feature_state_backup", "full_backup", "integrated_hardware_validation"):
            value = environment.get(key, "—")
            self.meta_labels[key].setText(str(value))

        ready = bool(environment.get("ready"))
        checked = bool(snapshot.get("checked"))
        acknowledged = bool(snapshot.get("notice_acknowledged"))
        self.check_button.setText("重新运行启动检查" if checked else "开始启动检查")
        busy = bool(snapshot.get("busy"))
        if busy:
            self.status.set_state("操作进行中", theme.WARNING)
        elif ready:
            self.status.set_state("环境就绪", theme.SUCCESS)
        elif checked:
            self.status.set_state("存在问题待处理", theme.DANGER)
        else:
            self.status.set_state("待检查", theme.TEXT_FAINT)
        self.check_button.setEnabled(acknowledged and not busy)
        self.check_button.setToolTip(
            "" if acknowledged else "请先勾选「我已阅读，并了解适用范围与真实设备操作风险」。")

    def _section(self, section: dict) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("Inset")
        inset_policy = wrapper.sizePolicy()
        inset_policy.setHeightForWidth(True)
        wrapper.setSizePolicy(inset_policy)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        level = str(section.get("level", "info"))
        marker = QLabel(chr(0x25CF))
        marker.setStyleSheet(f"color: {theme.LEVEL_COLORS.get(level, theme.TEXT_MUTED)};")
        head.addWidget(marker)
        title = QLabel(str(section.get("title", "")))
        title.setStyleSheet("font-weight: 600;")
        head.addWidget(title, 1)
        head.addWidget(Badge({"risk": "风险", "scope": "范围"}.get(level, "")))
        layout.addLayout(head)
        body = WrapLabel(str(section.get("body", "")))
        body.setObjectName("Muted")
        layout.addWidget(body)
        source = str(section.get("source_url") or "")
        if source:
            link = DocLink("查看官方说明 ↗")
            link.setToolTip(source)
            link.clicked.connect(lambda _=False, url=source: self.app.open_url(url))
            layout.addWidget(link)
        return wrapper


class PreparationPage(Page):
    title = "相机准备"
    subtitle = "按顺序确认四项准备工作；确认后即可进行只读兼容性检查。"
    step = 3

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.steps_box = QVBoxLayout()
        self.steps_box.setSpacing(12)
        self.root.addLayout(self.steps_box)
        self.step_cards: dict[str, StepCard] = {}

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.hint = QLabel("")
        self.hint.setObjectName("Faint")
        actions.addWidget(self.hint)
        actions.addStretch(1)
        self.all_button = QPushButton("全部确认")
        self.all_button.setObjectName("Ghost")
        self.all_button.clicked.connect(lambda: self.app.call_controller(
            lambda: self.app.controller.confirm_preparation(True)))
        actions.addWidget(self.all_button)
        self.clear_button = QPushButton("清除确认")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.clicked.connect(lambda: self.app.call_controller(
            lambda: self.app.controller.confirm_preparation(False)))
        actions.addWidget(self.clear_button)
        self.inspect_button = QPushButton("开始只读检查")
        self.inspect_button.setObjectName("Primary")
        self.inspect_button.clicked.connect(lambda: self.app.operate("inspect"))
        actions.addWidget(self.inspect_button)
        self.root.addLayout(actions)

        self.log_card = Card("进度")
        self.log = LogBox()
        self.log_card.add(self.log)
        self.root.addWidget(self.log_card, 1)

    def render(self, snapshot: dict) -> None:
        steps = snapshot.get("steps") or []
        known = [card.step_id for card in self.step_cards.values()]
        if [str(step.get("id")) for step in steps] != known:
            for card in self.step_cards.values():
                self.steps_box.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
            self.step_cards = {}
            for step in steps:
                card = StepCard(step)
                card.confirmed.connect(self._confirm)
                self.steps_box.addWidget(card)
                self.step_cards[card.step_id] = card

        for step in steps:
            card = self.step_cards.get(str(step.get("id")))
            if card is None:
                continue
            blocked = card.check.blockSignals(True)
            card.check.setChecked(bool(step.get("confirmed")))
            card.check.blockSignals(blocked)
            card.check.setEnabled(not snapshot.get("busy") and snapshot.get("phase") == "preparation")
            card.pill.set_state("已确认" if step.get("confirmed") else "",
                                theme.SUCCESS if step.get("confirmed") else theme.TEXT_FAINT)

        done = sum(1 for step in steps if step.get("confirmed"))
        self.hint.setText(f"已确认 {done}/{len(steps)} 项")
        busy = bool(snapshot.get("busy"))
        all_confirmed = bool(steps) and done == len(steps)
        ready = bool(snapshot.get("ready"))
        self.all_button.setEnabled(not busy and not all_confirmed)
        self.clear_button.setEnabled(not busy and done > 0)
        self.inspect_button.setEnabled(ready and all_confirmed and not busy)
        if not ready:
            self.inspect_button.setToolTip("请先在“操作前须知”页完成启动检查。")
        elif not all_confirmed:
            self.inspect_button.setToolTip("请先确认上方全部准备工作。")
        else:
            self.inspect_button.setToolTip("")

    def step_reason(self, snapshot: dict) -> str | None:
        if not snapshot.get("ready"):
            return "请先把四项准备全部确认。"
        if not snapshot.get("compatible"):
            return "请先点「开始只读检查」，通过后进入功能管理。"
        return None

    def _confirm(self, step_id: str, value: bool) -> None:
        self.app.call_controller(lambda: self.app.controller.confirm(step_id, bool(value)))


class HomePage(Page):
    title = "功能管理"
    subtitle = "只读检查通过后可选择功能并执行解锁、关闭、备份或恢复。"
    step = 4

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.status_row = QHBoxLayout()
        self.status_row.setSpacing(8)
        self.pill_connected = Pill("")
        self.pill_compatible = Pill("")
        self.pill_mode = Pill("")
        for pill in (self.pill_connected, self.pill_compatible, self.pill_mode):
            self.status_row.addWidget(pill)
        self.status_row.addStretch(1)
        self.root.addLayout(self.status_row)

        self.summary_card = Card("只读检查结果")
        self.summary = WrapLabel("尚未执行只读检查。")
        self.summary.setObjectName("Muted")
        self.summary_card.add(self.summary)
        self.root.addWidget(self.summary_card)

        self.features_card = Card("功能列表", "仅列出清单中已知的固定范围字段")
        self.features_box = QVBoxLayout()
        self.features_box.setSpacing(8)
        self.features_card.add_layout(self.features_box)
        self.features_empty = QLabel("执行只读检查后显示可管理功能。")
        self.features_empty.setObjectName("Muted")
        self.features_box.addWidget(self.features_empty)
        self.feature_rows: dict[str, FeatureRow] = {}
        self.root.addWidget(self.features_card)

        self.backup_card = Card("功能状态备份")
        backup_row = QHBoxLayout()
        backup_row.setSpacing(10)
        self.backup_combo = QComboBox()
        self.backup_combo.setMinimumWidth(300)
        backup_row.addWidget(self.backup_combo, 1)
        self.backup_button = QPushButton("备份当前功能状态")
        self.backup_button.clicked.connect(lambda: self.app.operate("backup"))
        backup_row.addWidget(self.backup_button)
        self.restore_button = QPushButton("恢复整份备份")
        self.restore_button.setObjectName("Ghost")
        self.restore_button.clicked.connect(self._restore)
        backup_row.addWidget(self.restore_button)
        self.backup_card.add_layout(backup_row)
        self.backup_hint = WrapLabel("")
        self.backup_hint.setObjectName("Faint")
        self.backup_card.add(self.backup_hint)
        self.root.addWidget(self.backup_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.reconnect_button = QPushButton("断开连接")
        self.reconnect_button.setObjectName("Ghost")
        self.reconnect_button.clicked.connect(self._toggle_connection)
        actions.addWidget(self.reconnect_button)
        actions.addStretch(1)
        self.select_all = QPushButton("全选")
        self.select_all.setObjectName("Ghost")
        self.select_all.clicked.connect(lambda: self.app.select_features("all"))
        actions.addWidget(self.select_all)
        self.select_none = QPushButton("全不选")
        self.select_none.setObjectName("Ghost")
        self.select_none.clicked.connect(lambda: self.app.select_features("none"))
        actions.addWidget(self.select_none)
        self.close_button = QPushButton("关闭所选功能")
        self.close_button.clicked.connect(lambda: self.app.operate("close"))
        actions.addWidget(self.close_button)
        self.unlock_button = QPushButton("解锁所选功能")
        self.unlock_button.setObjectName("Primary")
        self.unlock_button.clicked.connect(lambda: self.app.operate("unlock"))
        actions.addWidget(self.unlock_button)
        self.root.addLayout(actions)

        self.log_card = Card("进度")
        self.log = LogBox()
        self.log_card.add(self.log)
        self.root.addWidget(self.log_card, 1)

    def _toggle_connection(self) -> None:
        connected = bool(self.app.snapshot.get("connected"))
        if connected:
            self.app.call_controller(lambda: self.app.controller.disconnect())
        else:
            self.app.call_controller(lambda: self.app.controller.reconnect())

    def _restore(self) -> None:
        backup_id = self.backup_combo.currentData()
        if not backup_id:
            self.app.notify("请先选择一个备份。", error=True)
            return
        self.app.operate("restore", backup_id=str(backup_id))

    def render(self, snapshot: dict) -> None:
        simulation = bool(snapshot.get("simulation"))
        self.pill_mode.set_state("演示模式" if simulation else "真实设备", theme.ACCENT if simulation else theme.TEXT_MUTED)
        self.pill_connected.set_state("已连接" if snapshot.get("connected") else "未连接",
                                      theme.SUCCESS if snapshot.get("connected") else theme.TEXT_FAINT)
        compatible = bool(snapshot.get("compatible"))
        self.pill_compatible.set_state("兼容性通过" if compatible else "未验证",
                                       theme.SUCCESS if compatible else theme.WARNING)

        summary = snapshot.get("inspect_summary") or {}
        if summary:
            parts = [
                f"兼容性：{'通过' if summary.get('compatible') else '未通过'}",
                f"读取扇区：{summary.get('read_sectors', '—')}",
                f"读取字节：{summary.get('read_bytes', '—')}",
                f"功能项：{len(summary.get('features') or [])}",
            ]
            self.summary.setText("　·　".join(str(part) for part in parts))
        else:
            self.summary.setText("尚未执行只读检查。")

        features = snapshot.get("features") or []
        known = list(self.feature_rows)
        if [str(item.get("id")) for item in features] != known:
            for row in self.feature_rows.values():
                self.features_box.removeWidget(row)
                row.setParent(None)
                row.deleteLater()
            self.feature_rows = {}
            for feature in features:
                row = FeatureRow(feature)
                row.selection.connect(self._select)
                self.features_box.addWidget(row)
                self.feature_rows[row.feature_id] = row
        self.features_empty.setVisible(not features)

        editable = bool(snapshot.get("compatible")) and snapshot.get("phase") == "home" and not snapshot.get("busy")
        for feature in features:
            row = self.feature_rows.get(str(feature.get("id")))
            if row is None:
                continue
            # 状态必须每次渲染就地更新：写入后同一批功能的开关状态会变。
            row.update_feature(feature)
            row.set_selected(bool(feature.get("selected")))
            row.set_editable(editable)

        backups = snapshot.get("backups") or []
        current = self.backup_combo.currentData()
        self.backup_combo.clear()
        for entry in backups:
            label = str(entry.get("created") or entry.get("id") or "备份")
            detail = entry.get("label") or entry.get("path") or ""
            self.backup_combo.addItem(f"{label}　{detail}".strip(), str(entry.get("id") or ""))
        if current:
            index = self.backup_combo.findData(current)
            if index >= 0:
                self.backup_combo.setCurrentIndex(index)
        self.backup_button.setEnabled(bool(snapshot.get("compatible")) and not snapshot.get("busy"))
        self.restore_button.setEnabled(bool(backups) and not snapshot.get("busy"))
        self.backup_hint.setText(f"备份目录：{snapshot.get('backup_dir', '')}（恢复会把整份功能状态写回，与勾选无关）" if snapshot.get("backup_dir") else "")
        connected = bool(snapshot.get("connected"))
        self.reconnect_button.setText("断开连接" if connected else "重新连接")
        for button in (self.unlock_button, self.close_button):
            button.setEnabled(editable)
        self.select_all.setEnabled(editable)
        self.select_none.setEnabled(editable)

    def _select(self, feature_id: str, value: bool) -> None:
        self.app.call_controller(lambda: self.app.controller.set_feature_selection(feature_id, bool(value)))


class ResultPage(Page):
    title = "操作结果"
    subtitle = "结果来自真实设备回读校验；如提示不确定请按说明处置。"
    step = 6

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.card = Card("")
        self.card.set_title("")
        self.headline = QLabel("尚无结果")
        self.headline.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.card.add(self.headline)
        self.detail = WrapLabel("")
        self.detail.setObjectName("Muted")
        self.card.add(self.detail)
        self.meta = WrapLabel("")
        self.meta.setObjectName("Faint")
        self.meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.card.add(self.meta)
        self.root.addWidget(self.card)
        self.aftercare_card = Card("机身验收")
        self.aftercare_body = QVBoxLayout()
        self.aftercare_body.setSpacing(10)
        self.aftercare_card.add_layout(self.aftercare_body)
        self.aftercare_card.setVisible(False)
        self.root.addWidget(self.aftercare_card)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.home_button = QPushButton("返回功能管理")
        self.home_button.setObjectName("Primary")
        self.home_button.clicked.connect(lambda: self.app.call_controller(
            lambda: self.app.controller.home()) or self.app.goto("home"))
        actions.addWidget(self.home_button)
        self.root.addLayout(actions)
        self.root.addStretch(1)

    def render(self, snapshot: dict) -> None:
        result = snapshot.get("result") or {}
        if not result:
            self.headline.setText("尚无结果")
            self.detail.setText("完成一次操作后这里会显示回读校验结论。")
            self.meta.setText("")
            self.aftercare_card.setVisible(False)
            return
        success = bool(result.get("success"))
        self.card.set_title(str(result.get("status", "")))
        self.headline.setText(str(result.get("title", "操作完成")))
        self.headline.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {theme.SUCCESS if success else theme.DANGER};")
        lines = [str(result.get("detail", ""))]
        error = result.get("error")
        if error:
            lines.append(f"错误：{error}")
        self.detail.setText("\n".join(line for line in lines if line))
        meta = [
            f"状态：{result.get('status', '—')}",
            f"写操作：{'是' if result.get('write_attempted') else '否'}",
            f"设备访问：{'是' if result.get('device_access') else '否'}",
            f"模式：{'演示' if result.get('simulation') else '真实设备'}",
        ]
        if result.get("backup_path"):
            meta.append(f"备份文件：{result['backup_path']}")
        if result.get("backup_sha256"):
            meta.append(f"SHA-256：{result['backup_sha256']}")
        if result.get("cleanup_warning"):
            meta.append(f"清理提示：{result['cleanup_warning']}")
        self.meta.setText("\n".join(meta))
        self._render_aftercare(result)

    def _render_aftercare(self, result: dict) -> None:
        aftercare = result.get("aftercare")
        reset_layout(self.aftercare_body)
        if not aftercare:
            self.aftercare_card.setVisible(False)
            return
        restart = bool(aftercare.get("restart_required"))
        self.aftercare_card.set_title("机身验收" if restart else "菜单确认")
        steps = aftercare.get("steps") or []
        if restart and steps:
            head = WrapLabel("写入与独立回读已通过，但功能要断电重启后才体现。请按顺序完成：")
            head.setObjectName("Muted")
            self.aftercare_body.addWidget(head)
            for index, step in enumerate(steps, 1):
                row = WrapLabel(f"{index}. {step.get('title', '')} — {step.get('detail', '')}")
                self.aftercare_body.addWidget(row)
        checks = aftercare.get("features") or []
        if checks:
            head = WrapLabel("重启后按下列菜单逐项确认：" if restart else "按下列菜单逐项确认：")
            head.setObjectName("Muted")
            self.aftercare_body.addWidget(head)
        for check in checks:
            box = QWidget()
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(4)
            title = WrapLabel(f"{check.get('name', '')} · {check.get('outcome', '')}")
            title.setObjectName("SectionTitle")
            column.addWidget(title)
            for label, text, style in (("菜单路径", check.get("path"), "Muted"),
                                       ("预期", check.get("expected"), "Faint"),
                                       ("注意", check.get("note"), "Faint")):
                if not text:
                    continue
                line = WrapLabel(f"{label}：{text}")
                line.setObjectName(style)
                column.addWidget(line)
            self.aftercare_body.addWidget(box)
        self.aftercare_card.setVisible(True)
