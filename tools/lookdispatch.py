import numpy as np
d = open('../firmware/appFw-2.00.so','rb').read()
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
w = np.frombuffer(d, dtype='<u4', count=TEXT_SIZE//4, offset=TEXT_OFF)
br = np.nonzero((w & 0xFFFFFC1F) == 0xD61F0000)[0]
hits = []
for i in br:
    if i < 3: continue
    add = int(w[i-1]); adr = int(w[i-2])
    if (add & 0xFFE00000) != 0x8B200000: continue
    if (adr & 0x9F000000) != 0x10000000: continue
    pairs = 0; k = i + 1; vals = []
    while k + 1 < len(w):
        m0 = int(w[k]); m1 = int(w[k+1])
        if (m0 & 0xFF800000) == 0x52800000 and (m1 & 0xFC000000) == 0x14000000:
            vals.append((m0 >> 5) & 0xFFFF); pairs += 1; k += 2
        else:
            break
    if pairs < 8: continue
    bound = None; tbl = None
    for j in range(i-1, max(i-16, 0), -1):
        v = int(w[j])
        if (v & 0xFFC00000) == 0x71000000:
            bound = (v >> 10) & 0xFFF; break
        if (v & 0x7F800000) == 0x11000000:
            rn = (v >> 5) & 31; imm12 = (v >> 10) & 0xFFF
            for m in range(j-1, max(j-6, 0), -1):
                y = int(w[m])
                if (y & 0x9F000000) == 0x90000000 and ((y >> 5) & 31) == rn:
                    imm = ((y >> 5) & 0x7FFFF) << 2 | ((y >> 29) & 3)
                    if imm & (1 << 20): imm -= 1 << 21
                    tbl = (imm << 12) + imm12; break
            break
    hits.append((TEXT_OFF + int(i)*4, pairs, bound, tbl, vals))
print('total', len(hits))
for addr, pairs, bound, tbl, vals in sorted(hits):
    tb = ('%#x:%s' % (tbl, d[tbl:tbl+16].hex(' '))) if tbl and 0 < tbl < len(d) else '-'
    print('%#010x n=%-2d bound=%-4s tbl=%-40s %s' % (addr, pairs, bound, tb, ' '.join('%x' % v for v in vals[:14])))