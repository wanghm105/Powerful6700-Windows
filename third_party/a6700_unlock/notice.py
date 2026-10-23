"""Product notice content, separate from its desktop presentation.

Reading acknowledgement is an in-session navigation gate, not a waiver,
license acceptance, device compatibility check or permission to write a camera.
"""
from copy import deepcopy


_NOTICE = dict(
    title="操作前须知",
    introduction="请先了解适用范围、验证进度与操作风险，再准备相机。",
    acknowledgement="我已阅读，并了解适用范围与真实设备操作风险",
    sections=[
        dict(id="scope", title="仅适配 A6700 · 固件 2.00", icon="camera.fill", level="scope",
             body="现有适配与实机测试仅覆盖 Sony α6700（ILCE-6700）、固件 2.00。其他机型或版本尚未验证，不应使用；同为 2.00 的机身也仍需通过内容兼容性预检。",
             source_url=""),
        dict(id="validation", title="当前版本与验证进度", icon="checkmark.shield", level="info",
             body="0.2 版开放 FTP、关机快门帘、灵活曝光和电子快门声音；位移多帧合成与动态增强防抖暂不开放。启动仅检查本机环境，完成准备后才连接相机；可切换演示体验流程。已有实机连接、功能写入与独立回读记录，仍在扩大测试样本，不能保证所有机身和长期使用场景均已验证。",
             source_url=""),
        dict(id="device-risk", title="设备与数据风险", icon="exclamationmark.triangle", level="risk",
             body="真实固件修改存在无法启动（变砖）、设置或数据丢失的风险。掉电、断线、机身状态差异或程序错误都可能导致操作失败；恢复不保证成功。本应用暂不提供备份与恢复入口，也不提供整盘或固件镜像恢复；关闭解锁功能不等于恢复整机官方固件。",
             source_url=""),
        dict(id="warranty", title="保修与官方支持", icon="wrench.and.screwdriver", level="risk",
             body="非官方固件修改可能影响保修资格及官方售后支持。具体取决于当地适用政策、法律及售后判定，请在真实设备操作前了解相关规定。",
             source_url="https://www.sony.com.cn/content/casch/serviceinfo/servicepolicy.html"),
        dict(id="disclaimer", title="免责声明与开源许可", icon="doc.text", level="info",
             body="本项目是非 Sony 官方的开源工具，按现状提供，不承诺无缺陷、操作安全或恢复成功。无担保及责任限制见 GPL-3.0-only 许可，并以适用法律允许的范围为限。",
             source_url=""),
    ],
)


def operation_notice():
    """Return display data without reading a device or making legal decisions."""
    return deepcopy(_NOTICE)
