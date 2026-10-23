import struct
n8 = open('../firmware/nflasha8-2.00.bin','rb').read()
print('nflasha8', len(n8), hex(len(n8)))
for base in (0x016efe94, 0x016f1094, 0x016f3594):
    print('--- %#x' % base)
    for j in range(base, base+0x40, 16):
        seg = n8[j:j+16]
        print('  %#010x %s | %s' % (j, seg.hex(' '), ''.join(chr(b) if 32<=b<127 else '.' for b in seg)))
    p = base + 0x1200
    print('  param area %#x: %s' % (p, n8[p:p+64].hex(' ')))
    c = base + 0x1250
    print('  chroma area %#x: %s' % (c, n8[c:c+64].hex(' ')))