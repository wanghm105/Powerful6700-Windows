import numpy as np
d = open('../firmware/appFw-2.00.so','rb').read()
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
w = np.frombuffer(d, dtype='<u4', count=TEXT_SIZE//4, offset=TEXT_OFF)
ldrb = np.nonzero((w & 0xFFE0FC00) == 0x38606800)[0]
print('ldrb reg sites', len(ldrb))
cmp_base = 0x71000000
cmp_mask = 0xFFC00000
hits = []
for i in ldrb:
    for k in range(1, 9):
        if i - k < 0: break
        v = int(w[i-k])
        if (v & cmp_mask) == cmp_base:
            imm = (v >> 10) & 0xFFF
            if imm in (9, 10, 11, 12, 15, 16):
                hits.append((TEXT_OFF + int(i)*4, imm, k))
            break
print('candidates', len(hits))
for a, imm, k in hits[:40]:
    print('  %#010x cmp #%d (%d back)' % (a, imm, k))