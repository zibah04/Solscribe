"""Attach an existing tested build to an existing private draft. Never publish."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

REPOSITORY = 'zibah04/Solscribe'
RUN_ID = '42032772170'
SOURCE = 'f1290dffb5aeffd204609d37959d862fbaebc802'
RELEASE_ID = 435226602
TAG = 'v0.4.1-beta.1'
EXPECTED = {
    'SolScribe-Setup-0.4.1.exe': '325eee3777266caf392e57158de24eabc2ac4f741c259405ba18a3ee13957ed8',
    'SolScribe-Portable-Windows.zip': '614748cde0b2982994b731861d339b5689f4a71e24f36666eacb7df03c486bb6',
}


def gh_json(*arguments):
    return json.loads(subprocess.check_output(['gh', *arguments], text=True))


def draft():
    release = gh_json('api', f'repos/{REPOSITORY}/releases/{RELEASE_ID}')
    if not release.get('draft') or not release.get('prerelease') or release.get('tag_name') != TAG:
        raise RuntimeError('The release must remain the expected private beta draft; no published release will be changed')
    return release


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def locate(root, name):
    matches = list(root.rglob(name))
    if len(matches) != 1 or not matches[0].is_file():
        raise RuntimeError(f'Expected one build output named {name}')
    return matches[0]


def main():
    run = gh_json('api', f'repos/{REPOSITORY}/actions/runs/{RUN_ID}')
    if run.get('status') != 'completed' or run.get('conclusion') != 'success' or run.get('head_sha') != SOURCE:
        raise RuntimeError('Only the exact successfully validated source build may be staged')
    draft()
    with tempfile.TemporaryDirectory(prefix='solscribe-release-') as directory:
        root = Path(directory)
        subprocess.run(['gh', 'run', 'download', RUN_ID, '--repo', REPOSITORY,
                        '--name', 'SolScribe-Windows', '--dir', directory], check=True)
        files = [locate(root, name) for name in EXPECTED]
        for path in files:
            if digest(path) != EXPECTED[path.name]:
                raise RuntimeError(f'Tested build checksum mismatch: {path.name}')
        identity = locate(root, 'BUILD_INFO.txt').read_text(encoding='utf-8-sig')
        if SOURCE not in identity or TAG not in identity:
            raise RuntimeError('Downloaded build identity does not match the tested source and release tag')
        files += [locate(root, name) for name in ('SHA256SUMS.txt', 'START_HERE.txt',
                  'RELEASE_NOTES.md', 'BUILD_INFO.txt', 'SIGNING_STATUS.txt', 'LICENSE',
                  'requirements-tested-windows.txt')]
        for path in files:
            state = draft()  # A user may change release state while this job runs.
            checksum = digest(path)
            existing = [asset for asset in state['assets'] if asset['name'] == path.name]
            if existing:
                if len(existing) != 1 or existing[0].get('digest') != 'sha256:' + checksum:
                    raise RuntimeError(f'An existing draft asset needs review: {path.name}')
            else:
                subprocess.run(['gh', 'release', 'upload', TAG, str(path), '--repo', REPOSITORY], check=True)
            asset = next(item for item in draft()['assets'] if item['name'] == path.name)
            if asset['size'] != path.stat().st_size or asset.get('digest') not in (None, 'sha256:' + checksum):
                raise RuntimeError(f'Uploaded draft asset failed verification: {path.name}')
            print(f'Verified private draft asset: {path.name} ({asset["size"]} bytes, SHA256 {checksum})')
        state = draft()
        print('::notice title=Private beta download staged::' + state['html_url'])
        print('The draft remains private. Public publication requires separate user approval.')


if __name__ == '__main__':
    main()
