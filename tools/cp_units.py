import numpy as np, struct
d = open('../firmware/cp/cpapp-b.bin','rb').read()
w = np.frombuffer(d[:len(d)//4*4], dtype='<u4')
hits = np.nonzero((w & 0xFFFF0000) == 0x02a40000)[0]
print('02a4xxxx words:', len(hits))
for i in hits[:40]:
    off = int(i)*4
    print('  %#010x key=%#010x next=%s' % (off, int(w[i]), ' '.join('%08x' % int(x) for x in w[i+1:i+5])))
print()
for k in (0x02a40001, 0x02a4000d):
    idx = np.nonzero(w == k)[0]
    print('key %#x at %s' % (k, [hex(int(i)*4) for i in idx]))