import sys, time, hashlib
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
from a6700win import patches, paths
paths.ensure_vendor_on_path()
patches.install()
from a6700win.usb import setupapi
from a6700win.research import ServiceSession

local = Path("../firmware/cp/cpapp-b.bin").read_bytes()
CP_START = 0x24C000
size = len(local)
print("waiting for MSC ...", flush=True)
deadline = time.monotonic() + 200
while time.monotonic() < deadline:
    if 0x0E76 in setupapi.present_pids():
        break
    time.sleep(0.5)
else:
    print("timeout")
    raise SystemExit(1)

t0 = time.monotonic()
with ServiceSession(progress=lambda m: None) as session:
    data = session.read_range("/dev/nflasha8", CP_START, size)["data"]
print("read %d bytes in %.1fs" % (len(data), time.monotonic() - t0))
print("sha  live", hashlib.sha256(data).hexdigest()[:16])
print("sha local", hashlib.sha256(local).hexdigest()[:16])
diffs = [i for i in range(min(len(data), len(local))) if data[i] != local[i]]
print("diff bytes", len(diffs))
if diffs:
    runs = []
    start = prev = diffs[0]
    for i in diffs[1:]:
        if i - prev <= 16:
            prev = i
            continue
        runs.append((start, prev))
        start = prev = i
    runs.append((start, prev))
    print("runs", len(runs))
    for a, b in runs[:15]:
        print("  0x%08x..0x%08x len %d" % (a, b, b - a + 1))
