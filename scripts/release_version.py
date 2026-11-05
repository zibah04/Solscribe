"""Validate release version consistency and expose it to Windows build steps."""
import ast
import os
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
values = {}
for node in ast.parse((root / 'solscribe' / '__init__.py').read_text()).body:
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = node.value.value
version, tag = values['__version__'], values['__release_tag__']
assert re.fullmatch(r'\d+\.\d+\.\d+', version)
assert tag == 'v' + version or re.fullmatch('v' + re.escape(version) + r'-(alpha|beta|rc)\.\d+', tag)
assert f'#define MyAppVersion "{version}"' in (root / 'SolScribe.iss').read_text()
assert f'OutputBaseFilename=SolScribe-Setup-{version}' in (root / 'SolScribe.iss').read_text()
info = (root / 'assets' / 'version_info.txt').read_text()
assert f"StringStruct('FileVersion', '{version}')" in info
assert f'filevers=({version.replace(".", ", ")}, 0)' in info
if os.getenv('GITHUB_ENV'):
    with Path(os.environ['GITHUB_ENV']).open('a', encoding='utf-8') as output:
        output.write(f'SOLSCRIBE_VERSION={version}\nSOLSCRIBE_RELEASE_TAG={tag}\n')
print('Release metadata verified:', tag)
