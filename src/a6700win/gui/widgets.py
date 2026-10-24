"""可复用的界面部件。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from . import theme


class Card(QFrame):
    """带标题的圆角卡片。"""

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(12)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Faint")
        # 标题与说明上下两行，避免说明在标题右侧拉出一条长句。
        self.head_title = QVBoxLayout()
        self.head_title.setSpacing(3)
        self.head_title.addWidget(self.title_label)
        self.head_title.addWidget(self.subtitle_label)
        self.header = QHBoxLayout()
        self.header.setSpacing(10)
        self.head_left = QHBoxLayout()
        self.head_left.setSpacing(10)
        self.head_right = QHBoxLayout()
        self.head_right.setSpacing(10)
        self.header.addLayout(self.head_title)
        self.header.addLayout(self.head_left)
        self.header.addStretch(1)
        self.header.addLayout(self.head_right)
        self.body.addLayout(self.header)
        self.title_label.setVisible(bool(title))
        self.subtitle_label.setVisible(bool(subtitle))

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)
        self.title_label.setVisible(bool(text))

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)


def reset_layout(layout) -> None:
    """清空布局并把旧部件立刻从界面上摘掉（deleteLater 要等事件循环才生效）。"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                reset_layout(child)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class Pill(QLabel):
    """小圆点 + 文本的状态标签。"""

    def __init__(self, text: str = "", color: str = theme.TEXT_MUTED, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Faint")
        self.set_state(text, color)

    def set_state(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self.setText(f"● {text}" if text else "")
        self.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.setVisible(bool(text))


class Badge(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.setVisible(bool(text))


class WrapLabel(QLabel):
    """会自动换行的文本标签。

    QLabel 自己不会把换行后的高度告诉外层布局，短文本卡片里就会把文字裁掉或叠在一起。
    这里在每次尺寸变化后把最小高度校正为当前宽度下的实际换行高度。
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def _needed_height(self) -> int:
        width = self.width()
        if width <= 0:
            return 0
        return self.heightForWidth(width)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(hint.width(), max(hint.height(), self._needed_height()))

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), max(hint.height(), self._needed_height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        needed = self._needed_height()
        if needed > 0 and abs(self.minimumHeight() - needed) > 1:
            self.setMinimumHeight(needed)
            self.updateGeometry()
            parent = self.parentWidget()
            if parent is not None:
                parent.updateGeometry()


class LabeledCheck(QWidget):
    """文字在左、勾选框在右的勾选项；整块都能点，适合右对齐的确认行。"""

    toggled = Signal(bool)

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {theme.TEXT};")
        self.box = QCheckBox()
        self.box.setObjectName("Acknowledge")
        self.box.setAccessibleName(text)
        row.addWidget(self.label, 0, Qt.AlignVCenter)
        row.addWidget(self.box, 0, Qt.AlignVCenter)
        self.box.toggled.connect(self.toggled)
        self.setCursor(Qt.PointingHandCursor)

    def text(self) -> str:
        return self.label.text()

    def setText(self, text: str) -> None:
        self.label.setText(text)
        self.box.setAccessibleName(text)

    def isChecked(self) -> bool:
        return self.box.isChecked()

    def setChecked(self, value: bool) -> None:
        self.box.setChecked(bool(value))

    def setEnabled(self, value: bool) -> None:  # noqa: N802 (Qt 命名)
        super().setEnabled(value)
        self.label.setStyleSheet(f"color: {theme.TEXT if value else theme.TEXT_FAINT};")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.box.isEnabled():
            self.box.toggle()
        super().mouseReleaseEvent(event)


class LogBox(QPlainTextEdit):
    """只读的进度日志，自动滚动到底部。"""

    def __init__(self, parent: QWidget | None = None, max_lines: int = 400):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        self.setMinimumHeight(96)
        self.setPlaceholderText("操作进度会显示在这里。")

    def log(self, message: str) -> None:
        self.appendPlainText(message)
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        self.clear()


class DocLink(QToolButton):
    """打开文档或菜单路径的次要按钮。"""

    def __init__(self, text: str, url: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Link")
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.url = url
        self.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; color: {theme.ACCENT};"
            f" padding: 0; text-align: left; }}"
            f"QToolButton:hover {{ color: #f2c372; }}"
        )


class CheckLine(QWidget):
    """启动检查中的一行结果。"""

    def __init__(self, row: dict, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        ok = bool(row.get("ok"))
        mark = QLabel("✓" if ok else "✕")
        mark.setFixedWidth(16)
        mark.setStyleSheet(f"color: {theme.SUCCESS if ok else theme.DANGER}; font-weight: 700;")
        layout.addWidget(mark)
        name = QLabel(str(row.get("name", row.get("id", ""))))
        name.setFixedWidth(150)
        layout.addWidget(name)
        detail = str(row.get("detail", ""))
        detail_label = WrapLabel(detail)
        detail_label.setObjectName("Muted")
        detail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(detail_label, 1)
        self.remediation = str(row.get("remediation", ""))
        if self.remediation and not ok:
            self.setToolTip(self.remediation)
            detail_label.setToolTip(self.remediation)


class SectionRow(QWidget):
    """须知里的一条：左侧序号 + 标题（可带标签）+ 正文，没有内层边框。"""

    def __init__(self, index: int, section: dict, opener=None, text_width: int = 620,
                 parent: QWidget | None = None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        number = QLabel(f"{index:02d}")
        number.setObjectName("SectionIndex")
        number.setFixedWidth(22)
        number.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        grid.addWidget(number, 0, 0, 1, 1, Qt.AlignTop)

        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel(str(section.get("title", "")))
        title.setObjectName("RowTitle")
        head.addWidget(title)
        head.addStretch(1)
        level = str(section.get("level", "info"))
        head.addWidget(Badge({"risk": "风险", "scope": "范围"}.get(level, "")))
        grid.addLayout(head, 0, 1)

        body = WrapLabel(str(section.get("body", "")))
        body.setObjectName("Muted")
        body.setMaximumWidth(text_width)
        grid.addWidget(body, 1, 1)

        source = str(section.get("source_url") or "")
        if source and opener is not None:
            link = DocLink("查看官方说明 ↗")
            link.setToolTip(source)
            link.clicked.connect(lambda _=False, url=source: opener(url))
            grid.addWidget(link, 2, 1, Qt.AlignLeft)


class StepCard(QFrame):
    """相机准备中的一个确认步骤。"""

    confirmed = Signal(str, bool)

    def __init__(self, step: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.step_id = str(step.get("id", ""))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(9)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.check = QCheckBox(str(step.get("title", self.step_id)))
        self.check.setStyleSheet("QCheckBox { font-size: 14px; font-weight: 600; }")
        self.check.toggled.connect(lambda value: self.confirmed.emit(self.step_id, bool(value)))
        head.addWidget(self.check, 1)
        self.pill = Pill("")
        head.addWidget(self.pill)
        layout.addLayout(head)

        instruction = WrapLabel(str(step.get("instruction", "")))
        instruction.setObjectName("Muted")
        layout.addWidget(instruction)

        for guide in step.get("menu_guides", []) or []:
            row = QHBoxLayout()
            row.setSpacing(8)
            path = " › ".join(str(part) for part in guide.get("path", []) if part)
            label = WrapLabel(f"菜单路径：{path}" if path else str(guide.get("title", "")))
            label.setObjectName("Faint")
            row.addWidget(label, 1)
            if guide.get("target"):
                target = QLabel(f"设为：{guide['target']}")
                target.setObjectName("Faint")
                row.addWidget(target)
            layout.addLayout(row)

        self.skip_note = QLabel(str(step.get("skip_label", "")))
        self.skip_note.setObjectName("Faint")
        self.skip_note.setVisible(bool(self.skip_note.text()))
        layout.addWidget(self.skip_note)


class FeatureRow(QFrame):
    """功能列表中的一行。状态可以就地更新（预检结果会覆盖同一行）。"""

    selection = Signal(str, bool)

    def __init__(self, feature: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Inset")
        self.feature_id = str(feature.get("id", ""))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.check = QCheckBox()
        self.check.setMinimumWidth(260)
        self.check.toggled.connect(lambda value: self.selection.emit(self.feature_id, bool(value)))
        layout.addWidget(self.check)

        self.pill = Pill()
        layout.addWidget(self.pill)
        layout.addStretch(1)

        self.tag = QLabel()
        self.tag.setObjectName("Faint")
        layout.addWidget(self.tag)

        self.requires: list = []
        self.update_feature(feature)

    def update_feature(self, feature: dict) -> None:
        name = str(feature.get("name", self.feature_id))
        if self.check.text() != name:
            blocked = self.check.blockSignals(True)
            self.check.setText(name)
            self.check.blockSignals(blocked)
        state = str(feature.get("state", ""))
        self.pill.set_state({"enabled": "已开启", "disabled": "已关闭"}.get(state, state or "状态未知"),
                            theme.state_color(state))
        verification = str(feature.get("verification", ""))
        self.tag.setText({"historical-hardware-tested": "历史硬件验证",
                          "pending": "待验证"}.get(verification, verification))
        self.tag.setVisible(bool(verification))
        limits = feature.get("limits") or []
        self.setToolTip("\n".join(f"· {item}" for item in limits) if limits else "")
        self.requires = feature.get("requires") or []
        self.setEnabled(bool(feature.get("available", True)))

    def set_selected(self, selected: bool) -> None:
        blocked = self.check.blockSignals(True)
        self.check.setChecked(bool(selected))
        self.check.blockSignals(blocked)

    def set_editable(self, editable: bool) -> None:
        self.check.setEnabled(editable)
