"""读 CP 单元 0x02a40001 的参数表，看 40..63 是否为「槽 → bank」映射。"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from a6700win import patches  # noqa: E402
from a6700win import paths  # noqa: E402

paths.ensure_vendor_on_path()
from a6700_unlock.usb import legacy  # noqa: E402
from cp_read import CpReader  # noqa: E402

patches.install()
target, channel = legacy.run_authentication(None, 0x0336, 12.0, True, progress=lambda m: print("·", m))
try:
    unit = CpReader(target, channel).read_unit(0x02A40001)
    out = ROOT / ".data" / "cp" / "unit-02a40001.now.bin"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(unit)
    table = unit[0x1200:0x1300]
    print("参数 0..63：", " ".join(f"{table[i]:02X}" for i in range(64)))
    print("参数 40..63（十进制）：", [table[i] for i in range(40, 64)])
    print("参数 64..127：", [table[i] for i in range(64, 128)])
finally:
    legacy.vendor_request_out(target.device, legacy.STOP_SENSER, strict=False)
    legacy.close_target(target)
