"""Survey every CP unit listed in cpapp-b.bin's unit directory (read-only)."""
from __future__ import annotations
import argparse, hashlib, struct, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))

from a6700win import patches, paths, windows_shim  # noqa: E402
paths.ensure_vendor_on_path()
from a6700_unlock.usb import legacy  # noqa: E402

import cp_read  # noqa: E402
from cp_read import CpReader  # noqa: E402

CATALOG = ROOT.parent / 'firmware' / 'cp' / 'cpapp-b.bin'
DIR_OFF = 0xC2A5B0
COUNT = 19


def catalog():
    d = CATALOG.read_bytes()
    out = []
    for i in range(COUNT):
        key, ram, size = struct.unpack_from('<III', d, DIR_OFF + i * 12)
        out.append((key, ram, size))
    return out


def classify(data: bytes) -> str:
    nz = sum(1 for b in data if b)
    if not nz:
        return 'all-zero'
    u16 = struct.unpack_from('<%dH' % (len(data) // 2), data, 0) if len(data) % 2 == 0 else ()
    if u16 and max(u16) <= 1024:
        inc = sum(1 for a, b in zip(u16, u16[1:]) if b >= a)
        if inc > 0.9 * (len(u16) - 1):
            return 'monotonic-u16<=1024 (LUT?)'
    vals = set(data)
    if len(vals) <= 4:
        return 'low-cardinality bytes %s' % sorted(vals)[:4]
    return 'other'


def log(msg):
    print(msg, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT.parent / 'firmware' / 'cp' / 'units'))
    ap.add_argument('--timeout', type=float, default=25.0)
    ap.add_argument('--skip-known', action='store_true')
    args = ap.parse_args(argv)

    units = catalog()
    log('目录 %d 项' % len(units))
    for key, ram, size in units:
        log('  0x%08x ram=0x%08x size=%d' % (key, ram, size))

    wanted = [(k, s) for k, _, s in units if s and s <= 0x100000]
    cp_read.CP_KEYS.update({k: s for k, s in wanted})
    if args.skip_known:
        wanted = [(k, s) for k, s in wanted if k not in (0x02A40001, 0x02A4000D)]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    patches.install()
    lock = windows_shim.device_lock(paths.state_dir())
    lock.__enter__()
    target = channel = None
    try:
        target, channel = legacy.run_authentication(None, 0x0336, args.timeout, True, progress=log)
        log('服务模式就绪 in=0x%02x out=0x%02x' % (target.endpoint_in, target.endpoint_out))
        reader = CpReader(target, channel)
        for key, size in wanted:
            started = time.monotonic()
            try:
                data = reader.read_unit(key)
            except SystemExit as exc:
                log('  0x%08x 失败：%s' % (key, exc))
                continue
            except Exception as exc:
                log('  0x%08x 异常：%s: %s' % (key, type(exc).__name__, exc))
                break
            path = out_dir / ('unit-%08x.bin' % key)
            path.write_bytes(data)
            nz = sum(1 for b in data if b)
            log('  0x%08x %6d B nz=%-6d sha=%s %-28s %.2fs' % (
                key, len(data), nz, hashlib.sha256(data).hexdigest()[:16], classify(data),
                time.monotonic() - started))
            log('      head %s' % data[:32].hex())
    finally:
        if target is not None:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
                log('已发送 STOP_SENSER')
            except Exception as exc:
                log('STOP 失败：%s' % exc)
            try:
                legacy.close_target(target)
            except Exception:
                pass
        lock.__exit__(None, None, None)


if __name__ == '__main__':
    main()
