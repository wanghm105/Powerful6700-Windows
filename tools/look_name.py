"""改机身语言资源里的外观短名（就地替换，长度不变才允许）。

用法：
    python tools/look_name.py --show
    python tools/look_name.py --set 0x021c6654=CC --set 0x021c6434=CN --confirm yes-write

只写改动的几个字节；写前把整份资源备份到 ../firmware/uxc/，写完立刻回读校验。
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from a6700win import flash, patches, paths, windows_shim  # noqa: E402

paths.ensure_vendor_on_path()

from a6700_unlock.usb import legacy  # noqa: E402

import uxc  # noqa: E402

TARGET = "/usr/share/app/string_simplifiedchinese_f.uxc"
BACKUP_DIR = ROOT.parent / "firmware" / "uxc"
LOOK_RIDS = {
    0x021C658E: "ST",
    0x021C6654: "PT",
    0x021C6434: "NT",
    0x021C687B: "VV",
    0x021C689A: "VV2",
    0x021C6CC9: "FL",
    0x021C6857: "IN",
    0x021C6961: "SH",
    0x021C65F8: "BW",
    0x021C658A: "SE",
}
CHUNK = 0x8000


class ChannelBackend:
    """把 SenserChannel 包成 flash 模块需要的 _command/_file 形状。"""

    def __init__(self, channel):
        self.channel = channel

    def _command(self, command, payload):
        code, body = self.channel.send(0x40, struct.pack("<HH", 0x1001, command) + payload)
        if code != 0:
            raise RuntimeError(f"USB 服务命令失败：0x{command:04x}, code={code}")
        return body

    def _file(self, command, ident, data):
        body = self._command(command, bytes([0, ident, 0]) + data)
        if len(body) != 4 or body != b"\0" * 4:
            raise RuntimeError("文件写入或载荷执行失败，状态：" + body[:16].hex())


def read_whole(backend, path):
    size = flash.stat(backend, path)
    data = bytearray()
    offset = 0
    while offset < size:
        length = min(CHUNK, size - offset)
        data += flash.read_range(backend, path, offset, length)
        offset += length
    return bytes(data)


def parse_set(text):
    rid_text, _, name = text.partition("=")
    if not name:
        raise SystemExit(f"--set 需要 RID=NAME，收到 {text!r}")
    return int(rid_text, 16), name


def main(argv=None):
    parser = argparse.ArgumentParser(description="改机身外观短名")
    parser.add_argument("--path", default=TARGET)
    parser.add_argument("--set", action="append", default=[], metavar="RID=NAME")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--confirm", default="", help="真正写入需要 --confirm yes-write")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-service", action="store_true", help="失败时也不要退出服务模式，省一次手动切 MSC")
    args = parser.parse_args(argv)

    wanted = [parse_set(item) for item in args.set]
    patches.install()

    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = None
    try:
        target, _channel = legacy.run_authentication(None, 0x0336, args.timeout, True, progress=print)
        backend = ChannelBackend(_channel)
        raw = read_whole(backend, args.path)
        print(f"{args.path}  {len(raw)} 字节  sha256 {hashlib.sha256(raw).hexdigest()[:16]}")
        resource = uxc.decode(raw)
        records = {r.rid: r for r in resource.records}
        for rid, label in LOOK_RIDS.items():
            record = records.get(rid)
            if record:
                print(f"  0x{rid:08x} {label:<4} -> {record.text!r}  offset 0x{record.offset:x}")
        if args.show or not wanted:
            return 0
        if args.confirm != "yes-write" or args.dry_run:
            print("未提供 --confirm yes-write，只做检查，不写入。")
            return 0

        body = raw
        changed = []
        for rid, name in wanted:
            record = records.get(rid)
            if record is None:
                raise SystemExit(f"找不到 rid 0x{rid:08x}")
            old = record.text
            body = uxc.patch_text(body, record, name)
            span = record.end - 4 - record.offset
            changed.append((record.offset + 4, old.encode("utf-8"), name.encode("utf-8"), span))
            print(f"  改名 0x{rid:08x}: {old!r} -> {name!r}（容量 {span} 字节）")

        for offset, old, new, span in changed:
            if len(new) > span - 1:
                raise SystemExit(f"新名字 {len(new)} 字节超过记录容量 {span - 1} 字节")
            if body[offset + len(new)] != 0:
                raise SystemExit("新名字之后没有 NUL 结束符，放弃写入")

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = BACKUP_DIR / f"{Path(args.path).name}.{stamp}.bin"
        backup.write_bytes(raw)
        print(f"已备份原始资源：{backup}")
        patched = BACKUP_DIR / f"{Path(args.path).name}.{stamp}.patched.bin"
        patched.write_bytes(body)

        windows = [(offset, new) for offset, _old, new, _span in changed]
        flash.write_windows(backend, args.path, windows, progress=print)
        for offset, _old, new, _span in changed:
            check = flash.read_range(backend, args.path, offset, len(new))
            if check != new:
                raise SystemExit(f"回读不一致：偏移 0x{offset:x} 得到 {check!r}")
        print("回读校验通过，外观短名已更新。重启相机后生效。")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"失败：{exc}")
        return 1
    finally:
        if target is not None and not args.keep_service:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
                legacy.close_target(target)
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    raise SystemExit(main())
