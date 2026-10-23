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
    ("cpapp-b", "/dev/nflasha8", 0x24C000, cpapp, "../firmware/cp/cpapp-b.now.bin"),
    ("nflasha10", "/dev/nflasha10", 0, Path("../firmware/parts/nflasha10-def.bin").read_bytes(), "../firmware/parts/nflasha10-now.bin"),
    ("nflasha2", "/dev/nflasha2", 0, Path("../firmware/parts/nflasha2-def.bin").read_bytes(), "../firmware/parts/nflasha2-now.bin"),
]

print("waiting for MSC ...", flush=True)
deadline = time.monotonic() + 300
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
        data = session.read_range(dev, off, len(ref))["data"]
        diffs = [i for i in range(min(len(data), len(ref))) if data[i] != ref[i]]
        print("%s %d B %.1fs live=%s ref=%s diff=%d" % (
            label, len(data), time.monotonic() - t0,
            hashlib.sha256(data).hexdigest()[:12], hashlib.sha256(ref).hexdigest()[:12], len(diffs)), flush=True)
        for a, b in runlist(diffs)[:12]:
            print("  0x%08x..0x%08x len %d" % (a, b, b - a + 1))
        if diffs:
            Path(keep).write_bytes(data)
