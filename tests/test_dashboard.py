import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from socialmediaplus.store import Store, Error
from socialmediaplus.dashboard import records
from socialmediaplus.dashboard.server import listing
from socialmediaplus import workflow, network


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s = Store(self.root, create=True)
        self.s.settings["profile_url"] = "https://www.linkedin.com/in/example-member/"
        (self.root/'config').mkdir()
        source = Path(__file__).resolve().parents[1]
        for name in ('chat-commands.json','dashboard.json'):
            shutil.copy(source/('config' if name == 'chat-commands.json' else 'templates/config')/name, self.root/'config'/name)
        config_path = self.root/'config/dashboard.json'
        cfg = json.loads(config_path.read_text())
        cfg['thread_id'] = 'fixture-task'
        cfg['desktop_host'] = 'codex'
        config_path.write_text(json.dumps(cfg))

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def test_duplicate_click_and_changed_payload(self):
        r = records.enqueue(self.s, 'ENGAGE', {'minutes':30}, 'a'*16)
        self.assertEqual(r['id'], records.enqueue(self.s, 'ENGAGE', {'minutes':30}, 'a'*16)['id'])
        with self.assertRaises(Error):
            records.enqueue(self.s, 'REPLIES', {'minutes':30}, 'a'*16)
        self.assertEqual(self.s.one('SELECT COUNT(*) n FROM dashboard_requests')['n'], 1)

    def test_validation_and_plus_alias_scope(self):
        for name,params in [('UNKNOWN',{}),('ENGAGE',{'minutes':True}),('ENGAGE',{'minutes':121}),('ENGAGE',{'audience':'followers'}),('START',{'brief':'send now'}),('WEEK',{'week':'2026-09-15'}),('IMPORT',{'file':'/etc/passwd'})]:
            with self.assertRaises(Error):
                records.parse_command(self.s,name,params)
        name,params,prompt=records.parse_command(self.s,'SPM RECRUITER+',{'minutes':30,'preview':True})
        self.assertEqual(name,'RECRUITER+')
        self.assertEqual(prompt,'SMP RECRUITER+ 30 preview')

    def test_all_master_commands_have_a_valid_structured_invocation(self):
        p=self.root/'draft.md';p.write_text('A prepared draft for form validation.')
        item=workflow.content_add(self.s,p,'Form validation draft')
        upload='data/dashboard-uploads/'+'a'*32+'.csv'
        self.s.write(upload,'Date,Text\n')
        for command,spec in records.contract(self.s)['commands'].items():
            with self.subTest(command=command):
                params={}
                if 'default_minutes' in spec:
                    params={'minutes':30,'preview':False}
                elif command in ('ASSET','REWORK','SCHEDULE'):
                    params={'content_id':item['id']}
                elif command=='IMPORT':
                    params={'file':upload}
                elif command in ('WEEK','REVIEW'):
                    params={'week':'2026-09-14'}
                name,clean,prompt=records.parse_command(self.s,command,params)
                self.assertEqual(name,command)
                self.assertTrue(prompt.startswith('SMP '+command))
                self.assertEqual(clean,params)

    def test_ambiguous_attempt_blocks_next_dispatch(self):
        a=records.enqueue(self.s,'STATUS',{},'a'*16)
        b=records.enqueue(self.s,'STATUS',{},'b'*16)
        records.transition(self.s,a['id'],'dispatching','Submitting')
        records.transition(self.s,a['id'],'needs_reconciliation','Connection lost')
        with self.assertRaises(Error):
            records.transition(self.s,b['id'],'dispatching','Submitting')
        with self.assertRaises(Error):
            records.transition(self.s,a['id'],'queued','Retry blindly')
        records.transition(self.s,a['id'],'failed','Verified no turn was created')
        records.transition(self.s,b['id'],'dispatching','Now permitted')

    def test_cancel_before_dispatch_and_persistence(self):
        row=records.enqueue(self.s,'STATUS',{},'c'*16)
        self.s.close();self.s=Store(self.root)
        self.assertEqual(records.get(self.s,row['id'])['state'],'queued')
        records.transition(self.s,row['id'],'cancelled','User cancelled')
        with self.assertRaises(Error):
            records.transition(self.s,row['id'],'dispatching','Must not run')

    def test_expiry_does_not_resubmit_or_expire_dispatched_attempts(self):
        pending=records.enqueue(self.s,'ENGAGE',{'minutes':30},'pending-expiry-01')
        running=records.enqueue(self.s,'STATUS',{},'running-expiry-01')
        records.transition(self.s,running['id'],'dispatching','Submission attempted')
        with self.s.transaction():
            self.s.db.execute("UPDATE dashboard_requests SET created_at='2020-01-01T00:00:00+00:00'")
        with self.assertRaises(Error):
            records.transition(self.s,pending['id'],'dispatching','Too old')
        self.assertEqual(records.expire_pending(self.s)['expired'],[pending['id']])
        self.assertEqual(records.get(self.s,running['id'])['state'],'dispatching')
        self.assertEqual(records.expire_pending(self.s)['expired'],[])

    def test_turn_identity_and_binding_cannot_be_silently_changed(self):
        row=records.enqueue(self.s,'STATUS',{},'identity-test-01')
        cfg=json.loads((self.root/'config/dashboard.json').read_text())
        cfg['model']='a-different-model'
        (self.root/'config/dashboard.json').write_text(json.dumps(cfg))
        with self.assertRaises(Error):
            records.transition(self.s,row['id'],'dispatching','Wrong model')
        cfg['model']=row['model']
        (self.root/'config/dashboard.json').write_text(json.dumps(cfg))
        records.transition(self.s,row['id'],'dispatching','Submitting')
        with self.assertRaises(Error):
            records.transition(self.s,row['id'],'running','No observed turn')
        records.transition(self.s,row['id'],'running','Observed exact turn','turn-fixture-1')
        with self.assertRaises(Error):
            records.transition(self.s,row['id'],'completed','Different turn','turn-fixture-2')
        records.transition(self.s,row['id'],'completed','Observed completion','turn-fixture-1')

    def test_schedule_requires_exact_displayed_snapshot(self):
        p=self.root/'draft.md';p.write_text('A concrete test draft.')
        row=workflow.content_add(self.s,p,'Test draft')
        content_id=row['id']
        params={'content_id':content_id}
        snap=records.snapshot(self.s,params)
        with self.assertRaises(Error):
            records.enqueue(self.s,'SCHEDULE',params,'s'*16)
        r=records.enqueue(self.s,'SCHEDULE',params,'s'*16,snap)
        with self.s.transaction():
            self.s.db.execute("UPDATE content SET scheduled_at=? WHERE id=?",((datetime.now(timezone.utc)+timedelta(days=3)).isoformat(),content_id))
        with self.assertRaises(Error):
            records.transition(self.s,r['id'],'dispatching','Changed batch')

    def test_search_is_literal_and_bounded(self):
        self.assertEqual(listing(self.s,'network',{'q':["%' OR 1=1 --"]})['total'],0)
        self.assertEqual(listing(self.s,'runs',{'page':['-99']})['page'],1)

    def test_follower_only_filter_preserves_overlapping_memberships(self):
        first=network.add(self.s,'First','https://www.linkedin.com/in/first-fixture/','test',relationship_type='follower')
        network.add(self.s,'Second','https://www.linkedin.com/in/second-fixture/','test',relationship_type='follower')
        network.add(self.s,'First','https://www.linkedin.com/in/first-fixture/','test',relationship_type='connection')
        all_followers=listing(self.s,'network',{'membership':['follower']})
        follower_only=listing(self.s,'network',{'membership':['follower_only']})
        self.assertEqual(all_followers['total'],2)
        self.assertEqual(follower_only['total'],1)
        self.assertEqual(follower_only['rows'][0]['name'],'Second')

    def test_migration_preserves_content(self):
        p=self.root/'draft.md';p.write_text('Keep this text.')
        item=workflow.content_add(self.s,p,'Preserved')
        with self.s.transaction():
            self.s.db.execute('DROP TABLE dashboard_events')
            self.s.db.execute('DROP TABLE dashboard_requests')
            self.s.db.execute('UPDATE schema_version SET version=5')
        self.s.close();self.s=Store(self.root)
        self.assertEqual(self.s.require('content',item['id'])['title'],'Preserved')
        self.assertEqual(self.s.one('SELECT version FROM schema_version')['version'],7)


if __name__=='__main__': unittest.main()
