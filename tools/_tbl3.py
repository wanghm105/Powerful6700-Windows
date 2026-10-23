import struct
d = open('../firmware/appFw-2.00.so','rb').read()
# find the run of 8-byte records shaped 00 aa 02 01 vvvvvvvv around 0x43c7000
def rec_ok(o):
    return d[o] == 0x00 and d[o+2] == 0x02 and d[o+3] == 0x01
start = 0x43c7645
while rec_ok(start - 8): start -= 8
end = start
while rec_ok(end): end += 8
print('table', hex(start), '-', hex(end), 'records', (end-start)//8)
from collections import defaultdict
fam = defaultdict(list)
for o in range(start, end, 8):
    a = d[o+1]; v = struct.unpack_from('<I', d, o+4)[0]
    fam[a].append(v)
for a in sorted(fam):
    vs = fam[a]
    print(' fam %#04x  n=%-3d %s' % (a, len(vs), ' '.join('%#x' % v for v in sorted(set(vs))[:24])))