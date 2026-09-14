"""Public runtime integration tests. Every mutable operation uses a temporary root."""
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'src'))
from socialmediaplus.store import Store, Error
from socialmediaplus.dashboard import records, settings
from socialmediaplus.dashboard.server import Server
from socialmediaplus.mcp import Protocol, execute, serve
from socialmediaplus import engagement

spec = importlib.util.spec_from_file_location('smp_install', PACKAGE / 'scripts/smp-install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='smp-runtime-test-')
        self.root = Path(self.temp.name).resolve()
        self.result = installer.install(self.root, 'codex', 'test-local-session', 4029)

    def tearDown(self):
        self.temp.cleanup()

    def test_install_portable_private_and_idempotent(self):
        self.assertTrue(self.result['installed'])
        self.assertEqual(self.result['storage'], 'sqlite')
        self.assertEqual(self.result['listener']['status'], 'not_installed')
        self.assertFalse(self.result['listener']['verified'])
        self.assertTrue((self.root / 'profile/profile.json').is_file())
        self.assertTrue((self.root / 'ui/dist/index.html').is_file())
        p = self.root / 'profile/context.md'
        p.write_text('My user-authored context survives reinstall.')
        cfg_path = self.root / 'config/dashboard.json'
        cfg = json.loads(cfg_path.read_text())
        cfg['listener'] = {'status': 'installed', 'verified': False, 'automation_id': 'local-test-receipt'}
        cfg_path.write_text(json.dumps(cfg))
        installer.install(self.root, 'codex')
        self.assertIn('survives', p.read_text())
        self.assertEqual(json.loads(cfg_path.read_text())['listener']['automation_id'], 'local-test-receipt')
        installer.install(self.root, 'claude', 'different-session')
        cfg = json.loads(cfg_path.read_text())
        self.assertEqual(cfg['listener']['status'], 'binding_changed_needs_reconciliation')
        self.assertEqual(cfg['listener']['automation_id'], 'local-test-receipt')
        mcp = json.loads((self.root / 'runtime/install/claude-mcp.json').read_text())
        self.assertEqual(mcp['mcpServers']['social-media-plus']['args'][-1], str(self.root))
        if os.name == 'posix':
            self.assertEqual((self.root / 'data/socialmediaplus.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_new_root_copy_uses_public_allowlist(self):
        (self.root / '.claude').mkdir(exist_ok=True)
        (self.root / '.claude/settings.local.json').write_text('{"private_fixture": true}')
        (self.root / 'third_party/private-cache').mkdir(parents=True)
        (self.root / 'third_party/private-cache/value.txt').write_text('private fixture')
        config = self.root / 'config/settings.json'
        values = json.loads(config.read_text())
        values['owner'] = 'Private source fixture'
        config.write_text(json.dumps(values))
        original = installer.PACKAGE
        try:
            installer.PACKAGE = self.root
            with tempfile.TemporaryDirectory(prefix='smp-second-root-') as directory:
                target = Path(directory).resolve()
                installer.install(target, 'claude')
                self.assertFalse((target / '.claude/settings.local.json').exists())
                self.assertFalse((target / 'third_party').exists())
                self.assertNotEqual(json.loads((target / 'config/settings.json').read_text()).get('owner'), 'Private source fixture')
                self.assertTrue((target / 'THIRD_PARTY_NOTICES.md').is_file())
                self.assertTrue((target / 'ui/src/main.tsx').is_file())
                self.assertTrue((target / 'tests/test_release_runtime.py').is_file())
        finally:
            installer.PACKAGE = original

    def test_replicated_root_runs_its_own_cli_and_mcp(self):
        command = [sys.executable, str(self.root / 'scripts/smp'), '--root', str(self.root), 'status']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        stream = '\n'.join(json.dumps(message) for message in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'smp_status'}}]) + '\n'
        result = subprocess.run([sys.executable, str(self.root/'scripts/smp-mcp.py'), '--root', str(self.root)], input=stream, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertFalse(responses[-1]['result']['isError'])
        self.assertEqual(json.loads(responses[-1]['result']['content'][0]['text'])['storage'], 'sqlite')

    def test_credentials_never_return_values_and_blank_keeps_secret(self):
        values = {'publish': {'client_id': 'example-client', 'client_secret': 'synthetic-only-secret',
                              'redirect_uri': 'http://localhost:4900/callback'}}
        result = settings.save(self.root, values)
        self.assertEqual(result['apps']['publish']['status'], 'configured')
        self.assertFalse(result['authenticated'])
        self.assertNotIn('synthetic-only-secret', json.dumps(result))
        self.assertNotIn('example-client', json.dumps(result))
        self.assertIn('synthetic-only-secret', (self.root / '.env.local').read_text())
        self.assertEqual(settings.save(self.root, {'publish': {'client_secret': ''}})['apps']['publish']['status'], 'configured')
        self.assertEqual(settings.save(self.root, {'publish': {'clear': True}})['apps']['publish']['status'], 'not_configured')
        if os.name == 'posix':
            self.assertEqual((self.root / '.env.local').stat().st_mode & 0o777, 0o600)

    def test_credential_invalid_values_and_symlink_cannot_write(self):
        for body in ({'publish': {'client_secret': 'injected\nOTHER=value'}},
                     {'publish': {'redirect_uri': 'javascript:alert(1)'}},
                     {'publish': {'redirect_uri': 'http://remote.invalid/callback'}},
                     {'publish': {'redirect_uri': 'https://user:password@example.com/callback'}},
                     {'publish': {'clear': 'true'}}, {'unknown': {}}):
            with self.subTest(body=body), self.assertRaises(Error):
                settings.save(self.root, body)
        target = self.root / 'existing-file'
        target.write_text('preserve')
        (self.root / '.env.local').symlink_to(target)
        with self.assertRaises(Error):
            settings.save(self.root, {'publish': {'client_id': 'abc'}})
        self.assertEqual(target.read_text(), 'preserve')

    def test_queue_notification_claim_and_uncertainty_block(self):
        s = Store(self.root)
        try:
            first = records.enqueue(s, 'STATUS', {}, 'runtime-first-status')
            second = records.enqueue(s, 'STATUS', {}, 'runtime-next-status')
            mirror = json.loads((self.root / 'data/dashboard-queue.json').read_text())
            self.assertEqual(len(mirror['pending']), 2)
            self.assertNotIn('prompt', json.dumps(mirror))
            self.assertEqual(first['id'], records.enqueue(s, 'STATUS', {}, 'runtime-first-status')['id'])
            records.transition(s, first['id'], 'dispatching', 'Claimed in local test')
            with self.assertRaises(Error):
                records.transition(s, second['id'], 'dispatching', 'Cannot overlap')
            records.transition(s, first['id'], 'needs_reconciliation', 'Dispatch result unavailable')
            with self.assertRaises(Error):
                records.transition(s, second['id'], 'dispatching', 'Still cannot overlap')
            records.transition(s, first['id'], 'failed', 'Observed no external execution')
            records.transition(s, second['id'], 'dispatching', 'Claimed now')
            records.transition(s, second['id'], 'running', 'Local execution correlation only', 'local:test-execution')
            records.transition(s, second['id'], 'completed', 'Local STATUS completed', 'local:test-execution')
            self.assertEqual(json.loads((self.root / 'data/dashboard-queue.json').read_text())['pending'], [])
        finally:
            s.close()

    def test_host_switch_with_same_session_identifier_blocks_old_request(self):
        installer.install(self.root, 'codex', 'manual-local')
        s = Store(self.root)
        try:
            old = records.enqueue(s, 'STATUS', {}, 'host-switch-same-session')
            self.assertEqual(old['desktop_host'], 'codex')
            installer.install(self.root, 'claude', 'manual-local')
            with self.assertRaisesRegex(Error, 'Desktop host'):
                records.transition(s, old['id'], 'dispatching', 'Must not migrate authority across hosts')
            # A fresh button invocation records the actual new product binding.
            new = records.enqueue(s, 'STATUS', {}, 'fresh-host-same-session')
            self.assertEqual(new['desktop_host'], 'claude')
            records.transition(s, new['id'], 'dispatching', 'Fresh Claude invocation')
        finally:
            s.close()

    def test_schema_six_migration_preserves_unknown_host_and_blocks_dispatch(self):
        s = Store(self.root)
        old = records.enqueue(s, 'STATUS', {}, 'schema-six-legacy-request')
        try:
            with s.transaction():
                s.db.execute('ALTER TABLE dashboard_requests DROP COLUMN desktop_host')
                s.db.execute('UPDATE schema_version SET version=6')
        finally:
            s.close()
        upgraded = Store(self.root)
        try:
            self.assertEqual(upgraded.one('SELECT version FROM schema_version')['version'], 7)
            row = records.get(upgraded, old['id'])
            self.assertIsNone(row['desktop_host'])
            self.assertEqual(row['state'], 'queued')
            self.assertTrue(row['events'])
            with self.assertRaisesRegex(Error, 'legacy request'):
                records.transition(upgraded, old['id'], 'dispatching', 'Unknown historical host cannot be inferred')
            records.transition(upgraded, old['id'], 'cancelled', 'User can cancel legacy pending work')
        finally:
            upgraded.close()

    def test_mcp_handshake_bounded_tools_and_no_arbitrary_execution(self):
        protocol = Protocol(self.root)
        def call(method, params=None):
            return protocol.handle({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})
        self.assertIn('error', call('tools/list'))
        self.assertEqual(call('initialize', {'protocolVersion': '2025-11-25'})['result']['protocolVersion'], '2025-11-25')
        protocol.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual(len(call('tools/list')['result']['tools']), 5)
        self.assertFalse(call('tools/call', {'name': 'smp_status'})['result']['isError'])
        self.assertTrue(call('tools/call', {'name': 'smp_queue_list', 'arguments': {'limit': 51}})['result']['isError'])
        self.assertTrue(call('tools/call', {'name': 'shell', 'arguments': {'cmd': 'echo nope'}})['result']['isError'])
        self.assertTrue(call('tools/call', {'name': 'smp_status', 'arguments': {'path': '.env.local'}})['result']['isError'])
        stream = io.StringIO()
        serve(self.root, io.BytesIO(b'bad-json\n'+json.dumps({'jsonrpc':'2.0','id':2,'method':'ping'}).encode()+b'\n'), stream)
        messages = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(messages[0]['error']['code'], -32700)
        self.assertEqual(messages[1]['result'], {})

    def test_no_personal_defaults_or_outreach_enabled(self):
        s = Store(self.root)
        try:
            self.assertEqual(s.settings['profile_url'], '')
            self.assertEqual(s.settings['timezone'], 'UTC')
            with self.assertRaisesRegex(Error, 'Enable outreach'):
                engagement.active_session(s, 'not-a-session', 'dm')
        finally:
            s.close()

    def test_check_does_not_create_database_or_start_process(self):
        empty = self.root / 'empty-workspace'
        result = subprocess.run([sys.executable, str(PACKAGE/'scripts/smp-start.py'), '--root', str(empty), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(empty.exists())


class RuntimeHTTPTests(unittest.TestCase):
    # HTTP tests bind ephemeral ports and never touch any existing workspace service.
    def setUp(self):
        RuntimeTests.setUp(self)
        try:
            self.server = Server(self.root, 0)
        except PermissionError:
            self.temp.cleanup()
            self.skipTest('Loopback binding is unavailable in this execution sandbox.')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        RuntimeTests.tearDown(self)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request(method, path, json.dumps(body) if body is not None else None, headers or {})
        result = conn.getresponse()
        status, data = result.status, result.read()
        conn.close()
        return status, data

    def test_http_settings_require_csrf_and_do_not_echo(self):
        body = {'identity': {'client_id': 'fixture-client', 'client_secret': 'fixture-secret', 'redirect_uri': 'https://example.com/callback'}}
        self.assertEqual(self.request('POST','/api/settings/linkedin',body)[0],400)
        headers = {'X-SMP-Token': self.server.token, 'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/settings/linkedin',body,{**headers,'Origin':'https://attacker.invalid'})[0],400)
        code, raw = self.request('POST','/api/settings/linkedin',body,headers)
        self.assertEqual(code,200)
        self.assertNotIn(b'fixture-secret', raw)
        code, raw = self.request('GET','/api/settings/linkedin')
        self.assertEqual(code,200)
        self.assertNotIn(b'fixture-client',raw)
        self.assertEqual(json.loads(raw)['apps']['identity']['status'],'configured')
        self.assertEqual(self.request('GET','/.env.local')[0],404)
        self.assertEqual(self.request('GET','/../.env.local')[0],404)
        self.assertEqual(self.request('GET','/api/overview')[0],200)
        self.assertIn(b'Social Media Plus',self.request('GET','/')[1])


if __name__ == '__main__':
    unittest.main()
