import numpy as np, capstone
d = open('../firmware/appFw-2.00.so','rb').read()
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
w = np.frombuffer(d, dtype='<u4', count=TEXT_SIZE//4, offset=TEXT_OFF)
MD = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
MD.detail = True
cmp_idx = np.nonzero((w & 0xFFC00000) == 0x71000000)[0]
out = []
for i in cmp_idx:
    v = int(w[i]); imm = (v >> 10) & 0xFFF
    if imm not in (9, 10, 11): continue
    nxt = int(w[i+1]) if i + 1 < len(w) else 0
    if (nxt & 0xFF00001F) != 0x54000008: continue
    addr = TEXT_OFF + int(i)*4
    ins = list(MD.disasm(d[addr:addr+64], addr))
    mns = [x.mnemonic for x in ins]
    if 'ldrb' not in mns or 'adr' not in mns or 'br' not in mns: continue
    tbl = None; page = None
    for x in ins:
        if x.mnemonic == 'adrp':
            page = x.operands[1].imm
        elif x.mnemonic == 'add' and page is not None and len(x.operands) == 3:
            try:
                tbl = page + x.operands[2].imm
            except Exception:
                tbl = None
            page = None
            if tbl and 0 < tbl < len(d):
                out.append((addr, imm, tbl, d[tbl:tbl+14].hex(' ')))
                break
print('resolved', len(out))
for addr, imm, tbl, hx in out:
    print('%#010x cmp #%-2d tbl=%#x %s' % (addr, imm, tbl, hx))