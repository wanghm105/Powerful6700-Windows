d = open('../firmware/appFw-2.00.so','rb').read()
o = 0x43c7645
lo, hi = o-0x40, o+0x60
i = lo
while i < hi:
    seg = d[i:i+16]
    print('%#010x %s  %s' % (i, seg.hex(' '), ''.join(chr(b) if 32 <= b < 127 else '.' for b in seg)))
    i += 16