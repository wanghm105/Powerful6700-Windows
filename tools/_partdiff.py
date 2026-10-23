import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
from a6700win import patches, paths
paths.ensure_vendor_on_path()
patches.install()
from a6700win.research import ServiceSession

def progress(m): pass

targets = {
    "nflasha10": (12_582_912, "parts/nflasha10-def.bin"),
    "nflasha13": (4_194_304, "parts/nflasha13-def.bin"),
}
with ServiceSession(progress=progress) as session:
    for name, (size, ref) in targets.items():
        data = session.read_range("/dev/" + name, 0, size)["data"]
        local = Path("../firmware/" + ref).read_bytes()
        print(name, "sha", hashlib.sha256(data).hexdigest()[:16], "ref", hashlib.sha256(local).hexdigest()[:16])
        diffs = [i for i in range(min(len(data), len(local))) if data[i] != local[i]]
        print("  diff bytes", len(diffs))
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
            for a, b in runs[:10]:
                print("   run 0x%08x-0x%08x len %d" % (a, b, b - a + 1))
