import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
from a6700win import patches, paths, windows_shim
paths.ensure_vendor_on_path()
patches.install()
from a6700_unlock.usb import legacy
from cp_read import CpReader

factory = Path("../firmware/cp/unit-02a40001.factory.bin").read_bytes()
with windows_shim.device_lock(paths.state_dir()):
    target = None
    try:
        target, channel = legacy.run_authentication(None, 0x0336, 25.0, True, progress=lambda m: None)
        reader = CpReader(target, channel)
        unit = reader.read_unit(0x02A40001)
        print("live sha256", hashlib.sha256(unit).hexdigest()[:16], "factory", hashlib.sha256(factory).hexdigest()[:16])
        diffs = [i for i in range(len(unit)) if unit[i] != factory[i]]
        print("diff bytes", len(diffs))
        slots = {}
        for i in diffs:
            if 0x1250 <= i < 0x1250 + 54 * 64:
                slots.setdefault((i - 0x1250) // 64, 0)
                slots[(i - 0x1250) // 64] += 1
            else:
                slots.setdefault("other@%x" % i, 0)
        print("diff groups", {k: v for k, v in list(slots.items())[:12]})
    finally:
        if target is not None:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            except Exception:
                pass
