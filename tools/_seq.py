import numpy as np
d = open('../firmware/appFw-2.00.so','rb').read()
TEXT_OFF, TEXT_SIZE = 0x176d090, 0x1ec5c30
w = np.frombuffer(d, dtype='<u4', count=TEXT_SIZE//4, offset=TEXT_OFF)
imms = {}
for i, v in enumerate(w):
    v = int(v)
    if (v & 0xFF800000) == 0x52800000:
        imms[i] = ((v >> 5) & 0xFFFF, (v >> 0) & 31)   # (imm, rd)
seq = [0x10, 8, 0x0e, 0x0a, 0x0c, 9, 0x0f, 0x0b, 0x0d, 0x13]
print('movz', len(imms))
for window in (10, 12):
    for i in range(len(w) - window):
        vals = [imms.get(i + k, (None,))[0] for k in range(window)]
        if vals[:len(seq)] == seq:
            print(f'命中 @0x{TEXT_OFF + i*4:08x} 窗口{window}')
# 反向：只要求前 6 个匹配
for i in range(len(w) - 6):
    vals = [imms.get(i + k, (None,))[0] for k in range(12)]
    if vals[:6] == seq[:6]:
        print(f'前6匹配 @0x{TEXT_OFF + i*4:08x}: ' + ' '.join('-' if v is None else f'{v:x}' for v in vals))
