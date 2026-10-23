import re
d = open('../firmware/appFw-2.00.so','rb').read()
for w in ['Standard','Portrait','Neutral','Vivid','Sepia','Soft Highkey','SoftHighkey','Instant','Black & White','B&W','Cinema','Cine ','S-Cinetone','S-Cine','Cinetone','UserLUT','USER LUT','LUT Import','Import LUT','Import']:
    offs = [m.start() for m in re.finditer(re.escape(w.encode()), d)]
    print('%-14s %3d %s' % (w, len(offs), ' '.join(hex(x) for x in offs[:5])))