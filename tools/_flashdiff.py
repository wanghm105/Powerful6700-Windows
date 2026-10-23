import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
from a6700win import patches, paths
paths.ensure_vendor_on_path()
patches.install()
from a6700win.research import ServiceSession

CP_START = 0x24C000
local = Path("../firmware/cp/cpapp-b.bin").read_bytes()

def progress(m):
    pass

with ServiceSession(progress=progress) as session:
    for label, off, length in [
        ("param+chroma", 0x1200, 0x2000),
        ("unit0d", 0x5EAC94, 0x2000),
    ]:
        data = session.read_range("/dev/nflasha8", CP_START + off, length)["data"]
        ref = local[off:off + length]
        diffs = [i for i in range(min(len(data), len(ref))) if data[i] != ref[i]]
        print("%s offset=0x%x len=%d diff=%d" % (label, off, len(data), len(diffs)))
        if diffs:
            groups = {}
            for i in diffs:
                if label == "param+chroma":
                    if i < (0x1250 - 0x1200):
                        key = "param@0x%x" % (0x1200 + i)
                    else:
                        key = "chroma_slot_%d" % ((i - (0x1250 - 0x1200)) // 64)
                else:
                    key = "unitd@0x%x" % (off + i)
                groups[key] = groups.get(key, 0) + 1
            for key, count in list(groups.items())[:20]:
                print("   ", key, count)
