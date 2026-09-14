#!/usr/bin/env python3
"""Create a fresh public source ZIP from the audited allowlist, never Git history."""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location('release_check', Path(__file__).with_name('release-check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--deny-file', type=Path)
    args = p.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.is_relative_to(root):
        p.error('Choose an output path outside the source workspace.')
    forbidden = args.deny_file.read_text().splitlines() if args.deny_file else []
    report = check.audit(root, forbidden)
    if not report['ok']:
        report.pop('sha256')
        print(json.dumps(report, indent=2))
        return 1
    files = check.candidates(root)
    manifest = {'format': 1, 'scope': report['scope'], 'files': {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = str(path.relative_to(root))
            if relative == 'RELEASE-MANIFEST.json':
                continue
            raw = path.read_bytes()
            checksum = check.hashlib.sha256(raw).hexdigest()
            if checksum != report['sha256'][relative]:
                raise RuntimeError('Source changed during export; discard archive and retry after edits finish.')
            archive.writestr('social-media-plus/' + relative, raw)
            manifest['files'][relative] = checksum
        archive.writestr('social-media-plus/RELEASE-MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(output) as archive:
        for name, checksum in manifest['files'].items():
            if check.hashlib.sha256(archive.read('social-media-plus/' + name)).hexdigest() != checksum:
                raise RuntimeError('Archive verification failed.')
    print(json.dumps({'archive': str(output), 'verified_files': len(manifest['files']),
                      'private_runtime_exported': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
