"""Find byte tables addressed via adrp+add then indexed by ldrb (look/mode maps)."""
import sys, numpy as np

PATH = '../firmware/appFw-2.00.so'
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30

def main():
    d = open(PATH,'rb').read()
    w = np.frombuffer(d, dtype='<u4', count=TEXT_SIZE//4, offset=TEXT_OFF)
    n = len(w)
    ldrb = np.nonzero((w & 0xFFE0FC00) == 0x38606800)[0]
    found = {}
    for i in ldrb:
        v = int(w[i]); rn = (v >> 5) & 31
        for k in range(1, 21):
            j = int(i) - k
            if j < 0: break
            x = int(w[j])
            if (x & 0xFFC00000) != 0x91000000:
                if (x & 0x9F000000) == 0x90000000 and ((x >> 5) & 31) == rn:
                    break
                continue
            imm12 = (x >> 10) & 0xFFF
            rn2 = (x >> 5) & 31
            rd = x & 31
            if rd != rn:
                continue
            for m in range(1, 8):
                y = int(w[j-m]) if j-m >= 0 else 0
                if (y & 0x9F000000) == 0x90000000 and ((y >> 5) & 31) == rn2:
                    imm = ((y >> 5) & 0x7FFFF) << 2 | ((y >> 29) & 3)
                    if imm & (1 << 20): imm -= 1 << 21
                    page = imm << 12
                    addr = page + imm12
                    found.setdefault(addr, []).append(TEXT_OFF + int(i)*4)
                    break
            break
    print('tables found', len(found))
    for addr in sorted(found):
        if not (0 < addr < len(d)): continue
        head = d[addr:addr+16]
        if len(head) < 16: continue
        if all(b < 0x21 for b in head):
            print('%#010x sites=%d  %s' % (addr, len(found[addr]), head.hex(' ')))

if __name__ == '__main__':
    main()