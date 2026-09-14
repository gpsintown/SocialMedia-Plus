"""Local credential storage. Responses contain presence flags, never values."""
import json
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

from ..store import Error

APPS = ('publish', 'identity')
FIELDS = ('client_id', 'client_secret', 'redirect_uri')
KEYS = {f'LINKEDIN_{app.upper()}_{field.upper()}' for app in APPS for field in FIELDS}
LOCK = threading.Lock()


def private_write(path, text):
    """Atomic owner-only replacement. Refuse a symlink destination."""
    path = Path(path)
    if path.is_symlink():
        raise Error('Refusing to replace a symbolic link with private configuration.')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read(root):
    path = Path(root) / '.env.local'
    if path.is_symlink():
        raise Error('The local environment file must not be a symbolic link.')
    if not path.exists():
        return {}, []
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
        raise Error('The local environment file must be a regular file smaller than 64 KB.')
    if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise Error('Set .env.local permissions to owner-only (chmod 600 .env.local).')
    result, unmanaged = {}, []
    for line in path.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() in KEYS:
            value = value.strip()
            try:
                result[key.strip()] = json.loads(value) if value.startswith('"') else value.strip("'")
            except ValueError:
                raise Error('A LinkedIn environment value has invalid quoting.') from None
            if not isinstance(result[key.strip()], str):
                raise Error('LinkedIn environment values must be strings.')
        elif line.strip() != '# LinkedIn settings saved by Social Media Plus. Keep this file private.':
            unmanaged.append(line)
    return result, unmanaged


def status(root):
    values, _ = _read(root)
    apps = {}
    for app in APPS:
        present = {field: bool(values.get(f'LINKEDIN_{app.upper()}_{field.upper()}')) for field in FIELDS}
        state = 'configured' if all(present.values()) else 'partial' if any(present.values()) else 'not_configured'
        apps[app] = {'status': state, 'fields_present': present, 'authenticated': False}
    return {'apps': apps, 'storage': '.env.local', 'authenticated': False,
            'oauth_supported': False, 'note': 'Saved credentials are not an authenticated connection. OAuth and API publishing are not implemented in this release; use a verified browser workflow.'}


def save(root, body):
    if not isinstance(body, dict) or set(body) - set(APPS):
        raise Error('Choose the publishing or identity LinkedIn app.')
    # Validate the complete payload before touching existing credentials.
    updates = {}
    for app, fields in body.items():
        if not isinstance(fields, dict) or set(fields) - set(FIELDS) - {'clear'}:
            raise Error('Unsupported LinkedIn settings field.')
        if type(fields.get('clear', False)) is not bool:
            raise Error('Clear must be true or false.')
        if fields.get('clear'):
            if any(fields.get(field) for field in FIELDS):
                raise Error('Clear the app or save new values in separate requests.')
            updates.update({f'LINKEDIN_{app.upper()}_{field.upper()}': '' for field in FIELDS})
            continue
        for field, value in fields.items():
            if field == 'clear':
                continue
            if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise Error('Credential values must be single-line text up to 2,048 characters.')
            value = value.strip()
            if not value:
                continue  # Empty form fields retain existing values.
            if field == 'client_id' and not re.fullmatch(r'[A-Za-z0-9_-]+', value):
                raise Error('Client ID must contain only letters, digits, underscores or hyphens.')
            if field == 'redirect_uri':
                try:
                    parsed = urlsplit(value)
                    valid = bool(parsed.hostname and not parsed.username and not parsed.password and not parsed.fragment
                                 and (parsed.scheme == 'https' or parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')))
                    parsed.port
                except ValueError:
                    valid = False
                if not valid:
                    raise Error('Use an HTTPS redirect URI or an HTTP localhost callback without credentials or a fragment.')
            updates[f'LINKEDIN_{app.upper()}_{field.upper()}'] = value
    with LOCK:
        values, unmanaged = _read(root)
        values.update(updates)
        text = '\n'.join(unmanaged).strip()
        text = (text + '\n\n' if text else '') + '# LinkedIn settings saved by Social Media Plus. Keep this file private.\n'
        text += ''.join(key + '=' + json.dumps(values.get(key, ''), ensure_ascii=True) + '\n' for key in sorted(KEYS))
        if len(text.encode()) > 65536:
            raise Error('The local environment file would exceed 64 KB.')
        private_write(Path(root) / '.env.local', text)
        return status(root)
