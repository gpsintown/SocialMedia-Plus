#!/usr/bin/env python3
"""Audit the public file allowlist, without printing secret values."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT_FILES = {
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'SOCIAL_MEDIA_PLUS.md', 'LICENSE',
    'THIRD_PARTY_NOTICES.md', 'SECURITY.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
    'pyproject.toml', '.gitignore', '.gitattributes', '.env.example',
    'SMP Dashboard.command', 'RELEASE-MANIFEST.json',
}
PUBLIC_DIRS = {'src', 'scripts', 'tests', 'docs', 'templates', 'workflows', 'licenses'}
PRIVATE_DIRS = {'profile', 'data', 'content', 'assets', 'network', 'reports', 'research',
                'backups', 'runtime', 'tmp', 'exports', 'services'}
SKIP_PARTS = {'node_modules', '__pycache__', '.git', '.venv', 'venv', '.pytest_cache'}
REQUIRED_FILES = {
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'SOCIAL_MEDIA_PLUS.md', 'LICENSE',
    'THIRD_PARTY_NOTICES.md', '.gitignore', '.env.example', 'pyproject.toml',
    'scripts/smp', 'scripts/smp-install.py', 'scripts/smp-start.py',
    'scripts/smp-dashboard.py', 'scripts/smp-mcp.py', 'scripts/release-check.py',
    'scripts/build-release.py', 'src/socialmediaplus/store.py',
    'src/socialmediaplus/dashboard/server.py', 'src/socialmediaplus/mcp.py',
    'config/chat-commands.json', 'templates/config/settings.json',
    'templates/config/dashboard.json', 'templates/config/engagement-plus.json',
    'templates/profile/profile.json', 'templates/profile/claims.json',
    'ui/src/main.tsx', 'ui/dist/index.html', 'ui/package.json', 'ui/package-lock.json',
    'licenses/react-LICENSE', 'licenses/react-dom-LICENSE', 'licenses/scheduler-LICENSE',
    '.agents/skills/smp-copilot/SKILL.md', '.claude/skills/smp-copilot/SKILL.md',
    'workflows/install.md', 'workflows/dashboard-queue.md',
    'docs/linkedin-setup.md', 'docs/codex-setup.md', 'docs/claude-setup.md',
    'tests/test_release_runtime.py', 'tests/test_release_package.py',
}


def allowed(relative):
    parts = relative.parts
    if any(p in SKIP_PARTS or p.endswith('.egg-info') for p in parts):
        return False
    if relative.name.endswith(('.pyc', '.pyo')) or relative.name == '.DS_Store':
        return False
    if len(parts) == 1:
        return relative.name in ROOT_FILES
    if parts[0] in PUBLIC_DIRS:
        return True
    if parts[:2] in (('.agents', 'skills'), ('.agents', 'agents'), ('.agents', 'council'), ('.claude', 'skills'),
                     ('.claude', 'agents'), ('.github', 'workflows')):
        return True
    if parts[0] == 'config':
        return str(relative) in {'config/chat-commands.json', 'config/discovery.json'}
    if parts[0] == 'ui':
        return parts[1] in {'src', 'dist', 'public'} or str(relative) in {
            'ui/package.json', 'ui/package-lock.json', 'ui/tsconfig.json', 'ui/index.html'}
    return False


def candidates(root):
    return sorted(p for p in root.rglob('*') if (p.is_file() or p.is_symlink())
                  and allowed(p.relative_to(root)))


PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'service token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})\b'),
    'personal machine path': re.compile(r'/(?:Users|home)/[A-Za-z0-9._-]+/'),
    'embedded account credential': re.compile(r'(?im)^[ \t]*(?:LINKEDIN_\w*(?:SECRET|TOKEN)|OPENAI_API_KEY|ANTHROPIC_API_KEY|DATABASE_PASSWORD)[ \t]*=[ \t]*[\"\']?[A-Za-z0-9_+/=-]{20,}'),
}


def audit(root, forbidden=(), require_complete=True):
    issues, hashes = [], {}
    if require_complete:
        for relative in sorted(REQUIRED_FILES):
            if not (root / relative).is_file():
                issues.append({'file': relative, 'reason': 'required public source or license is missing'})
    for p in candidates(root):
        rel = str(p.relative_to(root))
        if p.is_symlink() or not p.resolve().is_relative_to(root):
            issues.append({'file': rel, 'reason': 'symlinks are excluded from public releases'})
            continue
        if p.name.startswith('.env') and p.name != '.env.example':
            issues.append({'file': rel, 'reason': 'credential file'})
        if p.suffix.lower() in {'.sqlite3', '.sqlite', '.db', '.pdf', '.docx', '.zip', '.pem', '.key'}:
            issues.append({'file': rel, 'reason': 'private/binary document type is not release source'})
        raw = p.read_bytes()
        hashes[rel] = hashlib.sha256(raw).hexdigest()
        value = raw.decode('utf-8', errors='replace')
        for label, pattern in PATTERNS.items():
            if pattern.search(value):
                issues.append({'file': rel, 'reason': label})
        for phrase in forbidden:
            if phrase and phrase.casefold() in value.casefold():
                issues.append({'file': rel, 'reason': 'private audit denylist match'})
                break
    return {'ok': not issues, 'files_checked': len(hashes), 'issues': issues,
            'scope': 'public allowlist; ignored local runtime is never exported', 'sha256': hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--deny-file', type=Path, help='Private newline-delimited phrases; values never printed')
    args = parser.parse_args()
    forbidden = args.deny_file.read_text().splitlines() if args.deny_file else []
    result = audit(args.root.resolve(), forbidden)
    result.pop('sha256')
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
