"""Loopback-only HTTP interface; no arbitrary files, shell commands or SQL."""
import json
import mimetypes
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..store import Error, Store, now
from .. import reports, workflow
from . import records, settings


VIEWS = {
 'content': ('content', 'title', 'updated_at'),
 'assets': ('assets', 'alt_text', 'created_at'),
 'engagement': ('actions', 'response', 'created_at'),
 'network': ('relationships', 'name', 'updated_at'),
 'opportunities': ('opportunities', 'title', 'observed_at'),
 'insights': ('metrics', 'metric', 'observed_at'),
 'runs': ('dashboard_requests', 'command', 'created_at'),
}


def listing(s, view, query):
    table, search, order = VIEWS[view]
    page = max(1, min(100000, int(query.get('page', ['1'])[0])))
    term = query.get('q', [''])[0][:200]
    where, args = [], []
    if term:
        where.append('instr(lower(' + search + '),lower(?)) > 0')
        args.append(term)
    if view == 'insights' and query.get('scope', [''])[0]:
        where.append('scope=?')
        args.append(query['scope'][0])
    if view == 'network':
        if query.get('membership', [''])[0]:
            where.append('EXISTS(SELECT 1 FROM relationship_memberships m WHERE m.relationship_id=relationships.id AND m.membership=?)')
            membership = query['membership'][0]
            args.append('follower' if membership == 'follower_only' else membership)
            if membership == 'follower_only':
                where.append("NOT EXISTS(SELECT 1 FROM relationship_memberships c WHERE c.relationship_id=relationships.id AND c.membership='connection')")
        if query.get('bucket', [''])[0]:
            where.append('bucket=?')
            args.append(query['bucket'][0])
    sql_where = ' WHERE ' + ' AND '.join(where) if where else ''
    total = s.one('SELECT COUNT(*) n FROM ' + table + sql_where, args)['n']
    columns = '*'
    if view == 'runs':
        columns = 'id,command,state,model,effort,created_at,updated_at,result'
    if view == 'opportunities':
        columns = 'id,job_url,company,title,country,observed_at,contact_id,created_at'
    rows = s.all('SELECT ' + columns + ' FROM ' + table + sql_where + ' ORDER BY ' + order + ' DESC,id DESC LIMIT 30 OFFSET ?', args + [(page-1)*30])
    for row in rows:
        if view == 'runs':
            row['expires_at'] = records.expires_at(row)
        if view == 'network':
            row['memberships'] = [x['membership'] for x in s.all('SELECT membership FROM relationship_memberships WHERE relationship_id=?', (row['id'],))]
        if view == 'assets':
            row['url'] = '/api/asset/' + row['id']
            row['extension'] = Path(row['path']).suffix.lower()
    return {'rows': rows, 'total': total, 'page': page, 'page_size': 30}


def overview(s):
    status = reports.status(s)
    cfg = records.configuration(s)
    return {'observed_at': now(), 'status': status, 'desktop': cfg,
        'workspace': {'owner': s.settings.get('owner') or 'Your workspace', 'timezone': s.settings['timezone']},
        'services': {'dashboard': True, 'storage': 'sqlite', 'automatic_dispatch_verified': False},
        'linkedin': settings.status(s.root),
        'next_posts': s.all("SELECT id,title,format,status,scheduled_at,publishing_authority FROM content WHERE scheduled_at IS NOT NULL ORDER BY scheduled_at LIMIT 12"),
        'activity': s.all('SELECT id,kind,state,response,target_url,updated_at FROM actions ORDER BY updated_at DESC LIMIT 6'),
        'runs': s.all('SELECT id,command,state,created_at,result FROM dashboard_requests ORDER BY created_at DESC LIMIT 8'),
        'buckets': s.all('SELECT bucket,COUNT(*) count FROM relationships GROUP BY bucket ORDER BY count DESC'),
        'experiments': s.all('SELECT * FROM experiments ORDER BY created_at DESC LIMIT 10')}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, port=4010):
        self.root = Path(root).resolve()
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)
        self.allowed_hosts = {f'127.0.0.1:{self.server_port}', f'localhost:{self.server_port}'}
        self.last_maintenance = 0

    def service_actions(self):
        if time.monotonic() - self.last_maintenance < 30:
            return
        self.last_maintenance = time.monotonic()
        s = None
        try:
            s = Store(self.root)
            records.expire_pending(s)
        except Exception:
            # A maintenance failure does not authorize dispatch; dispatch independently
            # checks expiry. Keep serving records while the database recovers.
            pass
        finally:
            if s:
                s.close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'SMP'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt, *args):
        # URLs, incoming text and payloads may be private.
        pass

    def send(self, status, body, kind='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        asset_policy = "object-src 'self'; frame-ancestors 'self'" if kind == 'application/pdf' else "object-src 'none'; frame-ancestors 'none'"
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; base-uri 'none'; " + asset_policy)
        self.end_headers()
        self.wfile.write(body)

    def validate(self, mutation=False):
        if self.headers.get('Host') not in self.server.allowed_hosts:
            raise Error('Invalid local host.')
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + h for h in self.server.allowed_hosts}:
            raise Error('Cross-origin requests are disabled.')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Error('Cross-site requests are disabled.')
        if mutation and not secrets.compare_digest(self.headers.get('X-SMP-Token', ''), self.server.token):
            raise Error('Refresh the local dashboard session before making changes.')

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, mutation):
        s = None
        try:
            self.validate(mutation)
            parsed = urlsplit(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            if not path.startswith('/api/'):
                if mutation:
                    raise Error('Unsupported route.')
                relative = 'index.html' if path == '/' else path.lstrip('/')
                build = (self.server.root / 'ui/dist').resolve()
                p = (build / relative).resolve()
                if not p.is_relative_to(build) or not p.is_file():
                    self.send(404, {'error': 'Page not found. Build the dashboard first.'})
                    return
                self.send(200, p.read_bytes(), mimetypes.guess_type(p)[0] or 'application/octet-stream')
                return
            s = Store(self.server.root)
            if mutation:
                length = int(self.headers.get('Content-Length', '0'))
                limit = 30*1024*1024 if path == '/api/upload' else 32000
                if not 0 < length <= limit:
                    raise Error('Invalid request size.')
                raw = self.rfile.read(length)
                if path == '/api/upload':
                    ext = query.get('extension', [''])[0].lower()
                    if ext not in ('zip', 'csv', 'xlsx'):
                        raise Error('Choose a LinkedIn ZIP, CSV or XLSX export.')
                    relative = f'data/dashboard-uploads/{uuid.uuid4().hex}.{ext}'
                    s.write(relative, raw, exclusive=True)
                    self.send(201, {'file': relative})
                    return
                body = json.loads(raw)
                if path == '/api/shutdown':
                    self.send(200, {'stopping': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if path == '/api/settings/linkedin':
                    self.send(200, settings.save(s.root, body))
                    return
                if path == '/api/requests':
                    result = records.enqueue(s, body['command'], body.get('params', {}), body['idempotency_key'], body.get('snapshot'))
                    self.send(201, result)
                    return
                if path.startswith('/api/cancel/'):
                    row = records.get(s, path.split('/')[-1])
                    if row['state'] not in ('queued', 'waiting'):
                        raise Error('This request has been dispatched; an exact Desktop turn interruption is required.')
                    self.send(200, records.transition(s, row['id'], 'cancelled', 'Cancelled by the dashboard user before dispatch.'))
                    return
                raise Error('Unsupported action.')
            if path == '/api/session':
                self.send(200, {'token': self.server.token, 'service': 'smp-dashboard', 'root': str(s.root)})
            elif path == '/api/settings/linkedin':
                self.send(200, settings.status(s.root))
            elif path == '/api/overview':
                self.send(200, overview(s))
            elif path == '/api/commands':
                self.send(200, records.contract(s))
            elif path == '/api/insights':
                self.send(200, {
                    'metrics': s.all('SELECT m.*,c.title,c.format,c.pillar FROM metrics m LEFT JOIN content c ON c.id=m.content_id ORDER BY m.observed_at DESC'),
                    'assets': s.all('SELECT a.id,a.content_id,a.alt_text,a.active,c.title,c.format,c.status FROM assets a JOIN content c ON c.id=a.content_id'),
                    'activity': s.all('SELECT kind,state,COUNT(*) count FROM actions GROUP BY kind,state'),
                    'history': s.all('SELECT kind,COUNT(*) count FROM history GROUP BY kind'),
                    'experiments': s.all('SELECT * FROM experiments ORDER BY created_at DESC LIMIT 20'),
                    'note': 'Outgoing actions and exports are not measurements of received engagement. Missing metrics remain unavailable.'})
            elif path.startswith('/api/list/') and path.split('/')[-1] in VIEWS:
                self.send(200, listing(s, path.split('/')[-1], query))
            elif path.startswith('/api/request/'):
                self.send(200, records.get(s, path.split('/')[-1]))
            elif path.startswith('/api/content/'):
                row = workflow.content_show(s, path.split('/')[-1])
                version = next(v for v in row['versions'] if v['version'] == row['current_version'])
                row['text'] = s.read_checked(version['path'], version['sha256']).read_text()
                row['metrics'] = s.all('SELECT * FROM metrics WHERE content_id=? ORDER BY observed_at DESC', (row['id'],))
                self.send(200, row)
            elif path.startswith('/api/person/'):
                row = s.require('relationships', path.split('/')[-1])
                row['interactions'] = s.all('SELECT * FROM interactions WHERE relationship_id=? ORDER BY occurred_at DESC LIMIT 50', (row['id'],))
                self.send(200, row)
            elif path.startswith('/api/action/'):
                row = s.require('actions', path.split('/')[-1])
                row['receipts'] = s.all('SELECT * FROM receipts WHERE action_id=? ORDER BY observed_at DESC', (row['id'],))
                self.send(200, row)
            elif path.startswith('/api/opportunity/'):
                row = s.require('opportunities', path.split('/')[-1])
                row['evidence'] = json.loads(row.pop('evidence_json'))
                row['actions'] = s.all('SELECT a.* FROM actions a JOIN action_details d ON d.action_id=a.id WHERE d.opportunity_id=? ORDER BY a.created_at DESC', (row['id'],))
                self.send(200, row)
            elif path == '/api/snapshot':
                params = {k: v[0] for k, v in query.items()}
                _, params, _ = records.parse_command(s, 'SCHEDULE', params)
                batch = records.snapshot(s, params)
                for item in batch:
                    version = s.one('SELECT path,sha256 FROM versions WHERE content_id=? AND version=?', (item['id'], item['version']))
                    item['text'] = s.read_checked(version['path'], version['sha256']).read_text()
                    item['assets'] = s.all('SELECT id,alt_text,path FROM assets WHERE content_id=? AND active=1', (item['id'],))
                self.send(200, {'items': batch, 'snapshot': records.snapshot(s, params)})
            elif path.startswith('/api/asset/'):
                row = s.require('assets', path.split('/')[-1])
                p = s.read_checked(row['path'], row['sha256'])
                kind = mimetypes.guess_type(p)[0]
                if kind not in ('image/png', 'image/jpeg', 'image/webp', 'application/pdf', 'video/mp4'):
                    kind = 'application/octet-stream'
                self.send(200, p.read_bytes(), kind)
            else:
                self.send(404, {'error': 'Unknown route.'})
        except (Error, ValueError, KeyError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(500, {'error': 'Unable to read this record. Check the local service and registered file integrity.'})
        finally:
            if s:
                s.close()
