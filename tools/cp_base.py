import struct, collections
p = '../firmware/cp/cpapp-b.bin'
d = open(p,'rb').read()
print('cp size', len(d), hex(len(d)))
strs = {'LookCategory_ERR': 0xa8589, 'LookName_ERR': 0xa85a1, 'InternalRec_ERR': 0xa8785,'SET_LOOKNAME_HEAD':0xa8560}
# collect all u32 aligned words once
import numpy as np
w = np.frombuffer(d[:len(d)//4*4], dtype='<u4')
def base_candidates(s):
    delta = (w.astype('uint64') - np.uint64(s)) & np.uint64(0xFFFFFFFF)
    # base must be positive, 0x1000-aligned
    ok = (delta % np.uint64(0x1000) == 0) & (delta > np.uint64(0)) & (delta < np.uint64(0x20000000))
    vals = collections.Counter(int(x) for x in delta[ok])
    return vals
per = {k: base_candidates(v) for k, v in strs.items()}
for k, c in per.items():
    print(k, 'candidates', len(c), c.most_common(6))
common = None
for k, c in per.items():
    s = set(c)
    common = s if common is None else (common & s)
print('intersection', sorted(common)[:10] if common else 'none')