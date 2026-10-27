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
        "这一步给相机装一个 Windows 认得的驱动，装完本程序才能跟相机说话。"
        "装的时候要管理员权限，只动索尼相机的三个接口；驱动文件就在安装包里，不用联网。"
        "只有「真实设备模式」才用得到这一页。"
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

        self.device_card = Card("找到的相机接口")
        self.device_box = QVBoxLayout()
        self.device_box.setSpacing(8)
        self.device_card.add_layout(self.device_box)
        self.device_empty = QLabel("还没查找。")
        self.device_empty.setObjectName("Muted")
        self.device_box.addWidget(self.device_empty)
        root.addWidget(self.device_card)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        self.scan_button = QPushButton("查找相机")
        self.scan_button.setObjectName("Ghost")
        self.scan_button.clicked.connect(self._scan)
        actions.addWidget(self.scan_button)
        self.download_button = QPushButton("联网补装驱动")
        self.download_button.setToolTip("只有包里的驱动文件被安全软件删掉时才需要。")
        self.download_button.setObjectName("Ghost")
        self.download_button.clicked.connect(self._download)
        actions.addWidget(self.download_button)
        self.install_button = QPushButton("给相机装驱动")
        self.install_button.setObjectName("Primary")
        self.install_button.clicked.connect(self._install)
        actions.addWidget(self.install_button)
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
        self.pill_wdi.set_state("驱动文件就绪" if report.get("wdi") else "缺少驱动文件",
                                theme.SUCCESS if report.get("wdi") else theme.WARNING)
        devices = report.get("devices") or []
        bound = [row for row in devices if row.get("winusb")]
        self.pill_devices.set_state(
            f"找到 {len(devices)} 个接口 · {len(bound)} 个装好了" if devices else "还没查找",
            theme.SUCCESS if devices and len(bound) == len(devices) else theme.TEXT_FAINT)

        reset_layout(self.device_box)
        if not devices:
            empty = QLabel("还没查找。" if not report else "没找到索尼相机接口。")
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
            service = str(row.get("service") or "没装")
            line.addWidget(Pill(f"驱动：{service}", theme.SUCCESS if row.get("winusb") else theme.WARNING))
            self.device_box.addLayout(line)

        if report:
            source = "随包附带" if report.get("wdi_bundled") else "已下载" 
            self.wdi_path.setText(
                f"驱动文件（{source}）：{report.get('wdi_path', driver_mod.wdi_executable())}")
        else:
            self.wdi_path.setText("")
        self.install_button.setEnabled(bool(devices) and not snapshot.get("busy"))
        self.scan_button.setEnabled(not snapshot.get("busy"))
        self.download_button.setEnabled(not snapshot.get("busy") and not report.get("wdi"))

    def step_reason(self, snapshot: dict) -> str | None:
        """没装驱动就进下一步，只读检查只会报“找不到 MSC 相机”。"""
        report = getattr(self.app, "driver_report", {}) or {}
        if not report:
            return "先点「查找相机」，确认相机接口都装好驱动。"
        devices = report.get("devices") or []
        if not devices:
            return "没找到索尼相机接口：接好数据线、把相机设成海量存储（MSC），再点一次「查找相机」。"
        pending = [row for row in devices if not row.get("winusb")]
        if pending:
            return "还有 %d 个相机接口没装好驱动，装完拔插一次数据线。" % len(pending)
        return None

    def _scan(self) -> None:
        self.app.run_task("查找相机接口", lambda progress: driver_mod.scan(), self._scanned)

    def _scanned(self, report) -> None:
        self.app.driver_report = report or {}
        self.log.log(f"扫描完成：{len((report or {}).get('devices') or [])} 个索尼相机接口。")
        self.app.refresh()

    def _download(self) -> None:
        def job(progress):
            return driver_mod.download_wdi(progress)

        self.app.run_task("下载驱动", job, self._downloaded)

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

        self.app.run_task("给相机装驱动", job, self._installed)

    def _installed(self, result) -> None:
        result = result or {}
        if result.get("driver_changed"):
            self.log.log("WinUSB 绑定完成。")
        elif result.get("pids"):
            # 安装程序返回成功，但没观察到接口切换：不能当成功。
            self.log.log("安装程序已返回，但没有观察到接口切换到 WinUSB；拔插一次数据线后重新扫描。")
        else:
            self.log.log("接口已经绑定到 WinUSB，无需重复安装。")
        self._scan()