"""单会话内 dump 三块分区 + appFw 并与「刚解锁」备份逐字节对比。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from a6700win.research import ServiceSession  # noqa: E402

FW = ROOT.parent / "firmware"
TMP = ROOT / ".data" / "compare"
TMP.mkdir(parents=True, exist_ok=True)
CHUNK = 0x40000

JOBS = [
    ("/cp", "/dev/nflasha8", FW / "parts" / "nflasha8-ext.bin", 67108864),
    ("/setting", "/dev/nflasha2", FW / "parts" / "nflasha2-def.bin", 20971520),
    ("/usr", "/dev/nflasha15", FW / "parts" / "nflasha15-full.bin", 749731840),
    ("appFw", "/usr/lib/appFw.so", FW / "appFw-2.00.so", 89027992),
]


def fetch(session, path, size, out: Path):
    part = out.with_suffix(".part")
    done = part.stat().st_size if part.exists() else 0
    mode = "ab" if done else "wb"
    started = time.monotonic()
    with part.open(mode) as handle:
        while done < size:
            length = min(CHUNK, size - done)
            data = b""
            for attempt in range(6):
                try:
                    data = session.read_range(path, done, length)["data"]
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"    重试 {attempt + 1}/6 @0x{done:X}+0x{length:X}：{exc}", flush=True)
                    time.sleep(1.0)
                    if attempt >= 2 and length > 0x1000:
                        length = max(0x1000, length // 2)
            if not data:
                raise IOError(f"{path} @0x{done:X} 连续失败（已保存 {done:,} 字节）")
            if not data:
                raise SystemExit(f"{path} @0x{done:X} 读到 0 字节")
            handle.write(data)
            done += len(data)
            if done % (16 << 20) < CHUNK:
                rate = done / max(time.monotonic() - started, 1e-6)
                print(f"    {path} {done:,}/{size:,} （{rate / 1048576:.1f} MiB/s）", flush=True)
    if part.stat().st_size == size:
        part.replace(out)


def compare(live: Path, base: Path) -> str:
    a = live.read_bytes()
    b = base.read_bytes()
    n = min(len(a), len(b))
    diffs = [i for i in range(n) if a[i] != b[i]]
    tail = abs(len(a) - len(b))
    if not diffs and not tail:
        return f"完全一致 ✓ （{len(a):,} B）"
    spans = []
    for i in diffs:
        if spans and i == spans[-1][1] + 1:
            spans[-1][1] = i
        else:
            spans.append([i, i])
    head = "、".join(f"0x{lo:08X}+{hi - lo + 1}" for lo, hi in spans[:6])
    return f"差异 {len(diffs):,} 字节 / {len(spans)} 段（{head}{' …' if len(spans) > 6 else ''}）长度差 {tail}"


def main(argv=None) -> int:
    wanted = set(argv or [])
    jobs = [job for job in JOBS if not wanted or job[0] in wanted]
    pending = list(jobs)
    for attempt in range(1, 9):
        if not pending:
            break
        try:
            with ServiceSession() as session:
                for label, path, base, size in list(pending):
                    real = session.stat(path)
                    print(f"[{label}] 设备声明大小 {real:,} B（基线 {size:,} B）", flush=True)
                    size = min(size, real)
                    out = TMP / (label.replace("/", "") + ".bin")
                    if out.exists() and out.stat().st_size == size:
                        print(f"[{label}] 已有本地副本，跳过读取", flush=True)
                        print(f"[{label}] 对比 → {compare(out, base)}", flush=True)
                        pending.remove((label, path, base, size))
                        continue
                    if out.exists() and out.stat().st_size > size:
                        out.unlink()
                    print(f"[{label}] 读取 {path}（第 {attempt} 轮）…", flush=True)
                    fetch(session, path, size, out)
                    print(f"[{label}] 对比 → {compare(out, base)}", flush=True)
                    pending.remove((label, path, base, size))
        except (IOError, OSError, RuntimeError) as exc:
            print(f"第 {attempt} 轮中断：{exc}", flush=True)
    if pending:
        print("仍未完成：" + "、".join(str(job[0]) for job in pending), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
