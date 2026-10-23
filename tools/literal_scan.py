"""Scan .text for literal-pool words equal to a 32-bit constant (ldr w?, =imm)."""
import struct, sys
sys.path.insert(0, 'tools')
import rela as R
DATA = R.DATA
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
def scan(imm, limit=60):
    out = []
    target = struct.pack("<I", imm)
    start = TEXT_OFF
    while len(out) < limit:
        hit = DATA.find(target, start, TEXT_OFF + TEXT_SIZE)
        if hit < 0: break
        if hit % 4 == 0:
            out.append(hit)
        start = hit + 1
    return out
for imm in (0x98c, 0x97e, 0x980, 0x182, 0x19f, 0x981):
    sites = scan(imm)
    print("%#07x  %d literal-pool hit(s): %s" % (imm, len(sites), ", ".join("%#x" % s for s in sites[:20])))