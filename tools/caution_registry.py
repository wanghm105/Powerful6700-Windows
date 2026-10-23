"""Export the whole caution/message registry (0x4958148..0x4968148) to a text file."""
import struct, sys
sys.path.insert(0, 'tools')
import rela as R
DATA = R.DATA
def s(addr, maxlen=200):
    if not (0x3000000 <= addr < len(DATA)): return ""
    end = DATA.find(b"\0", addr)
    if 0 < end - addr < maxlen: return DATA[addr:end].decode("latin1", "replace")
    return ""
base, stop = 0x4958148, 0x4968148
out = []
for off in range(base, stop, 16):
    name, packed = struct.unpack_from("<QQ", DATA, off)
    text = s(name)
    if not text: continue
    out.append("%#06x len=%#05x %#010x %s" % (packed & 0xFFFFFFFF, packed >> 32, off, text))
dst = R.Path(__file__).resolve().parent.parent.parent / "firmware" / "caution-registry.txt"
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
print("entries", len(out), "->", dst)