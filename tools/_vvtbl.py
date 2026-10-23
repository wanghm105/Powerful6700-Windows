import struct
d = open('../firmware/appFw-2.00.so','rb').read()
lo, hi = 0x537df20, 0x537e080
i = lo
while i < hi:
    seg = d[i:i+16]
    u = struct.unpack('<4I', seg)
    print('%#010x  %s  | %s' % (i, ' '.join('%08x' % x for x in u), ''.join(chr(b) if 32<=b<127 else '.' for b in seg)))
    i += 16