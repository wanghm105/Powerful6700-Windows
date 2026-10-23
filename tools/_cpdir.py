import struct
d = open('../firmware/cp/cpapp-b.bin','rb').read()
lo, hi = 0xc2a380, 0xc2a800
i = lo
while i < hi:
    seg = d[i:i+16]
    u = struct.unpack('<4I', seg)
    print('%#010x  %s  | %s' % (i, ' '.join('%08x' % x for x in u), ''.join(chr(b) if 32<=b<127 else '.' for b in seg)))
    i += 16
print()
for off in (0xc2a580-0x40, 0xc2a5bc-0x20):
    print('--- around', hex(off))
    for j in range(off, off+0x60, 8):
        print('  %#010x %s' % (j, ' '.join('%08x' % x for x in struct.unpack('<2I', d[j:j+8]))))