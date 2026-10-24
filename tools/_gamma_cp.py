import numpy as np, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = open('../firmware/cp/cpapp-b.bin','rb').read()
print('cpapp', len(d))
w = np.frombuffer(d, dtype='<u4')
mono = (w[1:] >= w[:-1])
# 129 点单调递增 u32 曲线（首点小、末点 ~0xFFFFxxxx）
run = 0; hits = []
for i, m in enumerate(mono):
    run = run + 1 if m else 0
    if run == 128:
        start = i - 127
        if w[start] < 0x1000 and w[start+128] > 0xF0000000:
            hits.append(start)
print('129 点 u32 单调曲线候选', len(hits))
for s in hits[:10]:
    print(f'  0x{s*4:08X} first={w[s]:#x} last={w[s+128]:#x}')
# A7C2 元数据标记 0x30010010
import struct
pat = struct.pack('<I', 0x30010010)
pos = 0; found = []
while True:
    pos = d.find(pat, pos)
    if pos < 0: break
    found.append(pos); pos += 1
print('0x30010010 命中', len(found), [hex(p) for p in found[:8]])
# 576 字节记录边界：129*4+60=576
print('576 对齐命中', [hex(p) for p in found if p % 576 == 0][:8])
