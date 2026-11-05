"""Official release validation and installer integrity; no meeting data involved."""
from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

REPOSITORY = 'zibah04/Solscribe'
RELEASES_API = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100'
MAX_INSTALLER_BYTES = 1024 ** 3


def version_key(tag):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta|rc)\.(0|[1-9]\d*))?', tag or '')
    if not match:
        raise ValueError('Unsupported release version')
    major, minor, patch, stage, number = match.groups()
    return int(major), int(minor), int(patch), {None: 3, 'rc': 2, 'beta': 1, 'alpha': 0}[stage], int(number or 0)


@dataclass(frozen=True)
class Update:
    tag: str
    filename: str
    url: str
    sha256: str
    size: int

    @property
    def page_url(self):
        return f'https://github.com/{REPOSITORY}/releases/tag/{quote(self.tag, safe="")}'

    @property
    def display_version(self):
        return self.tag.removeprefix('v').replace('-beta.', ' beta ').replace('-rc.', ' preview ')


def select_update(releases, current_tag, *, include_previews=True):
    if not isinstance(releases, list):
        raise ValueError('The update information could not be read')
    current = version_key(current_tag)
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') is not False:
            continue
        tag = release.get('tag_name')
        try:
            key = version_key(tag)
        except (TypeError, ValueError):
            continue
        if key <= current or (not include_previews and (release.get('prerelease') or key[3] < 3)):
            continue
        candidates.append((key, release))
    if not candidates:
        return None
    key, release = max(candidates, key=lambda item: item[0])
    tag = release['tag_name']
    filename = f'SolScribe-Setup-{key[0]}.{key[1]}.{key[2]}.exe'
    url = f'https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe="")}/{filename}'
    assets = release.get('assets')
    matches = [item for item in assets if isinstance(item, dict) and item.get('name') == filename] if isinstance(assets, list) else []
    if len(matches) != 1:
        raise ValueError('The new version is still being prepared. Please try again later')
    asset = matches[0]
    digest, size = asset.get('digest', ''), asset.get('size')
    if asset.get('browser_download_url') != url or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest or ''):
        raise ValueError('This update could not be verified. Please try again later')
    if type(size) is not int or not 0 < size <= MAX_INSTALLER_BYTES:
        raise ValueError('This update has an unsupported download size')
    return Update(tag, filename, url, digest.split(':')[1].lower(), size)


def trusted_url(url, *, download=False):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
        return False
    if download:
        return (parts.hostname == 'github.com' and parts.path.startswith(f'/{REPOSITORY}/releases/download/')) or parts.hostname in {
            'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
    return parts.hostname == 'api.github.com' and parts.path.startswith(f'/repos/{REPOSITORY}/releases')


def verify_installer(path, update):
    path = Path(path)
    if path.is_symlink() or path.name != update.filename or path.stat().st_size != update.size:
        raise ValueError('The downloaded update has changed. Please download it again')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != update.sha256:
        raise ValueError('The downloaded update could not be verified. Please download it again')
    return path
