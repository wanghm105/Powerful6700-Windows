"""Grow a camera text resource by one record, then put it back.

Look names live in /usr/share/app/string_simplifiedchinese_f.uxc as a packed
sequence of records:  u32 (rid | 0x1e000000) , UTF-8 text , NUL , pad to 4 bytes.
There is no index table, so a longer name can only be stored by moving everything
after it.  This tool tests the cheap question first: does the camera tolerate a
larger file at all?

It appends a duplicate of the last record at EOF.  Nothing that already exists
changes, every rid still maps to the same text, and the experiment is undone with
--restore, which truncates the file back to its original size.

    python tools/uxc_grow_test.py --confirm yes-append   # grow, then reboot
    python tools/uxc_grow_test.py --restore              # back to original size
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a6700win import flash, paths  # noqa: E402

TARGET = "/usr/share/app/string_simplifiedchinese_f.uxc"
ORIGINAL_SIZE = 145612
ZERO = bytes([0])


class ChannelBackend:
    """Wrap a SenserChannel into the _command/_file shape the flash module needs."""

    def __init__(self, channel):
        self.channel = channel

    def _command(self, command, payload):
        code, body = self.channel.send(
            0x40, struct.pack("<HH", 0x1001, command) + payload)
        if code != 0:
            raise RuntimeError("USB 服务命令失败：0x%04x, code=%d" % (command, code))
        return body

    def _file(self, command, ident, data):
        body = self._command(command, bytes([0, ident, 0]) + data)
        if len(body) != 4 or body != ZERO * 4:
            raise RuntimeError("文件写入或载荷执行失败，状态：" + body[:16].hex())


def open_backend(progress):
    paths.ensure_vendor_on_path()
    from a6700win.patches import install
    from a6700win.usb.windows_auth import run_authentication

    install()
    target, channel = run_authentication(None, 0x0336, 12.0, True, progress=progress)
    return target, ChannelBackend(channel)


def last_record(tail):
    """Return the final record inside tail (which must end at EOF)."""
    for back in range(len(tail) - 4, -1, -1):
        if back % 4:
            continue
        word = int.from_bytes(tail[back:back + 4], "little")
        if word >> 24 != 0x1E:
            continue
        text = tail[back + 4:]
        if ZERO not in text:
            continue
        body = text.split(ZERO, 1)[0]
        if not body or any(b < 0x20 for b in body):
            continue
        return tail[back:]
    raise SystemExit("没能在文件尾部找到完整的记录，先不要追加。")


def main(argv=None):
    parser = argparse.ArgumentParser(description="测试相机文本资源能否变大")
    parser.add_argument("--restore", action="store_true", help="截断回原始长度")
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--confirm", default="", help="追加时需 --confirm yes-append")
    args = parser.parse_args(argv)

    def progress(message):
        print("  ·", message)

    try:
        target, flash_backend = open_backend(progress)
    except Exception as exc:  # noqa: BLE001
        print("连接失败：", exc)
        return 2
    try:
        size = flash.stat(flash_backend, args.target)
        print("当前长度：%d 字节" % size)
        if args.restore:
            if size <= ORIGINAL_SIZE:
                print("长度 %d 不大于 %d，无需截断。" % (size, ORIGINAL_SIZE))
                return 0
            final = flash.truncate(flash_backend, args.target, ORIGINAL_SIZE)
            print("已截断回 %d 字节（实测 %d）。" % (ORIGINAL_SIZE, final))
            return 0 if final == ORIGINAL_SIZE else 1
        if args.confirm != "yes-append":
            print("追加会让文件变大，需要 --confirm yes-append。")
            return 1
        if size != ORIGINAL_SIZE:
            print("当前长度不是预期的 %d，先停止。" % ORIGINAL_SIZE)
            return 1
        tail = flash.read_range(flash_backend, args.target, size - 64, 64)
        record = last_record(tail)
        print("尾部记录 %d 字节：%s" % (len(record), record.hex()))
        flash.write_block(flash_backend, args.target, size, record)
        after = flash.stat(flash_backend, args.target)
        print("追加完成：%d -> %d 字节" % (size, after))
        print("请关机再开机，确认菜单文字正常，然后回来跑 --restore。")
        return 0 if after == size + len(record) else 1
    finally:
        try:
            from a6700win.usb import legacy
            legacy.close_target(target)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
