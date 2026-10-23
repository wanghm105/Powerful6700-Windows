"""Find code pages that reference several caution-family bases: candidate id-arithmetic sites."""
import struct, sys
sys.path.insert(0, 'tools')
import rela as R
DATA = R.DATA
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
def movz_sites(imm):
    out = []
    for i in range(TEXT_OFF, TEXT_OFF + TEXT_SIZE - 4, 4):
        w, = struct.unpack_from("<I", DATA, i)
        if (w & 0xFFFFFFE0) == (0x52800000 | ((imm & 0xFFFF) << 5)):
            out.append(i)
    return out
FAMILIES = {0x16a: "XAVC", 0x18a: "SQ", 0x1bf: "PROXY_SQ", 0x1d4: "PROXY_SQ_1350"}
sites = {imm: set(movz_sites(imm)) for imm in FAMILIES}
for imm, s in sites.items(): print("%#06x %-14s %d sites" % (imm, FAMILIES[imm], len(s)))
print("--- pages (4 KiB) hosting >=2 different family bases")
pages = {}
for imm, s in sites.items():
    for a in s: pages.setdefault(a & ~0xFFF, set()).add(imm)
for page, imms in sorted(pages.items()):
    if len(imms) >= 2:
        print("%#010x  %s" % (page, ", ".join("%#06x(%s)" % (i, FAMILIES[i]) for i in sorted(imms))))
print("--- pairs within 0x800 of each other")
all_sites = sorted((a, imm) for imm, s in sites.items() for a in s)
for idx, (a, imm) in enumerate(all_sites):
    for b, imm2 in all_sites[idx+1:]:
        if b - a > 0x800: break
        if imm2 != imm: print("%#010x %#06x  ..  %#010x %#06x  (delta %#x)" % (a, imm, b, imm2, b - a))