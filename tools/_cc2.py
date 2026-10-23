d = open('../firmware/appFw-2.00.so','rb').read()
def lst(lo, hi, label):
    print('==', label, hex(lo), '-', hex(hi))
    i = lo
    while i < hi:
        j = d.find(b'\x00', i)
        if j < 0: break
        s = d[i:j]
        if s and all(32 <= b < 127 for b in s):
            print('  %#010x %s' % (i, s.decode()))
        i = j + 1
lst(0x366de80, 0x366df60, 'cluster A (SE/AC/CC)')
lst(0x388af00, 0x388af60, 'cluster B (FL)')
lst(0x388ba20, 0x388bb00, 'cluster C (CN/IN)')