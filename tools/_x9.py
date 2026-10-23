from pathlib import Path
app = Path('../firmware/appFw-2.00.so').read_bytes()
pats = {
  '10 0f 11 12': bytes([0x10,0x0f,0x11,0x12]),
  '0f 10 11 12': bytes([0x0f,0x10,0x11,0x12]),
  '0d 0f 10 11': bytes([0x0d,0x0f,0x10,0x11]),
  '03 02 01 10': bytes([0x03,0x02,0x01,0x10]),
  '00 03 02 01 10 0f 11 12 05 0d': bytes([0,3,2,1,0x10,0x0f,0x11,0x12,5,0x0d]),
  '12 00 02 04 06 08 0a 0c 0e 10': bytes([0x12,0,2,4,6,8,0x0a,0x0c,0x0e,0x10]),
}
for name, pat in pats.items():
    hits = []
    p = app.find(pat)
    while p != -1 and len(hits) < 8:
        hits.append(hex(p)); p = app.find(pat, p+1)
    print(name, '->', len(hits), hits)
