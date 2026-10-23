import struct
cp = open('../firmware/cp/cpapp-b.bin','rb').read()
def probe(name, addr, size):
    print('--- %s  ram=%#x file=%#x size=%#x' % (name, addr, addr - 0x1000000, size))
    for j in range(addr - 0x1000000, addr - 0x1000000 + 0x30, 16):
        seg = cp[j:j+16]
        print('   %#010x %s | %s' % (j, seg.hex(' '), ''.join(chr(b) if 32<=b<127 else '.' for b in seg)))
probe('unit02a40001', 0x016f1094, 0x2000)
probe('unit02a4000d', 0x016f3594, 0x7000)
b = 0x016f1094 - 0x1000000
print('param bytes (0x1200 + 0..0x40):', cp[b+0x1200:b+0x1240].hex(' '))
print('chroma slot23 (0x1250+23*64):', cp[b+0x1250+23*64:b+0x1250+24*64].hex(' '))
print('chroma slot0:', cp[b+0x1250:b+0x1250+64].hex(' '))
b2 = 0x016f3594 - 0x1000000
print('unit0d param 0x196+55:', cp[b2+0x196:b2+0x196+0x20].hex(' '))
print('unit0d matrix slot23 (0x1e0+23*768):', cp[b2+0x1e0+23*768:b2+0x1e0+23*768+32].hex(' '))