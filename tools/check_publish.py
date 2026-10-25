"""发布前扫描：确认仓库与发布 zip 里没有不该上传的东西。

规则（项目所有者 2026-10-25 明示）：不上传固件、私人备份、密钥、ProductInfo、
照片、原始抓包或完整日志。这个脚本把这些变成可执行的检查，发布前跑一次。

用法：
    python tools/check_publish.py              # 只检查 git 跟踪的文件
    python tools/check_publish.py --zip        # 顺带检查 dist 里的发布 zip
    python tools/check_publish.py --zip path   # 检查指定 zip

退出码：0 = 干净；1 = 有发现。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 扩展名：一律不允许出现在仓库里
BANNED_SUFFIXES = {
    ".bin", ".dat", ".arw", ".jpg", ".jpeg", ".heic", ".cr2", ".cr3",
    ".pcap", ".pcapng", ".log", ".pem", ".key", ".p12", ".pfx",
    ".uxc", ".a6700backup", ".img", ".rom", ".fd",
}
# 文件名：小写后完全等于或以这些开头
BANNED_NAMES = {
    "backup.bin", "productinfo.dat", "productinfo.bin",
    "tmmc.jit", "tmmc.dat", "sd.dat", "wbi.bin",
}
BANNED_PREFIXES = ("bodydata", "productinfo", "backup.bin")
# 路径片段（目录名）
BANNED_PARTS = {"firmware", "looknames", "photo", "photos", "captures", "dumps"}
# 允许的例外：扩展名命中但确实属于源码/第三方组件
ALLOWED = {
    # 我们自己编译的相机侧载荷（源码在同一目录，GPL 允许随源码分发）
    "native/flash_write.elf",
    "native/dump_range.elf",
    "third_party/a6700_unlock/data/native/reader.elf",
    "third_party/a6700_unlock/data/native/writer.elf",
    # 第三方驱动安装组件（libwdi / WinUSB 协同安装器）
    "third_party/libwdi/wdi-simple.exe",
    "third_party/libwdi/amd64/WdfCoInstaller01011.dll",
    "third_party/libwdi/amd64/winusbcoinstaller2.dll",
    "third_party/libwdi/amd64/libusbK.dll",
    "third_party/libwdi/amd64/libusbK_x86.dll",
    "third_party/libwdi/amd64/libusb0.dll",
    "third_party/libwdi/amd64/libusb-1.0.dll",
    "third_party/libwdi/x86/libusbK.dll",
    "third_party/libwdi/x86/libusb0.dll",
    "third_party/libwdi/x86/libusb-1.0.dll",
}
# 允许的 PNG：只有界面截图，不含相机照片
ALLOWED_PNG_DIR = "docs/images/"
# 体积上限（超过就人工确认；编译产物与第三方组件除外）
SIZE_LIMIT = 2 * 1024 * 1024
SIZE_EXEMPT_DIRS = ("third_party/libwdi/",)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def judge(name: str) -> str | None:
    """返回不通过的原因；通过返回 None。"""
    if name in ALLOWED:
        return None
    path = Path(name)
    lowered = path.name.lower()
    parts = {part.lower() for part in path.parts[:-1]}
    if parts & BANNED_PARTS:
        return "路径里出现敏感目录（%s）" % "、".join(sorted(parts & BANNED_PARTS))
    if lowered in BANNED_NAMES or lowered.startswith(BANNED_PREFIXES):
        return "文件名属于不上传清单（%s）" % path.name
    suffix = path.suffix.lower()
    if suffix in BANNED_SUFFIXES:
        return "扩展名属于不上传清单（%s）" % suffix
    if suffix == ".png" and not name.replace("\\", "/").startswith(ALLOWED_PNG_DIR):
        return "PNG 只允许界面截图（docs/images/）"
    return None


def check_repo() -> list[str]:
    problems = []
    for name in tracked_files():
        reason = judge(name)
        if reason:
            problems.append("%s：%s" % (name, reason))
            continue
        full = ROOT / name
        try:
            size = full.stat().st_size
        except OSError:
            continue
        if size > SIZE_LIMIT and not any(
                name.replace("\\", "/").startswith(prefix) for prefix in SIZE_EXEMPT_DIRS):
            problems.append("%s：体积 %.1f MB 超过上限，请人工确认" % (name, size / 1048576))
    return problems


def check_zip(path: Path) -> list[str]:
    if not path.exists():
        return ["找不到发布 zip：%s" % path]
    problems = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            lowered = Path(name).name.lower()
            suffix = Path(name).suffix.lower()
            if suffix in BANNED_SUFFIXES or lowered in BANNED_NAMES:
                problems.append("zip 内含 %s" % name)
            elif suffix == ".png":
                problems.append("zip 内含图片 %s" % name)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布前扫描：不上传固件/备份/密钥/照片/抓包/日志")
    parser.add_argument("--zip", nargs="?", const="", default=None,
                        help="顺带检查发布 zip（不带值则用 dist/Powerful6700-Windows-x64.zip）")
    args = parser.parse_args(argv)

    problems = check_repo()
    if args.zip is not None:
        target = Path(args.zip) if args.zip else ROOT / "dist" / "Powerful6700-Windows-x64.zip"
        problems.extend(check_zip(target))

    if not problems:
        print("干净：仓库与发布包都没有固件、私人备份、密钥、ProductInfo、照片、抓包或日志。")
        return 0
    for line in problems:
        print("· " + line)
    print("共 %d 项，先处理再发布。" % len(problems))
    return 1


if __name__ == "__main__":
    sys.exit(main())
