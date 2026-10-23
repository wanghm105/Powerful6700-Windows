import struct
from pathlib import Path
raw = Path("../firmware/ui/string_simplifiedchinese.uxc").read_bytes()
MAGIC = b"uxc" + bytes([7, 0, 0, 0, 0])
kind, group, descriptor = struct.unpack_from("<HHI", raw, 8)
count = descriptor & 0x1FFF
base = (16 + count * 2 + 3) & ~3
rows = []
for i in range(count):
    pointer = struct.unpack_from("<H", raw, 16 + 2 * i)[0]
    if pointer == 0xFFFF:
        continue
    at = base + pointer * 4
    rid = 0x02000000 | (group << 13) + i
    end = raw.find(bytes([0]), at + 4)
    if end < 0:
        continue
    rows.append((rid, raw[at + 4:end]))
out = Path("../firmware/ui/string_simplifiedchinese.txt")
out.write_text("\n".join("%08x %s" % (rid, text.decode("utf-8", "replace")) for rid, text in rows), "utf-8")
print("写出", out, len(rows), "条")
keys = ["标准", "人像", "中性", "鲜明", "亮丽", "胶片", "复古", "通透", "黑白", "棕褐", "外观", "自定义"]
for rid, text in rows:
    s = text.decode("utf-8", "replace")
    if len(s) <= 8 and any(k in s for k in keys):
        print("  %08x %s" % (rid, s))
