import json
from pathlib import Path
p = json.loads(Path('../refs/a7c2-fl23/src/camera_runtime/assets/patches.json').read_text(encoding='utf-8'))
for idx, chip in enumerate(p):
    print('=== chip', idx, 'src', chip['source_sha256'][:12], 'writes', len(chip['writes']))
    for w in chip['writes']:
        print(' %s  %s -> %s  | %s' % (w['file_offset'], w['before_hex'], w['after_hex'], w['purpose']))
