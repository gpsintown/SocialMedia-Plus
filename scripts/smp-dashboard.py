#!/usr/bin/env python3
"""Run the private dashboard in the foreground; process control stays explicit."""
import argparse
import json
import sys
import os
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from socialmediaplus.dashboard.server import Server

p = argparse.ArgumentParser()
p.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
p.add_argument('--port', type=int, default=4010)
p.add_argument('--check', action='store_true', help='Check the existing local dashboard')
p.add_argument('--stop', action='store_true', help='Stop only the dashboard serving this workspace')
p.add_argument('--background', action='store_true', help='Start detached from this terminal and verify readiness')
a = p.parse_args()
url = f'http://127.0.0.1:{a.port}'
try:
    with urllib.request.urlopen(url + '/api/session', timeout=2) as response:
        running = json.load(response)
except (OSError, ValueError):
    running = None
if running and (running.get('service') != 'smp-dashboard' or running.get('root') != str(Path(a.root).resolve())):
    p.error('Port belongs to a different service or workspace; leaving it unchanged.')
if a.stop:
    if running:
        req = urllib.request.Request(url+'/api/shutdown', data=b'{}', headers={'X-SMP-Token': running['token'], 'Content-Type':'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=3) as response:
            print(response.read().decode())
    else:
        print(json.dumps({'running':False}))
    raise SystemExit(0)
if a.check:
    print(json.dumps({'running':bool(running), 'url':url, 'root':str(Path(a.root).resolve())}))
    raise SystemExit(0 if running else 1)
if running:
    print('Social Media Plus is already running: '+url)
    raise SystemExit(0)
if a.background:
    root = Path(a.root).resolve()
    logdir = root / 'reports/private/dashboard'
    logdir.mkdir(parents=True, exist_ok=True)
    fd = os.open(logdir / 'server.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'a') as log:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--root', str(root), '--port', str(a.port)],
                                 cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True, close_fds=True)
    for _ in range(40):
        try:
            with urllib.request.urlopen(url + '/api/session', timeout=1) as response:
                info = json.load(response)
            if info.get('service') == 'smp-dashboard' and info.get('root') == str(root):
                print(json.dumps({'running': True, 'url': url, 'mode': 'background'}))
                raise SystemExit(0)
        except (OSError, ValueError):
            pass
        if child.poll() is not None:
            break
        time.sleep(.25)
    print(json.dumps({'running': False, 'url': url, 'error': 'Startup failed; inspect reports/private/dashboard/server.log'}))
    raise SystemExit(1)
server = Server(a.root, a.port)
print(f'Social Media Plus: http://127.0.0.1:{server.server_port}', flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
