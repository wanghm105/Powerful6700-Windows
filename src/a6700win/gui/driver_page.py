"""驱动准备页：把相机 PID 绑定到 WinUSB。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..usb import driver as driver_mod
from . import theme
from .pages import Page
from .widgets import Card, LogBox, Pill, WrapLabel, reset_layout


class DriverPage(Page):
    title = "驱动准备"
    step = 2
    subtitle = (
        "Windows 需要把相机的 USB 接口绑定到 WinUSB，Python 才能通过 libusb 与相机通信。"
        "本页仅在真实设备模式下使用；绑定过程需要管理员权限，且只针对索尼相机的 "
        "0x047D / 0x0E76 / 0x0336 三个 PID。"
    )

    def __init__(self, app, parent: QWidget | None = None):
        super().__init__(app, parent)
        root = self.root

        self.state_card = Card("当前状态")
        self.state_row = QHBoxLayout()
        self.state_row.setSpacing(10)
        self.pill_admin = Pill("")
        self.pill_wdi = Pill("")
        self.pill_devices = Pill("")
        for pill in (self.pill_admin, self.pill_wdi, self.pill_devices):
            self.state_row.addWidget(pill)
        self.state_row.addStretch(1)
        self.state_card.add_layout(self.state_row)
        self.wdi_path = WrapLabel("")
        self.wdi_path.setObjectName("Faint")
        self.state_card.add(self.wdi_path)
        root.addWidget(self.state_card)

        self.device_card = Card("已识别的相机接口")
        self.device_box = QVBoxLayout()
        self.device_box.setSpacing(8)
        self.device_card.add_layout(self.device_box)
        self.device_empty = QLabel("尚未扫描。")
        self.device_empty.setObjectName("Muted")
        self.device_box.addWidget(self.device_empty)
        root.addWidget(self.device_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.scan_button = QPushButton("扫描设备")
        self.scan_button.setObjectName("Primary")
        self.scan_button.clicked.connect(self._scan)
        actions.addWidget(self.scan_button)
        self.download_button = QPushButton("下载驱动组件")
        self.download_button.clicked.connect(self._download)
        actions.addWidget(self.download_button)
        self.install_button = QPushButton("绑定 WinUSB")
        self.install_button.clicked.connect(self._install)
        actions.addWidget(self.install_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.log_card = Card("进度")
        self.log = LogBox()
        self.log_card.add(self.log)
        root.addWidget(self.log_card, 1)

    def render(self, snapshot: dict) -> None:
        report = getattr(self.app, "driver_report", {}) or {}
        admin = report.get("admin")
        self.pill_admin.set_state("管理员" if admin else "普通权限",
                                  theme.SUCCESS if admin else theme.TEXT_FAINT)
        self.pill_wdi.set_state("组件就绪" if report.get("wdi") else "缺少组件",
                                theme.SUCCESS if report.get("wdi") else theme.WARNING)
        devices = report.get("devices") or []
        bound = [row for row in devices if row.get("winusb")]
        self.pill_devices.set_state(
            f"{len(devices)} 个接口 · {len(bound)} 个已绑定" if devices else "未扫描",
            theme.SUCCESS if devices and len(bound) == len(devices) else theme.TEXT_FAINT)

        reset_layout(self.device_box)
        if not devices:
            empty = QLabel("尚未扫描。" if not report else "没有发现索尼相机接口。")
            empty.setObjectName("Muted")
            self.device_box.addWidget(empty)
        for row in devices:
            line = QHBoxLayout()
            line.setSpacing(10)
            name = QLabel(f"0x{int(row.get('pid', 0)):04X}")
            name.setMinimumWidth(70)
            name.setStyleSheet("font-family: Consolas, monospace;")
            line.addWidget(name)
            label = QLabel(str(row.get("label") or row.get("title") or ""))
            label.setObjectName("Muted")
            line.addWidget(label, 1)
            service = str(row.get("service") or "无")
            line.addWidget(Pill(f"服务：{service}", theme.SUCCESS if row.get("winusb") else theme.WARNING))
            self.device_box.addLayout(line)

        self.wdi_path.setText(f"驱动组件：{report.get('wdi_path', driver_mod.wdi_executable())}"
                              if report else "")
        self.install_button.setEnabled(bool(devices) and not snapshot.get("busy"))
        self.scan_button.setEnabled(not snapshot.get("busy"))
        self.download_button.setEnabled(not snapshot.get("busy") and not report.get("wdi"))

    def _scan(self) -> None:
        self.app.run_task("扫描 USB 设备", lambda progress: driver_mod.scan(), self._scanned)

    def _scanned(self, report) -> None:
        self.app.driver_report = report or {}
        self.log.log(f"扫描完成：{len((report or {}).get('devices') or [])} 个索尼相机接口。")
        self.app.refresh()

    def _download(self) -> None:
        def job(progress):
            return driver_mod.download_wdi(progress)

        self.app.run_task("下载驱动组件", job, self._downloaded)

    def _downloaded(self, path) -> None:
        self.log.log(f"驱动组件已就绪：{path}")
        self._scan()

    def _install(self) -> None:
        pids = [int(row["pid"]) for row in (getattr(self.app, "driver_report", {}) or {}).get("devices", [])
                if not row.get("winusb") and driver_mod.supported(int(row["pid"]))]
        if not pids:
            self.app.notify("没有需要绑定的相机接口。", error=True)
            return

        def job(progress):
            return driver_mod.install(pids, progress)

        self.app.run_task("绑定 WinUSB", job, self._installed)

    def _installed(self, result) -> None:
        changed = (result or {}).get("driver_changed")
        self.log.log("WinUSB 绑定完成。" if changed else "接口已经绑定到 WinUSB，无需重复安装。")
        self._scan()