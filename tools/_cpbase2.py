import numpy as np, re
p = '../firmware/cp/cpapp-b.bin'
d = open(p,'rb').read()
w = np.frombuffer(d[:len(d)//4*4], dtype='<u4')
words = w.astype('uint64')
# sample strings: ASCII runs >= 12 bytes, at least 2 spaces or letters
cands = []
for m in re.finditer(rb'[ -~]{16,}', d):
    cands.append(m.start())
print('ascii runs', len(cands))
import random
random.seed(7)
sample = random.sample(cands, 200)
def coverage(B):
    hit = 0
    for s in sample:
        v = B + s
        if v > 0xFFFFFFFF: continue
        if np.any(words == v): hit += 1
    return hit
for B in [0, 0x548000, 0x558000, 0x558400, 0x5B8000, 0x1FA0000]:
    print('base %#x coverage %d/200' % (B, coverage(B)))