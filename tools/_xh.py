import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()
n = len(cp)
S = 0xFBF000
L = 0x1412b8
print('len', hex(n))
print('blob S..end', hex(S), hex(S+L), 'tail after blob', hex(n - (S+L)))
tail = cp[S+L:]
print('tail nonzero bytes:', sum(1 for b in tail if b))
print('preceding 32 bytes at S-0x20:', cp[S-0x20:S].hex(' '))
print('at S:', cp[S:S+32].hex(' '))
print('nonzero in blob:', sum(1 for b in cp[S:S+L] if b), '/', L)
# check a plausible struct field: does 0x20140 hold 0x1412b8 only once?
pat = struct.pack('<I', L)
hits = []
p = cp.find(pat)
while p != -1 and len(hits) < 6:
    hits.append(hex(p)); p = cp.find(pat, p+1)
print('occurrences of 0x1412b8:', hits)
