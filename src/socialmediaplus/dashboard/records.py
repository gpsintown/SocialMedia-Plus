"""Dashboard request ledger. All writes use the project's Store transactions."""
import json
import re
from functools import wraps
from .settings import private_write
from datetime import date, datetime, timedelta

from ..store import Error, dump, digest, ident, now
from ..workflow import fingerprint


SCHEMA = """
CREATE TABLE IF NOT EXISTS dashboard_requests(
 id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
 command TEXT NOT NULL, params_json TEXT NOT NULL, prompt TEXT NOT NULL,
 state TEXT NOT NULL, desktop_host TEXT, thread_id TEXT NOT NULL, model TEXT NOT NULL, effort TEXT NOT NULL,
 turn_id TEXT, snapshot_json TEXT, result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dashboard_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL REFERENCES dashboard_requests(id),
 type TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
"""
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted', 'expired'}
TRANSITIONS = {
 'queued': {'dispatching', 'cancelled', 'waiting', 'expired'},
 'waiting': {'queued', 'cancelled', 'expired'},
 'dispatching': {'running', 'needs_reconciliation', 'failed'},
 'running': {'completed', 'failed', 'interrupted', 'needs_reconciliation'},
 'needs_reconciliation': {'running', 'completed', 'failed', 'interrupted'},
}
SESSION_COMMANDS = {'ENGAGE', 'ENGAGE+', 'NETWORK', 'DISCOVER', 'RECRUITERS', 'RECRUITER+', 'REPLIES'}


def notify(s):
    """Advisory file for desktop listeners; always query SQLite before acting."""
    pending = s.all("SELECT id,command,state,updated_at FROM dashboard_requests WHERE state NOT IN ('completed','failed','cancelled','interrupted','expired') ORDER BY created_at,id LIMIT 100")
    sequence = s.one('SELECT COALESCE(MAX(sequence),0) value FROM dashboard_events')['value']
    private_write(s.root / 'data/dashboard-queue.json', json.dumps({'schema': 1, 'sequence': sequence, 'pending': pending,
        'authoritative_source': 'data/socialmediaplus.sqlite3', 'note': 'Notification mirror only. Re-read the queue through the CLI or MCP before execution.'}, indent=2) + '\n')


def with_notification(fn):
    @wraps(fn)
    def wrapped(s, *args, **kwargs):
        result = fn(s, *args, **kwargs)
        try:
            notify(s)
        except (OSError, Error):
            # The committed ledger remains authoritative if the advisory file fails.
            pass
        return result
    return wrapped


def expires_at(row):
    # This is the latest permitted start, not the duration of a running session.
    delta = timedelta(minutes=30) if row['command'] in SESSION_COMMANDS else timedelta(hours=24)
    return (datetime.fromisoformat(row['created_at']) + delta).isoformat(timespec='seconds')


@with_notification
def expire_pending(s):
    expired = []
    instant = datetime.fromisoformat(now())
    with s.transaction():
        for row in s.all("SELECT id,command,created_at FROM dashboard_requests WHERE state IN ('queued','waiting')"):
            if datetime.fromisoformat(expires_at(row)) <= instant:
                detail = 'Request expired before dispatch. A new button invocation is required.'
                s.db.execute("UPDATE dashboard_requests SET state='expired',result=?,updated_at=? WHERE id=?", (detail, now(), row['id']))
                event(s, row['id'], 'expired', detail)
                expired.append(row['id'])
    return {'expired': expired}


def contract(s):
    return json.loads((s.root / 'config/chat-commands.json').read_text())


def configuration(s):
    p = s.root / 'config/dashboard.json'
    return json.loads(p.read_text()) if p.exists() else {
        'thread_id': '', 'model': 'host-selected', 'effort': 'host-selected', 'port': 4010}


def parse_command(s, name, params):
    c = contract(s)
    name = str(name).upper().strip()
    name = c.get('aliases', {}).get(name, name)
    if name.startswith('SMP '):
        name = name[4:]
    if name not in c['commands']:
        raise Error('Unknown SMP command.')
    if not isinstance(params, dict) or set(params) - {'minutes', 'week', 'content_id', 'brief', 'preview', 'audience', 'file'}:
        raise Error('Invalid command parameters.')
    spec = c['commands'][name]
    tokens = ['SMP', name]
    clean = {}
    if 'default_minutes' in spec:
        minutes = params.get('minutes', 30)
        if type(minutes) is not int or not 1 <= minutes <= 120:
            raise Error('Choose a duration from 1 to 120 minutes.')
        clean['minutes'] = minutes
        tokens.append(str(minutes))
        if params.get('audience'):
            if name != 'NETWORK' or params['audience'] not in ('followers', 'connections'):
                raise Error('Audience modifier is available for Network only.')
            tokens.append(params['audience'])
            clean['audience'] = params['audience']
        if type(params.get('preview', False)) is not bool:
            raise Error('Preview must be true or false.')
        clean['preview'] = params.get('preview', False)
        if clean['preview']:
            tokens.append('preview')
    elif params.get('preview') or params.get('minutes') or params.get('audience'):
        raise Error('This command does not accept engagement parameters.')
    if name in ('WEEK', 'REVIEW', 'SCHEDULE', 'REWORK') and params.get('week'):
        try:
            week = date.fromisoformat(params['week'])
        except (ValueError, TypeError):
            raise Error('Week must be a Monday date.')
        if week.weekday() != 0:
            raise Error('Week must start on Monday.')
        clean['week'] = week.isoformat()
        tokens.append(clean['week'])
    if params.get('content_id'):
        if name not in ('SCHEDULE', 'ASSET', 'REWORK') or 'week' in clean:
            raise Error('Choose either a week or an individual content item.')
        s.require('content', params['content_id'])
        clean['content_id'] = params['content_id']
        tokens.append(clean['content_id'])
    if name in ('SCHEDULE', 'ASSET', 'REWORK') and not ('week' in clean or 'content_id' in clean):
        raise Error('Select the week or content item first.')
    if name == 'IMPORT':
        value = params.get('file', '')
        if not re.fullmatch(r'data/dashboard-uploads/[a-f0-9]{32}\.(zip|csv|xlsx)', value):
            raise Error('Select and upload your export first.')
        if not s.managed(value).is_file():
            raise Error('Selected upload is unavailable.')
        clean['file'] = value
        tokens.append(value)
    if params.get('brief'):
        if name not in ('REWORK', 'ASSET') or not isinstance(params['brief'], str) or len(params['brief']) > 4000:
            raise Error('A brief of up to 4,000 characters is available for Rework or Asset.')
        clean['brief'] = params['brief'].strip()
    unknown = set(params) - set(clean)
    if any(params[k] not in (None, '', False) for k in unknown):
        raise Error('Unexpected parameters for this command: ' + ', '.join(sorted(unknown)))
    return name, clean, ' '.join(tokens)


def snapshot(s, params):
    if params.get('content_id'):
        items = [s.require('content', params['content_id'])]
    else:
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        from datetime import datetime
        week = date.fromisoformat(params['week'])
        items = []
        for row in s.all('SELECT * FROM content WHERE scheduled_at IS NOT NULL ORDER BY scheduled_at,id'):
            local = datetime.fromisoformat(row['scheduled_at']).astimezone(ZoneInfo(s.settings['timezone'])).date()
            if week <= local < week + timedelta(days=7):
                items.append(row)
    if not items:
        raise Error('No dated content is available for this selection.')
    return [{'id': x['id'], 'version': x['current_version'], 'fingerprint': fingerprint(s, x['id']),
             'title': x['title'], 'scheduled_at': x['scheduled_at'], 'authority': x['publishing_authority']}
            for x in items]


def get(s, request_id):
    row = s.one('SELECT * FROM dashboard_requests WHERE id=?', (request_id,))
    if not row:
        raise Error('Unknown dashboard request.')
    row['params'] = json.loads(row.pop('params_json'))
    row['snapshot'] = json.loads(row.pop('snapshot_json') or 'null')
    row['events'] = s.all('SELECT * FROM dashboard_events WHERE request_id=? ORDER BY sequence', (request_id,))
    row['expires_at'] = expires_at(row)
    return row


def event(s, request_id, kind, detail):
    s.insert('dashboard_events', {'request_id': request_id, 'type': kind, 'detail': detail, 'created_at': now()})


@with_notification
def enqueue(s, command, params, key, presented_snapshot=None):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', key):
        raise Error('A valid idempotency key is required.')
    cfg = configuration(s)
    if cfg.get('desktop_host') not in ('codex', 'claude'):
        raise Error('Configure the desktop host before submitting commands.')
    if not cfg.get('thread_id'):
        raise Error('Bind the existing Desktop task before submitting commands.')
    with s.transaction():
        name, clean, message = parse_command(s, command, params)
        old = s.one('SELECT * FROM dashboard_requests WHERE idempotency_key=?', (key,))
        if old:
            if old['command'] != name or old['params_json'] != dump(clean):
                raise Error('Idempotency key already belongs to another request.')
            return get(s, old['id'])
        selected = snapshot(s, clean) if name == 'SCHEDULE' else None
        if selected is not None and selected != presented_snapshot:
            raise Error('The batch changed or was not presented. Open its current review before scheduling.')
        request_id = ident('run')
        prompt = message + '\n\nDashboard request: ' + request_id + '. Read SOCIAL_MEDIA_PLUS.md and follow the canonical workflow. This button click is the current invocation within its documented scope. Save actual results and receipts. Never treat this request as proof an external action succeeded.'
        if clean.get('brief'):
            prompt += '\nUser revision brief:\n' + clean['brief']
        if selected:
            prompt += '\nExact displayed batch, authorized unchanged only:\n' + dump(selected)
        s.insert('dashboard_requests', dict(id=request_id, idempotency_key=key, command=name,
            params_json=dump(clean), prompt=prompt, state='queued', desktop_host=cfg['desktop_host'], thread_id=cfg['thread_id'],
            model=cfg['model'], effort=cfg['effort'], snapshot_json=dump(selected), created_at=now(), updated_at=now()))
        event(s, request_id, 'queued', 'Button invocation saved. Not yet processed by the selected desktop host.')
        return get(s, request_id)


@with_notification
def transition(s, request_id, state, detail, turn_id=None):
    with s.transaction():
        row = get(s, request_id)
        if state not in TRANSITIONS.get(row['state'], set()):
            raise Error('Invalid request transition: ' + row['state'] + ' → ' + state)
        if not isinstance(detail, str) or not detail.strip():
            raise Error('Observed transition evidence is required.')
        if state == 'dispatching':
            if datetime.fromisoformat(row['expires_at']) <= datetime.fromisoformat(now()):
                raise Error('This request is too old to start. Record expiry and use a new invocation.')
            cfg = configuration(s)
            if row.get('desktop_host') not in ('codex', 'claude'):
                raise Error('This legacy request has no verified desktop host binding. Use a fresh invocation.')
            if (row['desktop_host'], row['thread_id'], row['model'], row['effort']) != (cfg.get('desktop_host'), cfg.get('thread_id'), cfg.get('model'), cfg.get('effort')):
                raise Error('Desktop host, task or model binding changed. Use a fresh invocation for the new binding.')
            other = s.one("SELECT id FROM dashboard_requests WHERE id<>? AND state IN ('dispatching','running','needs_reconciliation')", (request_id,))
            if other:
                raise Error('Another request is active or requires reconciliation.')
            if row['command'] == 'SCHEDULE' and snapshot(s, row['params']) != row['snapshot']:
                raise Error('The displayed batch has changed since authorization.')
        if turn_id and row['turn_id'] and turn_id != row['turn_id']:
            raise Error('Cannot replace the observed Desktop turn identity.')
        if state in ('running', 'completed') and not (turn_id or row['turn_id']):
            raise Error('An observed host turn ID or explicitly labelled local execution ID is required for this state.')
        s.db.execute('UPDATE dashboard_requests SET state=?,result=?,turn_id=COALESCE(?,turn_id),updated_at=? WHERE id=?',
                     (state, detail, turn_id, now(), request_id))
        event(s, request_id, state, detail)
        return get(s, request_id)
