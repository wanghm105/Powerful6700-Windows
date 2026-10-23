d = open('../firmware/appFw-2.00.so','rb').read()
def dump(lo, hi):
    i = lo
    while i < hi:
        seg = d[i:i+16]
        print('%#010x %s  %s' % (i, seg.hex(' '), ''.join(chr(b) if 32 <= b < 127 else '.' for b in seg)))
        i += 16
print('table at 0x40ce568, 12 bytes:', d[0x40ce568:0x40ce568+12].hex(' '))
print('as u16:', [hex(x) for x in __import__('struct').unpack_from('<12H', d, 0x40ce568)])
print()
dump(0x40ce540, 0x40ce5b0)