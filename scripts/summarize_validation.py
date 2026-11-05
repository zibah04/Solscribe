"""Publish compact synthetic-test evidence to the normal Actions job summary."""
import json
import os
from pathlib import Path
from run_tests import annotation

lines = ['# SolScribe build evidence', '', 'Measurements use synthetic test data. Physical audio acceptance remains separate.', '']
for name in ('performance-windows.json', 'speech-source-metrics.json', 'speech-packaged-metrics.json'):
    path = Path(name)
    if path.is_file():
        value = json.loads(path.read_text(encoding='utf-8'))
        lines.extend(['## ' + name, '', '```json', json.dumps(value, indent=2), '```', ''])
        print('::notice title=' + name + '::' + annotation(json.dumps(value)))
checksums = Path('SHA256SUMS.txt')
if checksums.is_file():
    value = checksums.read_text(encoding='utf-8-sig')
    lines.extend(['## SHA256', '', '```text', value, '```'])
    print('::notice title=Release checksums::' + annotation(value))
if os.getenv('GITHUB_STEP_SUMMARY'):
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as summary:
        summary.write('\n'.join(lines))
