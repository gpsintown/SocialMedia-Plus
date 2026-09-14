import http.client
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from socialmediaplus.store import Store
from socialmediaplus.dashboard.server import Server


class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        Store(self.root, create=True).close()
        (self.root/'config').mkdir()
        source = Path(__file__).resolve().parents[1]
        for name in ('chat-commands.json','dashboard.json'):
            shutil.copy(source/('config' if name == 'chat-commands.json' else 'templates/config')/name, self.root/'config'/name)
        config_path = self.root/'config/dashboard.json'
        cfg = json.loads(config_path.read_text())
        cfg['thread_id'] = 'fixture-task'
        cfg['desktop_host'] = 'codex'
        config_path.write_text(json.dumps(cfg))
        (self.root/'ui/dist').mkdir(parents=True)
        (self.root/'ui/dist/index.html').write_text('<h1>Fixture dashboard</h1>')
        (self.root/'private.txt').write_text('must not be served')
        try:
            self.server = Server(self.root, 0)
        except PermissionError:
            self.temp.cleanup()
            self.skipTest('Loopback binding requires the approved HTTP test run outside the shell sandbox.')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        payload=json.dumps(body) if body is not None else None
        conn.request(method,path,body=payload,headers=headers or {})
        res=conn.getresponse(); raw=res.read(); status=res.status; conn.close()
        return status, raw

    def test_host_and_origin_boundaries(self):
        self.assertEqual(self.request('GET','/api/session',headers={'Host':'attacker.example'})[0],400)
        self.assertEqual(self.request('GET','/api/session',headers={'Origin':'https://attacker.example'})[0],400)
        self.assertEqual(self.request('GET','/api/session',headers={'Sec-Fetch-Site':'cross-site'})[0],400)
        self.assertEqual(self.request('GET','/api/session')[0],200)

    def test_mutation_needs_session_and_cancels_without_dispatch(self):
        body={'command':'STATUS','params':{},'idempotency_key':'http-test-status-01'}
        self.assertEqual(self.request('POST','/api/requests',body)[0],400)
        headers={'X-SMP-Token':self.server.token}
        status,raw=self.request('POST','/api/requests',body,headers)
        self.assertEqual(status,201)
        row=json.loads(raw)
        self.assertEqual(row['state'],'queued')
        duplicate=json.loads(self.request('POST','/api/requests',body,headers)[1])
        self.assertEqual(row['id'],duplicate['id'])
        status,raw=self.request('POST','/api/cancel/'+row['id'],{},headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['state'],'cancelled')

    def test_private_files_and_symlinks_not_served(self):
        self.assertEqual(self.request('GET','/../private.txt')[0],404)
        self.assertEqual(self.request('GET','/config/dashboard.json')[0],404)
        (self.root/'ui/dist/leak.txt').symlink_to(self.root/'private.txt')
        self.assertEqual(self.request('GET','/leak.txt')[0],404)
        self.assertIn(b'Fixture dashboard',self.request('GET','/')[1])

    def test_queries_are_bounded_and_unknown_routes_rejected(self):
        self.assertEqual(self.request('GET','/api/list/network?q=%25%27')[0],200)
        self.assertEqual(self.request('GET','/api/list/secrets')[0],404)
        self.assertEqual(self.request('GET','/api/list/network?page=not-an-integer')[0],400)
        self.assertEqual(self.request('POST','/api/run-shell',{}, {'X-SMP-Token':self.server.token})[0],400)

    def test_insights_do_not_invent_missing_measurements(self):
        status,raw=self.request('GET','/api/insights')
        self.assertEqual(status,200)
        result=json.loads(raw)
        self.assertEqual(result['metrics'],[])
        self.assertIn('not measurements of received engagement',result['note'])


if __name__=='__main__': unittest.main()
