import struct
from pathlib import Path
app = Path('../firmware/appFw-2.00.so').read_bytes()
RELA_OFF, RELA_SIZE = 0xe440, 0x1756dd0
target = 0x34e5604
found = []
for p in range(RELA_OFF, RELA_OFF + RELA_SIZE, 24):
    off, info, add = struct.unpack_from('<QQq', app, p)
    if add == target:
        found.append((hex(p), hex(off), hex(info)))
print('rela entries with addend == 0x34e5604:', len(found), found[:10])

# raw 8-byte pointers
raw = []
p = app.find(struct.pack('<Q', target))
while p != -1 and len(raw) < 10:
    raw.append(hex(p)); p = app.find(struct.pack('<Q', target), p+1)
print('raw u64 hits:', raw)
