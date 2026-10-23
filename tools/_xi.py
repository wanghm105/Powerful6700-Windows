import json
from pathlib import Path
p = json.loads(Path('../refs/a7c2-fl23/src/camera_runtime/assets/patches.json').read_text(encoding='utf-8'))
for chip in p:
    print('=== source', chip['source_sha256'][:16], 'writes', len(chip['writes']))
    for w in chip['writes']:
        print(' %-10s %-28s -> %-28s %s' % (hex(w['file_offset']), w['before_hex'][:28], w['after_hex'][:28], w.get('purpose','')[:70]))
