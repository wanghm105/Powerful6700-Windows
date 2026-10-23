import struct
from pathlib import Path
raw = Path("../firmware/ui/string_simplifiedchinese_f.uxc").read_bytes()
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
Path("../firmware/ui/f-entries.txt").write_text(
    "\n".join("%08x %s" % (rid, t.decode("utf-8", "replace")) for rid, t in rows), "utf-8")
looks = ["标准", "人像", "中性", "鲜明", "亮丽", "胶片", "复古", "通透", "黑白", "棕褐", "外观"]
out = ["group=%d count=%d base=%d 解析 %d 条" % (group, count, base, len(rows))]
for rid, t in rows:
    s = t.decode("utf-8", "replace")
    if len(s) <= 8 and (any(k == s or s.startswith(k) for k in looks) or s.startswith("自定义")):
        out.append("%08x %s" % (rid, s))
Path("../firmware/ui/_f-looks.txt").write_text("\n".join(out), "utf-8")
