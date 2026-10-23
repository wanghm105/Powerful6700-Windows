import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
from a6700win import patches, paths, windows_shim
paths.ensure_vendor_on_path()
patches.install()
from a6700_unlock.usb import legacy
from cp_read import CpReader
from cp_write import CpWriter

factory = Path("../firmware/cp/unit-02a40001.factory.bin").read_bytes()
with windows_shim.device_lock(paths.state_dir()):
    target = None
    try:
        target, channel = legacy.run_authentication(None, 0x0336, 25.0, True, progress=lambda m: None)
        writer = CpWriter(target, channel)
        writer.write_unit(0x02A40001, factory)
        back = CpReader(target, channel).read_unit(0x02A40001)
        diffs = sum(1 for a, b in zip(back, factory) if a != b)
        print("回写出厂态：回读差异字节 =", diffs)
    finally:
        if target is not None:
            try:
                legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
            except Exception:
                pass
