from pathlib import Path

def ranges(a, b, maxr=40):
    out = []
    n = min(len(a), len(b))
    i = 0
    while i < n and len(out) < maxr:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out

for name in ('nflasha10', 'nflasha2', 'nflasha6'):
    a = Path(f'../firmware/parts/{name}-ext.bin').read_bytes()
    b = Path(f'../firmware/parts/{name}-def.bin').read_bytes()
    rs = ranges(a, b)
    total = sum(j-i for i, j in rs)
    print(f'== {name}: {len(rs)} ranges, {total} bytes differ')
    for i, j in rs[:20]:
        print(f'   {i:#010x}-{j:#010x} ({j-i} B)')
        print('     ext:', a[i:min(j, i+48)].hex())
        print('     def:', b[i:min(j, i+48)].hex())
