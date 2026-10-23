# -*- mode: python ; coding: utf-8 -*-
"""Powerful6700 · Windows 的 PyInstaller 打包定义（onedir）。

必须一起打进包里的东西：
- third_party/a6700_unlock：上游 GPL-3.0 运行时代码、清单与 native 载荷，
  运行时由 a6700win.paths.ensure_vendor_on_path() 从 _internal/third_party 导入；
- libusb-1.0.dll：放在 _internal 根目录，a6700win.usb.windows_auth 会先找
  libusb_package，再退到 exe 目录与 _MEIPASS 根；
- third_party/libwdi/wdi-simple.exe（若已下载）：驱动准备页离线可用。

构建：.venv\\Scripts\\python.exe -m PyInstaller packaging/Powerful6700.spec --noconfirm
"""
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
VENDOR = ROOT / "third_party" / "a6700_unlock"
WDI = ROOT / "third_party" / "libwdi"

if not VENDOR.is_dir():
    raise SystemExit("missing vendored runtime: %s" % VENDOR)


def _libusb() -> Path:
    import libusb_package

    return Path(libusb_package.get_library_path())


datas = [(str(VENDOR), "third_party/a6700_unlock")]
if WDI.is_dir():
    datas.append((str(WDI), "third_party/libwdi"))
datas.append((str(_libusb()), "."))

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "usb",
        "usb.backend.libusb1",
        "usb.core",
        "usb.util",
        "libusb_package",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Powerful6700",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Powerful6700",
)
