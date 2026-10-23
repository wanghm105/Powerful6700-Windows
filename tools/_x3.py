import json
from pathlib import Path
d = json.loads(Path('../refs/a7c2-fl23/src/camera_runtime/assets/fx2_fl23_donor.json').read_text(encoding='utf-8'))
for look in d['looks']:
    print(look['look'], 'param', look['target_parameter'], 'slot', look['target_slot'], 'gamma', look.get('gamma'), 'used', look.get('used'))
    ms = look['matrix_slots']
    print('  matrix type', type(ms).__name__, (list(ms)[:3] if isinstance(ms, dict) else len(ms)))
    if isinstance(ms, dict):
        for k, v in ms.items():
            print('   ', k, type(v).__name__, (len(v) if hasattr(v,'__len__') else v))
            if isinstance(v, list):
                print('     first 12:', v[:12], 'len', len(v))
                if v and isinstance(v[0], list):
                    print('     row0:', v[0])
            break
    print('  cc1_int16:', str(look.get('cc1_int16'))[:200])
    print('  banks:', look.get('donor_block13_bank'), look.get('donor_cc1_bank'))
