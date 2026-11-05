"""Bound headless validation and expose failures as normal GitHub annotations."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def annotation(text):
    return str(text).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def main():
    result_file = Path('windows-tests.xml')
    command = [sys.executable, '-m', 'pytest', '-q', '--junitxml=' + str(result_file)]
    with Path('pytest-console.log').open('w', encoding='utf-8') as output:
        try:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=240,
                                    env={**os.environ, 'PYTHONUTF8': '1'})
            code = result.returncode
        except subprocess.TimeoutExpired:
            print('::error::Headless regression process exceeded 240 seconds; inspect the retained console log for the last test.')
            code = 1
    print(Path('pytest-console.log').read_text(encoding='utf-8', errors='replace'))
    if result_file.is_file():
        root = ET.parse(result_file).getroot()
        for item in list(root.iter('failure'))[:12] + list(root.iter('error'))[:12]:
            print('::error::' + annotation((item.text or item.get('message', 'Test failure'))[-5000:]))
        suite = root.find('testsuite') if root.tag != 'testsuite' else root
        if suite is not None:
            print('::notice title=Regression results::' + annotation(str(suite.attrib)))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
