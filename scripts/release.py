#!/usr/bin/env python3
"""Prepare versions, validate metadata and build a source release using the stdlib."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
                    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?')
PAYLOAD_FILES = (
    'VERSION', 'app_version.py', 'app.py', 'calendar_data.py', 'race_results.py',
    'podiums-2026.json', 'install.py', 'style.css', 'motogp-logo.svg', 'icon.png',
    'motogp.lua', 'README.md', 'CHANGELOG.md',
)
PAYLOAD_DIRS = ('circuits', 'icons', 'plugin', 'docs', 'scripts', 'tests')


def validate_version(value):
    match = SEMVER.fullmatch(value)
    if not match or any(part.isdigit() and len(part) > 1 and part.startswith('0')
                        for part in (match[4] or '').split('.')):
        raise ValueError(f'Invalid version: {value!r}. Use X.Y.Z or X.Y.Z-rc.N.')
    return value


def version_key(value):
    match = SEMVER.fullmatch(validate_version(value))
    prerelease = tuple((0, int(part)) if part.isdigit() else (1, part)
                       for part in (match[4] or '').split('.') if part)
    return tuple(map(int, match.group(1, 2, 3))), match[4] is None, prerelease


def release_notes(root, version):
    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    section = re.search(r'^## \[' + re.escape(version)
                        + r'\] - (\d{4}-\d{2}-\d{2})\n(.*?)(?=^## |\Z)',
                        changelog, re.MULTILINE | re.DOTALL)
    if not section or not section[2].strip():
        raise ValueError(f'CHANGELOG.md needs dated release notes for {version}.')
    dt.date.fromisoformat(section[1])
    return section[2].strip() + '\n'


def check(root=ROOT, tag=None):
    version = validate_version((root / 'VERSION').read_text(encoding='utf-8').strip())
    manifest = json.loads((root / 'plugin/manifest.json').read_text(encoding='utf-8'))
    if manifest['version'] != version:
        raise ValueError('VERSION and plugin/manifest.json disagree.')
    if tag is not None and tag != f'v{version}':
        raise ValueError(f'Tag {tag!r} does not match VERSION (v{version}).')
    release_notes(root, version)
    return version


def prepare(root, version):
    validate_version(version)
    current = check(root)
    if version_key(version) <= version_key(current):
        raise ValueError(f'{version} must be newer than {current}.')
    path = root / 'CHANGELOG.md'
    changelog = path.read_text(encoding='utf-8')
    if re.search(r'^## \[' + re.escape(version) + r'\]', changelog, re.MULTILINE):
        raise ValueError(f'{version} already has release notes; released versions must not be reused.')
    unreleased = re.search(r'^## \[Unreleased\]\n(.*?)(?=^## |\Z)',
                           changelog, re.MULTILINE | re.DOTALL)
    if not unreleased or not re.search(r'^- \S', unreleased[1], re.MULTILINE):
        raise ValueError('Add changes under ## [Unreleased] before preparing a version.')
    entry = f'## [Unreleased]\n\n## [{version}] - {dt.date.today().isoformat()}\n'
    changelog = changelog[:unreleased.start()] + entry + unreleased[1] + changelog[unreleased.end():]
    manifest_path = root / 'plugin/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['version'] = version
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'VERSION').write_text(version + '\n', encoding='utf-8')
    path.write_text(changelog, encoding='utf-8')
    check(root)


def build(root, output, tag=None):
    version = check(root, tag)
    paths = [root / name for name in PAYLOAD_FILES]
    for directory in PAYLOAD_DIRS:
        folder = root / directory
        if not folder.is_dir():
            raise ValueError(f'Missing release directory: {directory}')
        paths.extend(p for p in folder.rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and not p.name.endswith(('.pyc', '.pyo')))
    output.mkdir(parents=True, exist_ok=True)
    basename = f'motogp-calendar-{version}'
    archive = output / f'{basename}.tar.gz'
    with archive.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as bundle:
            for path in sorted(paths):
                if path.is_symlink() or not path.is_file():
                    raise ValueError(f'Expected a regular release file: {path}')
                content = path.read_bytes()
                info = tarfile.TarInfo(f'{basename}/{path.relative_to(root).as_posix()}')
                info.size = len(content)
                info.mode = 0o755 if path.relative_to(root).as_posix() == 'plugin/bin/motogp-calendar' else 0o644
                bundle.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    (output / 'release-notes.md').write_text(release_notes(root, version), encoding='utf-8')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    validation = commands.add_parser('check', help='Check version, plugin and changelog agreement')
    validation.add_argument('--tag', help='Require a matching Git tag, e.g. v1.0.0')
    preparation = commands.add_parser('prepare', help='Move Unreleased notes into a new version')
    preparation.add_argument('version')
    packaging = commands.add_parser('build', help='Build an installable source archive and checksum')
    packaging.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    packaging.add_argument('--tag')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(ROOT, args.version)
            print(f'Prepared {args.version}. Review and commit the changes before tagging.')
        elif args.command == 'build':
            print(build(ROOT, args.output_dir, args.tag))
        else:
            print(f'Version metadata OK: {check(ROOT, args.tag)}')
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Release error: {error}\n')


if __name__ == '__main__':
    main()
