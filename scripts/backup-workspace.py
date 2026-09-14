#!/usr/bin/env python3
"""Create and verify a private SQLite editorial backup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    database = root / 'data/socialmediaplus.sqlite3'
    if not database.is_file():
        parser.error('Initialize the workspace first.')
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = root / 'backups' / ('editorial-' + stamp + '.zip')
    output.parent.mkdir(parents=True, exist_ok=True)
    source_roots = ['.gitignore', 'AGENTS.md', 'README.md', 'SOCIAL_MEDIA_PLUS.md', 'reports', 'pyproject.toml', 'config', 'profile',
                    'content', 'assets', 'data/imports', 'data/opportunities', 'data/action-attachments', 'network', 'workflows', '.agents/skills',
                    'research', 'src', 'scripts', 'tests', 'SMP Dashboard.command', 'ui/src', 'ui/public', 'ui/package.json', 'ui/package-lock.json', 'ui/tsconfig.json', 'ui/index.html', 'data/dashboard-uploads', 'templates', '.claude', 'docs', 'licenses', 'CLAUDE.md']
    paths = set()
    for relative in source_roots:
        base = root / relative
        candidates = [base] if base.is_file() else base.rglob('*') if base.is_dir() else []
        for path in candidates:
            if not path.is_file() or path.is_symlink():
                continue
            if any(x in path.parts for x in ('__pycache__', 'node_modules', '.git')):
                continue
            if path.name.startswith('.env') or path.name == 'api-key':
                continue
            # Do not follow an intermediate symlink outside the workspace.
            if not path.resolve().is_relative_to(root):
                raise RuntimeError('Refusing path outside workspace: ' + str(path))
            paths.add(path)
    manifest = {'created_at': stamp, 'scope': 'private editorial records and sources',
                'excludes': ['credentials', 'installed dependencies'],
                'files': {}}
    with tempfile.TemporaryDirectory(prefix='smp-backup-') as temporary:
        snapshot = Path(temporary) / 'socialmediaplus.sqlite3'
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('SQLite backup integrity check failed.')
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(paths):
                relative = str(path.relative_to(root))
                payload = path.read_bytes()
                archive.writestr(relative, payload)
                manifest['files'][relative] = hashlib.sha256(payload).hexdigest()
            payload = snapshot.read_bytes()
            archive.writestr('data/socialmediaplus.sqlite3', payload)
            manifest['files']['data/socialmediaplus.sqlite3'] = hashlib.sha256(payload).hexdigest()
            archive.writestr('BACKUP-MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(output) as archive:
        for name, expected in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise RuntimeError('Backup hash verification failed: ' + name)
    print(json.dumps({'path': str(output), 'verified_files': len(manifest['files']),
                      'sqlite_integrity': 'ok', 'mode': oct(output.stat().st_mode & 0o777),
                      'credentials_included': False}, indent=2))


if __name__ == '__main__':
    main()
