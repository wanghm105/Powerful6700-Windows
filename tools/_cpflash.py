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
print("waiting for MSC ...", flush=True)
deadline = time.monotonic() + 270
while time.monotonic() < deadline:
    if 0x0E76 in setupapi.present_pids():
        break
    time.sleep(0.5)
else:
    print("timeout: camera never appeared as 0x0E76")
    raise SystemExit(1)

REGIONS = [
    ("unit01 params+chroma", 0x5E8794, 0x2000),
    ("unit0d matrix", 0x5EAC94, 0x2000),
]
with ServiceSession(progress=lambda m: None) as session:
    for label, off, length in REGIONS:
        data = session.read_range("/dev/nflasha8", off, length)["data"]
        ref = local[off:off + length]
        diffs = [i for i in range(min(len(data), len(ref))) if data[i] != ref[i]]
        print("%s @0x%x diff=%d" % (label, off, len(diffs)))
        if diffs:
            runs = []
            start = prev = diffs[0]
            for i in diffs[1:]:
                if i - prev <= 8:
                    prev = i
                    continue
                runs.append((start, prev))
                start = prev = i
            runs.append((start, prev))
            for a, b in runs[:12]:
                print("   run +0x%04x..+0x%04x len %d" % (a, b, b - a + 1))
            if label.startswith("unit01"):
                slots = sorted({(i - 0x1250) // 64 for i in diffs if i >= 0x1250})
                print("   chroma slots touched:", slots)
