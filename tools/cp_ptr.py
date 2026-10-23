"""Find Thumb movw/movt pairs in cpapp-b.bin and report materialised addresses."""
import struct, sys, collections

PATH = '../firmware/cp/cpapp-b.bin'
LO, HI = 0xFBF000, 0x1120000     # initialized-data block .. a bit past its end
d = open(PATH, 'rb').read()
print('cpapp', len(d))

def h(i):
    return struct.unpack_from('<H', d, i)[0]

def movw_imm(hw1, hw2):
    # hw1: 11110 i 10 0100 imm4 ; hw2: 0 imm3 Rd imm8
    if (hw1 & 0xFBF0) != 0xF240: return None
    i = (hw1 >> 10) & 1
    imm4 = hw1 & 0xF
    imm3 = (hw2 >> 12) & 0x7
    imm8 = hw2 & 0xFF
    rd = (hw2 >> 8) & 0xF
    return rd, (imm4 << 12) | (imm3 << 8) | imm8

def movt_imm(hw1, hw2):
    if (hw1 & 0xFBF0) != 0xF2C0: return None
    i = (hw1 >> 10) & 1
    imm4 = hw1 & 0xF
    imm3 = (hw2 >> 12) & 0x7
    imm8 = hw2 & 0xFF
    rd = (hw2 >> 8) & 0xF
    return rd, (imm4 << 12) | (imm3 << 8) | imm8

hits = collections.Counter()
sites = []
for i in range(0, len(d) - 8, 2):
    a = movw_imm(h(i), h(i+2))
    if not a: continue
    rd, lo = a
    # movt within next 4 halfwords to same rd
    for j in range(i+4, min(i+16, len(d)-4), 2):
        b = movt_imm(h(j), h(j+2))
        if b and b[0] == rd:
            addr = (b[1] << 16) | lo
            if LO <= addr < HI:
                sites.append((i, j, addr, rd))
            break
print('pairs into data block:', len(sites))
for i, j, addr, rd in sites[:80]:
    print('  movw@%#010x movt@%#010x -> %#010x r%d' % (i, j, addr, rd))
