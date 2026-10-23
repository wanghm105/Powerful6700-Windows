from pathlib import Path
fw = Path('../firmware')
n8 = (fw/'nflasha8-2.00.bin').read_bytes()
cp = (fw/'cp/cpapp-b.bin').read_bytes()
app = (fw/'appFw-2.00.so').read_bytes()

for key, addr, size in ((0x02a40001, 0x16f1094, 0x2000), (0x02a4000d, 0x16f3594, 0x7000)):
    print('unit', hex(key), 'ram', hex(addr), 'size', hex(size))
    for name, d in (('nflasha8', n8), ('cpapp', cp)):
        if addr + size <= len(d):
            seg = d[addr:addr+size]
            nz = sum(1 for b in seg if b)
            print('  ', name, 'in range; nonzero bytes =', nz, 'head:', seg[:24].hex(' '))
        else:
            print('  ', name, 'OUT OF RANGE (len', hex(len(d)), ')')

# where does cpapp sit inside nflasha8?
print('cpapp-in-n8 search:', n8.find(cp[:4096]))
