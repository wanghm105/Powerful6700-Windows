import struct, hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
import ext4_walk
from a6700win.research import ServiceSession

OUT = Path("../firmware/ui")
NAMES = ["string_simplifiedchinese_f.uxc", "string_simplifiedchinese_func_j.uxc", "string_simplifiedchinese_g.uxc"]
PROBES = ["胶片", "复古", "通透", "亮丽", "鲜明", "人像", "中性", "棕褐", "自定义 1", "自定义 6"]

def progress(message):
    print(message, flush=True)

report = []
with ServiceSession(progress=progress) as session:
    fs = ext4_walk.Ext2(session, "/dev/nflasha15")
    app = fs.lookup("/share/app")
    rows = {r["name"]: r["ino"] for r in fs.entries(app)}
    for name in NAMES:
        ino = rows.get(name)
        if not ino:
            report.append("%s 不存在" % name)
            continue
        node = fs.inode(ino)
        data = fs.read_file(node)
        (OUT / name).write_bytes(data)
        head = data[:8] == b"uxc" + bytes([7, 0, 0, 0, 0])
        group = count = None
        if head:
            kind, group, descriptor = struct.unpack_from("<HHI", data, 8)
            count = descriptor & 0x1FFF
        hits = [p for p in PROBES if p.encode("utf-8") in data]
        report.append("%s %d 字节 uxc=%s group=%s count=%s 命中=%s" % (name, len(data), head, group, count, hits))
Path("../firmware/ui/_variants.txt").write_text("\n".join(report), "utf-8")
