"""四个主流程页面：须知、相机准备、功能管理、结果。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import diagnostics, paths
from ..notices import HARDWARE_RECOVERY_URL, NOTICE_SECTIONS
from . import theme
from .widgets import (
    Badge, Card, CheckLine, Divider, DocLink, FeatureRow, LabeledCheck, LogBox, Pill, SectionRow,
    StepCard,
    WrapLabel, reset_layout,
)


COLUMN_WIDTH = 800  # 内容列上限：正文行宽控制在 45 字左右


def _faint(text: str) -> "WrapLabel":
    label = WrapLabel(text)
    label.setObjectName("Faint")
    return label


def _bundle_default() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return paths.documents_dir() / ("Powerful6700-诊断-%s.zip" % stamp)


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
        self.shell = QHBoxLayout(self.content)
        self.shell.setContentsMargins(0, 0, 0, 0)
        self.shell.setSpacing(0)
        self.column = QWidget()
        self.column.setObjectName("Column")
        self.column.setFixedWidth(COLUMN_WIDTH)
        self.column.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        # 左对齐 + 尾部 stretch：左缘由 _fit_gutters 的固定外边距决定，
        # 尾部富余空间吸收有/无竖直滚动条带来的宽度差，保证换页时不横跳。
        self.shell.addWidget(self.column, 0, Qt.AlignTop)
        self.shell.addStretch(1)
        self.scroll.viewport().installEventFilter(self)
        self.root = QVBoxLayout(self.column)
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
        self.root.addWidget(Divider())

        self.footer = QFrame()
        self.footer.setObjectName("Footer")
        bar = QHBoxLayout(self.footer)
        bar.setContentsMargins(30, 10, 30, 12)
        bar.setSpacing(10)
        self.footer_bar = bar
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_gutters()

    def _gutter(self) -> int:
        return max(0, (self.width() - COLUMN_WIDTH) // 2)

    def _fit_gutters(self) -> None:
        """内容列与页脚统一按窗口宽度留出居中外边距。"""
        gutter = self._gutter()
        if self.shell.contentsMargins().left() != gutter:
            self.shell.setContentsMargins(gutter, 0, 0, 0)
        if self.footer_bar.contentsMargins().left() != 30 + gutter:
            self.footer_bar.setContentsMargins(30 + gutter, 10, 30 + gutter, 12)

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._fit_gutters()
            self._fit_column()
        return super().eventFilter(watched, event)

    def _fit_column(self) -> None:
        """内容列固定上限宽度；窗口变窄时收窄到两侧留白之外。"""
        available = self.width() - 2 * self._gutter()
        width = max(360, min(COLUMN_WIDTH, available))
        if self.column.width() != width:
            self.column.setFixedWidth(width)

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
    subtitle = "先看完「要紧的几条」，再跑一次启动检查。"
    step = 1

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.sections_box = Card("适用范围与风险")
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(18)
        self.sections_box.add_layout(self.rows_box)
        self.root.addWidget(self.sections_box)

        self.env_card = Card("动手前先检查这台电脑")
        self.status = Pill("")
        self.env_card.head_left.addWidget(self.status)
        self.check_button = QPushButton("开始检查")
        self.check_button.setObjectName("Primary")
        self.check_button.clicked.connect(lambda: self.app.check_environment())
        self.env_card.header.addWidget(self.check_button)

        self.env_rows = QVBoxLayout()
        self.env_rows.setSpacing(9)
        self.env_card.add_layout(self.env_rows)
        self.env_empty = QLabel("还没检查。")
        self.env_empty.setObjectName("Muted")
        self.env_rows.addWidget(self.env_empty)
        self.env_card.add(Divider())

        self.meta_grid = QGridLayout()
        self.meta_grid.setContentsMargins(26, 0, 0, 0)
        self.meta_grid.setHorizontalSpacing(10)
        self.meta_grid.setVerticalSpacing(7)
        self.meta_grid.setColumnMinimumWidth(0, 150)
        self.meta_grid.setColumnStretch(1, 1)
        self.meta_labels = {}
        for row, key, name in ((0, "read_bytes", "检查读取范围"), (1, "feature_state_backup", "功能状态备份"),
                              (2, "full_backup", "完整备份"), (3, "integrated_hardware_validation", "整机验证")):
            key_label = QLabel(name)
            key_label.setObjectName("Faint")
            value_label = WrapLabel("—")
            value_label.setObjectName("Muted")
            self.meta_grid.addWidget(key_label, row, 0)
            self.meta_grid.addWidget(value_label, row, 1)
            self.meta_labels[key] = value_label
        self.env_card.add_layout(self.meta_grid)

        self.env_card.add(Divider())
        ack_row = QHBoxLayout()
        ack_row.setSpacing(12)
        self.env_hint = QLabel("")
        self.env_hint.setObjectName("Faint")
        ack_row.addWidget(self.env_hint)
        ack_row.addStretch(1)
        self.ack = LabeledCheck("上面的说明我都看过，知道有风险，仍然继续")
        self.ack.toggled.connect(self._acknowledge)
        ack_row.addWidget(self.ack)
        self.env_card.add_layout(ack_row)

        self.root.addWidget(self.env_card)
        self.root.addStretch(1)
        self._rendered_sections = False

    def _acknowledge(self, value: bool) -> None:
        if getattr(self, "_syncing", False):
            return
        self.app.call_controller(lambda: self.app.controller.acknowledge_notice(bool(value)))

    def step_reason(self, snapshot: dict) -> str | None:
        if not snapshot.get("notice_acknowledged"):
            return "先勾上「我都看过」那个框，才能进下一步。"
        if not snapshot.get("checked"):
            return "先跑一次启动检查。"
        if not (snapshot.get("environment") or {}).get("ready"):
            return "检查没全部通过，按上面的提示处理完再跑一次。"
        return None

    def _go_next(self) -> None:
        if self.app.call_controller(lambda: self.app.controller.begin_preparation()):
            super()._go_next()

    def render(self, snapshot: dict) -> None:
        notice = snapshot.get("notice") or {}
        if not self._rendered_sections:
            # 壳层那两条（内部存储 / 断电等 60 秒）排在 vendor 之前：它们讲的是这台
            # 相机真出过的事，比「适用范围」更该先被看见。
            sections = list(NOTICE_SECTIONS) + list(notice.get("sections", []))
            for index, section in enumerate(sections, start=1):
                self.rows_box.addWidget(SectionRow(index, section, self.app.open_url))
            self.sections_box.set_subtitle(f"共 {len(sections)} 条 · 看完再检查环境")
            self._rendered_sections = True

        self._syncing = True
        acknowledged = bool(snapshot.get("notice_acknowledged"))
        self.ack.setChecked(acknowledged)
        self._syncing = False
        busy = bool(snapshot.get("busy"))
        self.ack.setEnabled(not busy)

        environment = snapshot.get("environment") or {}
        checks = environment.get("checks") or []
        reset_layout(self.env_rows)
        if checks:
            for row in checks:
                self.env_rows.addWidget(CheckLine(row))
        else:
            empty = QLabel("还没检查。")
            empty.setObjectName("Muted")
            self.env_rows.addWidget(empty)

        read_bytes = environment.get("read_bytes")
        self.meta_labels["read_bytes"].setText(
            f"{read_bytes:,} 字节（{read_bytes // 512} 个固定扇区）" if isinstance(read_bytes, int) else "—"
        )
        for key in ("feature_state_backup", "full_backup", "integrated_hardware_validation"):
            self.meta_labels[key].setText(str(environment.get(key, "—")))

        ready = bool(environment.get("ready"))
        checked = bool(snapshot.get("checked"))
        self.check_button.setText("再跑一次检查" if checked else "开始检查")
        if busy:
            self.status.set_state("正在检查", theme.WARNING)
        elif ready:
            self.status.set_state("这台电脑没问题", theme.SUCCESS)
        elif checked:
            self.status.set_state("有问题要处理", theme.DANGER)
        else:
            self.status.set_state("还没检查", theme.TEXT_FAINT)
        self.check_button.setEnabled(acknowledged and not busy)
        self.check_button.setToolTip(
            "" if acknowledged else "先勾上左边那个确认框。")

        if busy:
            hint = "正在检查，等一下。"
        elif not acknowledged:
            hint = "勾上确认，就能开始检查。"
        elif not checked:
            hint = "已经确认过了，点右上角的「开始检查」。"
        elif ready:
            hint = "全部通过，可以进「相机准备」了。"
        else:
            hint = "按上面的提示处理完，再跑一次检查。"
        self.env_hint.setText(hint)


class PreparationPage(Page):
    title = "相机准备"
    subtitle = "照顺序确认四件事，然后做一次只看不改的检查。"
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
            self.inspect_button.setToolTip("先去「操作前须知」把启动检查跑完。")
        elif not all_confirmed:
            self.inspect_button.setToolTip("先把上面四项都确认一遍。")
        else:
            self.inspect_button.setToolTip("")

    def step_reason(self, snapshot: dict) -> str | None:
        if not snapshot.get("ready"):
            return "先把上面四项确认完。"
        if not snapshot.get("compatible"):
            return "先点「开始只读检查」，通过了再进下一步。"
        return None

    def _confirm(self, step_id: str, value: bool) -> None:
        self.app.call_controller(lambda: self.app.controller.confirm(step_id, bool(value)))


class HomePage(Page):
    title = "功能管理"
    subtitle = "只读检查通过后，在这里开关功能、备份或还原。"
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

        self.summary_card = Card("上次检查的结果")
        self.summary = WrapLabel("尚未执行只读检查。")
        self.summary.setObjectName("Muted")
        self.summary_card.add(self.summary)
        # 被结构守卫拦下时，上游只给一句「内容或布局不匹配」（operations.py:288），
        # 差异明细其实在 plan["issues"] 里。这里先露三行，完整版在「操作结果」页。
        self.blocked_hint = WrapLabel("")
        self.blocked_hint.setObjectName("Muted")
        self.blocked_hint.setVisible(False)
        self.summary_card.add(self.blocked_hint)
        self.root.addWidget(self.summary_card)

        self.features_card = Card("功能列表", "只列这份清单里核对过的开关")
        self.features_box = QVBoxLayout()
        self.features_box.setSpacing(8)
        self.features_card.add_layout(self.features_box)
        self.features_empty = QLabel("先做一次只读检查，这里才会列出能开能关的功能。")
        self.features_empty.setObjectName("Muted")
        self.features_box.addWidget(self.features_empty)
        self.feature_rows: dict[str, FeatureRow] = {}
        self.root.addWidget(self.features_card)

        self.backup_card = Card("功能状态备份", "还原是整份写回，跟上面勾了哪些无关。")
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
        hint_row = QHBoxLayout()
        hint_row.setSpacing(10)
        self.backup_hint = QLabel("")
        self.backup_hint.setObjectName("Faint")
        self.backup_hint.setWordWrap(False)
        hint_row.addWidget(self.backup_hint)
        hint_row.addStretch(1)
        self.open_backup_button = QPushButton("打开备份目录")
        self.open_backup_button.setObjectName("Ghost")
        self.open_backup_button.setToolTip("在资源管理器里打开备份文件所在的文件夹。")
        self.open_backup_button.clicked.connect(self._open_backup_dir)
        hint_row.addWidget(self.open_backup_button)
        self.backup_card.add_layout(hint_row)
        self._backup_dir = ""
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

    def _open_backup_dir(self) -> None:
        target = self._backup_dir or str(paths.backup_dir())
        try:
            Path(target).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.app.notify(f"打不开备份目录：{exc}", error=True)
            return
        url = QUrl.fromLocalFile(target).toString()
        opener = getattr(self.app, "open_url", None)
        if callable(opener):
            opener(url)
        else:
            QDesktopServices.openUrl(QUrl(url))
        self.log.log(f"备份目录：{target}")

    def _restore(self) -> None:
        backup_id = self.backup_combo.currentData()
        if not backup_id:
            self.app.notify("先在列表里挑一份备份。", error=True)
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
            self.summary.setText("还没做只读检查。")

        issues = list(((snapshot.get("result") or {}).get("plan") or {}).get("issues") or [])
        if issues:
            preview = diagnostics.issue_lines(issues, limit=3)
            self.blocked_hint.setText(
                "检查没通过：有 %d 处对不上。完整原因在「操作结果」页，那里能一键复制："
                % len(issues) + "\n" + "\n".join("· " + row for row in preview))
        else:
            self.blocked_hint.setText("")
        self.blocked_hint.setVisible(bool(issues))

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
        backup_dir = str(snapshot.get("backup_dir") or "")
        self._backup_dir = backup_dir
        self.open_backup_button.setEnabled(True)
        if backup_dir:
            tail = "\\".join(backup_dir.rstrip("\\").split("\\")[-2:])
            self.backup_hint.setText(f"备份目录：…\\{tail}")
            self.backup_hint.setToolTip(backup_dir)
        else:
            self.backup_hint.setText("")
            self.backup_hint.setToolTip("")
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
    subtitle = "下面是从相机读回来的结果；说「不确定」就按说明做，别自己猜。"
    step = 6

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        self.card = Card("")
        self.card.set_title("")
        self.headline = QLabel("还没有结果")
        self.headline.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.card.add(self.headline)
        self.detail = WrapLabel("")
        self.detail.setObjectName("Muted")
        self.card.add(self.detail)
        self.meta = WrapLabel("")
        self.meta.setObjectName("Faint")
        self.root.addWidget(self.card)

        # 失败时先给三步自救：最常见的情况是「一看没反应就连续重试」，那才是真变砖。
        self.rescue_card = Card("先别急着重试")
        self.rescue_body = QVBoxLayout()
        self.rescue_body.setSpacing(8)
        self.rescue_card.add_layout(self.rescue_body)
        self.rescue_card.setVisible(False)
        self.root.addWidget(self.rescue_card)

        # 被拦下时把 plan["issues"] 摊开：上游算好了差异，之前一个字段都没显示。
        self.issues_card = Card("哪里对不上")
        self.issues_body = QVBoxLayout()
        self.issues_body.setSpacing(6)
        self.issues_card.add_layout(self.issues_body)
        issues_actions = QHBoxLayout()
        issues_actions.setSpacing(8)
        issues_actions.addStretch(1)
        self.copy_button = QPushButton("复制诊断信息")
        self.copy_button.setObjectName("Ghost")
        self.copy_button.clicked.connect(self._copy_diagnostics)
        issues_actions.addWidget(self.copy_button)
        self.export_button = QPushButton("导出诊断包")
        self.export_button.setObjectName("Ghost")
        self.export_button.clicked.connect(self._export_diagnostics)
        issues_actions.addWidget(self.export_button)
        self.issues_card.add_layout(issues_actions)
        self.issues_card.setVisible(False)
        self.root.addWidget(self.issues_card)

        self.aftercare_card = Card("在相机上确认")
        self.aftercare_body = QVBoxLayout()
        self.aftercare_body.setSpacing(10)
        self.aftercare_card.add_layout(self.aftercare_body)
        self.aftercare_card.setVisible(False)
        self.root.addWidget(self.aftercare_card)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.home_button = QPushButton("回到功能开关")
        self.home_button.setObjectName("Primary")
        self.home_button.clicked.connect(self._back_to_home)
        actions.addWidget(self.home_button)
        self.root.addLayout(actions)
        self.root.addStretch(1)

    def _back_to_home(self) -> None:
        """控制器成功时返回 snapshot（真值），不能再拿它做 or 判断。"""
        snapshot = self.app.call_controller(self.app.controller.home)
        if snapshot is not None:
            self.app.goto("home")

    def render(self, snapshot: dict) -> None:
        result = snapshot.get("result") or {}
        if not result:
            self.headline.setText("还没有结果")
            self.detail.setText("做完一次操作，这里会显示从相机读回来的结论。")
            self.meta.setText("")
            self.issues_card.setVisible(False)
            self.aftercare_card.setVisible(False)
            self.rescue_card.setVisible(False)
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
        self._render_rescue(result)
        self._render_issues(result)
        self._render_aftercare(result)

    RESCUE_STEPS = (
        "拔掉数据线，先别再插回去。",
        "取出电池，等满 1 分钟以上，再把电池装回去。",
        "只装电池开机（别插线）：能进菜单就说明救回来了；一直黑屏或反复重启，就只剩硬件恢复。",
    )

    def _render_rescue(self, result: dict) -> None:
        """失败时最先给的东西：三步自救，而不是让用户自己猜着再试一遍。"""
        reset_layout(self.rescue_body)
        if bool(result.get("success")):
            self.rescue_card.setVisible(False)
            return
        if result.get("write_attempted"):
            head = "写到一半停了。按这个顺序处理，别在这里再点一次。"
        elif result.get("device_access"):
            head = "这次没写进去。按这个顺序处理，再回来看。"
        else:
            head = "这次没能跟相机说上话。按这个顺序处理，再回来看。"
        intro = WrapLabel(head)
        intro.setObjectName("Muted")
        self.rescue_body.addWidget(intro)
        for index, step in enumerate(self.RESCUE_STEPS, 1):
            self.rescue_body.addWidget(WrapLabel(f"{index}. {step}"))
        stop = WrapLabel("不要连续重试、不要反复插拔数据线——那会让相机更久连不上电脑，连海量存储器（MSC）都不出现。")
        stop.setStyleSheet(f"color: {theme.DANGER}; font-weight: 600;")
        self.rescue_body.addWidget(stop)
        links = QHBoxLayout()
        links.setSpacing(18)
        self.rescue_link = DocLink("硬件说明（救砖）↗")
        self.rescue_link.clicked.connect(lambda: self.app.open_url(HARDWARE_RECOVERY_URL))
        links.addWidget(self.rescue_link)
        links.addStretch(1)
        self.rescue_body.addLayout(links)
        self.rescue_card.setVisible(True)

    # --------------------------------------------------------------- 差异与取证
    def _render_issues(self, result: dict) -> None:
        """blocked 时给出「差在哪、下一步做什么」，取证入口放在同一张卡上。"""
        issues = list((result.get("plan") or {}).get("issues") or [])
        reset_layout(self.issues_body)
        if not issues:
            self.issues_card.setVisible(False)
            return
        self.issues_card.set_title("哪里对不上 · %d 处" % len(issues))
        hint = diagnostics.issue_hint(issues)
        if hint:
            head = WrapLabel(hint)
            head.setObjectName("Muted")
            self.issues_body.addWidget(head)
        for row in diagnostics.issue_lines(issues, limit=10):
            self.issues_body.addWidget(_faint("· " + row))
        run_directory = result.get("run_directory")
        if run_directory:
            self.issues_body.addWidget(_faint("运行目录：%s" % run_directory))
        self.issues_card.setVisible(True)

    def _copy_diagnostics(self) -> None:
        result = dict(self.app.snapshot.get("result") or {})
        if not result:
            self.app.notify("还没有结果可以复制。", error=True)
            return
        QGuiApplication.clipboard().setText(diagnostics.report(result, diagnostics.environment()))
        self.app.notify("诊断信息已复制，可以直接贴到 issue。")

    def _export_diagnostics(self) -> None:
        result = dict(self.app.snapshot.get("result") or {})
        if not result:
            self.app.notify("还没有结果可以导出。", error=True)
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "保存诊断包", str(_bundle_default()), "Zip (*.zip)")
        if not target:
            return
        try:
            path = diagnostics.export_bundle(result, Path(target))
        except OSError as exc:
            self.app.notify("导出失败：%s" % exc, error=True)
            return
        self.app.notify("已导出诊断包：%s" % path)

    def _render_aftercare(self, result: dict) -> None:
        aftercare = result.get("aftercare")
        reset_layout(self.aftercare_body)
        if not aftercare:
            self.aftercare_card.setVisible(False)
            return
        restart = bool(aftercare.get("restart_required"))
        self.aftercare_card.set_title("在相机上确认" if restart else "在菜单里确认")
        steps = aftercare.get("steps") or []
        if restart and steps:
            head = WrapLabel("已经写进去、也读回来核对过了，但要断电重开一次才生效。按顺序做完：")
            head.setObjectName("Muted")
            self.aftercare_body.addWidget(head)
            for index, step in enumerate(steps, 1):
                row = WrapLabel(f"{index}. {step.get('title', '')} — {step.get('detail', '')}")
                self.aftercare_body.addWidget(row)
        checks = aftercare.get("features") or []
        if checks:
            head = WrapLabel("重开后按下面的菜单一项项确认：" if restart else "按下面的菜单一项项确认：")
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
