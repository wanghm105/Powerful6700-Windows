import struct
from pathlib import Path
app = Path('../firmware/appFw-2.00.so').read_bytes()
start = 0x34e55f0
cand = None
for p in range(start-4, start-0x1200, -4):
    w = struct.unpack_from('<I', app, p)[0]
    if (w & 0xFFC07FFF) == 0xA9807BFD:   # stp x29, x30, [sp, #-imm]!
        cand = p; break
print('prologue candidate:', hex(cand) if cand else None)
if cand:
    # find callers of cand
    TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
    out = []
    for p in range(TEXT_OFF, TEXT_OFF+TEXT_SIZE-4, 4):
        w = struct.unpack_from('<I', app, p)[0]
        if (w & 0xFC000000) == 0x94000000:
            off = w & 0x03FFFFFF
            if off & 0x02000000: off -= 0x04000000
            if p + off*4 == cand: out.append(hex(p))
    print('callers:', len(out), out[:12])
