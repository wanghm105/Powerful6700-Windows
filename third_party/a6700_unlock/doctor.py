"""Environment diagnostics with stable IDs and no explicit USB enumeration."""
from importlib.util import find_spec
import platform
import shutil
import sys

from .usb.backend import payloads


def check(identifier, name, ok, detail, remediation):
    """Stable IDs are the UI/API contract; translated names are presentation."""
    return dict(id=identifier, name=name, ok=bool(ok), detail=detail, remediation=remediation)


def diagnose(profile):
    checks = [
        check('python', 'Python', sys.version_info >= (3, 10), platform.python_version(),
              '源码运行请使用 Python 3.10+；桌面版应重新安装匹配系统的应用。'),
        check('platform', '平台', sys.platform in ('darwin', 'linux'), sys.platform,
              '当前设备连接层支持 macOS／Linux，Windows 适配尚未完成。'),
        check('pyusb', 'PyUSB', find_spec('usb') is not None, '设备操作需要 a6700-unlock[usb]',
              '源码运行安装 a6700-unlock[usb]；桌面版应包含此组件。'),
    ]
    if sys.platform == 'darwin':
        from .bundled import resource
        try:
            helper = resource('capture')
            ready = helper.is_file() if helper else bool(shutil.which('clang'))
            checks.append(check('capture-compiler', 'macOS 接口接管组件', ready,
                                '应用内置组件' if helper else '源码运行需要 clang / Command Line Tools',
                                '桌面版请重新获取完整应用；源码版安装 Command Line Tools。'))
        except Exception:
            checks.append(check('capture-compiler', 'macOS 接口接管组件', False,
                                '应用内置组件校验失败', '请重新获取完整应用。'))
    try:
        from .usb.legacy import check_libusb_library
        available = check_libusb_library()
        checks.append(check('libusb', 'libusb', available, '只检查库加载，不初始化 USB 会话',
                            '源码运行请安装系统 libusb；桌面版请重新获取完整应用。'))
    except Exception as exc:
        checks.append(check('libusb', 'libusb', False, str(exc),
                            '源码运行请安装系统 libusb；桌面版请重新获取完整应用。'))
    try:
        assets = payloads(profile)
        checks.append(check('payload-integrity', '固定范围载荷完整性', True,
                            {name: len(data) for name, data in assets.items()},
                            '重新获取同一版本的完整安装包；不要手工混用适配文件和载荷。'))
    except Exception as exc:
        checks.append(check('payload-integrity', '固定范围载荷完整性', False, str(exc),
                            '重新获取同一版本的完整安装包；不要手工混用适配文件和载荷。'))
    return dict(ready=all(item['ok'] for item in checks), checks=checks, device_access=False,
                read_bytes=len(profile.entries) * 512,
                full_backup='未实现，后续补充', full_restore='未实现，后续补充',
                feature_state_backup='稀疏支持（254 个固定扇区）',
                feature_state_restore='稀疏支持（只写回清单字段）',
                integrated_hardware_validation=profile.data['hardware_validation'])
