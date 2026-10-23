import struct, sys
from pathlib import Path
fw = Path('../firmware')
app = (fw/'appFw-2.00.so').read_bytes()
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30

def callers(target, limit=40):
    out = []
    p = TEXT_OFF
    end = TEXT_OFF + TEXT_SIZE - 4
    while p < end:
        w = struct.unpack_from('<I', app, p)[0]
        if (w & 0xFC000000) == 0x94000000:
            off = w & 0x03FFFFFF
            if off & 0x02000000: off -= 0x04000000
            if p + off*4 == target:
                out.append(p)
                if len(out) >= limit: break
        p += 4
    return out

print('callers of 0x34e5604:', [hex(c) for c in callers(0x34e5604)])
for name in ('cp/cpapp-b.bin','cp/cpImg.dat','nflasha8-2.00.bin'):
    d = (fw/name).read_bytes()
    hits = []
    for p in range(0, len(d)-12, 4):
        key, addr, size = struct.unpack_from('<III', d, p)
        if 0x02a40000 <= key <= 0x02a400ff and 0 < size <= 0x40000 and addr > 0x1000:
            hits.append((hex(p), hex(key), hex(addr), hex(size)))
    print(name, 'unit records:', len(hits), hits[:8])
