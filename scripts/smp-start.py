#!/usr/bin/env python3
"""Start or check the local SQLite dashboard. No Docker or social API calls."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PACKAGE)
    parser.add_argument('--port', type=int)
    parser.add_argument('--check', action='store_true', help='Read-only readiness check; do not start a process.')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    cfg_path = root / 'config/dashboard.json'
    try:
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        port = args.port if args.port is not None else cfg.get('port', 4010)
        if type(port) is not int or not 1024 <= port <= 65535:
            parser.error('--port must be between 1024 and 65535')
        if not (root / 'data/socialmediaplus.sqlite3').is_file():
            print(json.dumps({'ready': False, 'error': 'Run scripts/smp-install.py --root PATH --host codex (or claude) first.'}))
            return 1
        result = subprocess.run([sys.executable, str(PACKAGE / 'scripts/smp-dashboard.py'), '--root', str(root), '--port', str(port),
                                 '--check' if args.check else '--background'], capture_output=True, text=True, timeout=25)
        report = {'ready': result.returncode == 0, 'runtime_ready': result.returncode == 0, 'storage': 'sqlite',
                  'dashboard': {'running': result.returncode == 0, 'url': f'http://127.0.0.1:{port}'},
                  'listener': cfg.get('listener', {'status': 'not_installed', 'verified': False}),
                  'linkedin_authentication': 'not_tested', 'actions': [] if args.check else ['ensure_local_dashboard']}
        if result.returncode:
            report['error'] = 'Dashboard unavailable or port belongs to another workspace. Inspect reports/private/dashboard/server.log.'
        print(json.dumps(report, indent=2))
        return 0 if report['ready'] else 1
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print(json.dumps({'ready': False, 'error': 'Unable to read local configuration or start the dashboard.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
