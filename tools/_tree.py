import struct, hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
sys.path.insert(0, str(Path("src").resolve()))
import ext4_walk
from a6700win.research import ServiceSession

OUT = Path("../firmware/ui")
OUT.mkdir(parents=True, exist_ok=True)
NAME = "string_simplifiedchinese.uxc"

def progress(message):
    print(message, flush=True)

with ServiceSession(progress=progress) as session:
    fs = ext4_walk.Ext2(session, "/dev/nflasha15")
    app = fs.lookup("/share/app")
    rows = fs.entries(app)
    lines = []
    for row in sorted(rows, key=lambda r: r["name"]):
        child = fs.inode(row["ino"])
        kind = "d" if child["mode"] & 0o170000 == 0o040000 else "-"
        lines.append("%s %12d  %s" % (kind, child["size"], row["name"]))
    (OUT / "listing-share-app.txt").write_text("\n".join(lines), "utf-8")
    print("目录清单 %d 项 -> %s" % (len(lines), OUT / "listing-share-app.txt"), flush=True)
    match = [r for r in rows if r["name"] == NAME]
    node = fs.inode(match[0]["ino"])
    data = fs.read_file(node)
    target = OUT / NAME
    target.write_bytes(data)
    print("保存 %s %d 字节 sha256=%s" % (NAME, len(data), hashlib.sha256(data).hexdigest()), flush=True)

raw = (OUT / NAME).read_bytes()
MAGIC = b"uxc" + bytes([7, 0, 0, 0, 0])
print("头部", raw[:16].hex(), "len", len(raw), flush=True)
if raw[:8] == MAGIC:
    kind, group, descriptor = struct.unpack_from("<HHI", raw, 8)
    count = descriptor & 0x1FFF
    base = (16 + count * 2 + 3) & ~3
    print("kind=%d group=%d descriptor=0x%08x count=%d base=%d" % (kind, group, descriptor, count, base), flush=True)
    entries = {}
    for i in range(count):
        pointer = struct.unpack_from("<H", raw, 16 + 2 * i)[0]
        if pointer == 0xFFFF:
            continue
        at = base + pointer * 4
        rid = 0x02000000 | (group << 13) + i
        end = raw.find(bytes([0]), at + 4)
        if end < 0:
            continue
        entries[rid] = raw[at + 4:end]
    print("解析出 %d 条" % len(entries), flush=True)
    for rid in range(0x0200AB2C, 0x0200AB32):
        print("  rid 0x%08x -> %r" % (rid, entries.get(rid)), flush=True)
    for rid, text in entries.items():
        if text and any(k in text for k in (b"FL", b"VV2", b"SEPIA", b"Sepia")):
            print("  命中 %s -> %r" % (hex(rid), text), flush=True)
