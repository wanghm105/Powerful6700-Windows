import sys, time, hashlib
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
from a6700win import patches, paths
paths.ensure_vendor_on_path()
patches.install()
from a6700win.usb import setupapi
from a6700win.research import ServiceSession

def runlist(diffs):
    if not diffs:
        return []
    runs = []
    start = prev = diffs[0]
    for i in diffs[1:]:
        if i - prev <= 16:
            prev = i
            continue
        runs.append((start, prev))
        start = prev = i
    runs.append((start, prev))
    return runs

cpapp = Path("../firmware/cp/cpapp-b.bin").read_bytes()
JOBS = [
    ("nflasha10", "/dev/nflasha10", 0, Path("../firmware/parts/nflasha10-def.bin").read_bytes(), "../firmware/parts/nflasha10-now.bin"),
    ("cpapp-b", "/dev/nflasha8", 0x24C000, cpapp, "../firmware/cp/cpapp-b.now.bin"),
    ("nflasha2", "/dev/nflasha2", 0, Path("../firmware/parts/nflasha2-def.bin").read_bytes(), "../firmware/parts/nflasha2-now.bin"),
]
CHUNK = 0x40000

print("waiting for MSC ...", flush=True)
deadline = time.monotonic() + 240
while time.monotonic() < deadline:
    if 0x0E76 in setupapi.present_pids():
        break
    time.sleep(0.5)
else:
    print("timeout")
    raise SystemExit(1)
print("MSC ready", flush=True)

with ServiceSession(progress=lambda m: None) as session:
    for label, dev, off, ref, keep in JOBS:
        t0 = time.monotonic()
        parts = []
        pos = 0
        while pos < len(ref):
            n = min(CHUNK, len(ref) - pos)
            parts.append(session.read_range(dev, off + pos, n)["data"])
            pos += n
        data = b"".join(parts)
        diffs = [i for i in range(min(len(data), len(ref))) if data[i] != ref[i]]
        print("%s %d B %.1fs diff=%d" % (label, len(data), time.monotonic() - t0, len(diffs)), flush=True)
        for a, b in runlist(diffs)[:10]:
            print("  0x%08x..0x%08x len %d" % (a, b, b - a + 1), flush=True)
        if diffs:
            Path(keep).write_bytes(data)
