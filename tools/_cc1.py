import re
d = open('../firmware/appFw-2.00.so','rb').read()
def offs(p):
    return [m.start() for m in re.finditer(re.escape(p), d)]
print('--- word hits')
for w in ['Cinematic','Cinema','cine','CineMode','CC','CN']:
    o = offs(w.encode())
    print('%-10s %d %s' % (w, len(o), ' '.join(hex(x) for x in o[:6])))
print()
print('--- NUL-delimited 2-char code runs')
codes = [b'ST', b'PT', b'NT', b'VV', b'VV2', b'FL', b'IN', b'SH', b'BW', b'SE', b'CC', b'CN', b'AC', b'FL2', b'FL3']
hits = {c: offs(b'\x00' + c + b'\x00') for c in codes}
for c, hs in hits.items():
    print('%-4s %3d %s' % (c.decode(), len(hs), ' '.join(hex(h) for h in hs[:6])))