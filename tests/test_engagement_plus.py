import json
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from socialmediaplus import engagement, network, reports, workflow
from socialmediaplus.store import Error, Store, digest, now


class PlusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s = Store(self.root, create=True)
        self.resume = self.root / "master-resume.pdf"
        self.resume.write_bytes(b"%PDF-1.7\nfixture reviewed resume\n%%EOF\n")
        (self.root / "config").mkdir()
        (self.root / "config/engagement-plus.json").write_text(json.dumps({"outreach": {"enabled": True, "countries": ["Germany"]}, "inmail": {"enabled": True}, "resume": {
            "path": "master-resume.pdf", "sha256": digest(self.resume.read_bytes())}}))
        self.session = engagement.session_start(self.s, "recruiter_plus", 30, "Actual test invocation")['id']
        self.sequence = 0

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def job(self, company=None, **updates):
        self.sequence += 1
        person = network.add(self.s, "Hiring contact " + str(self.sequence),
                             "https://www.linkedin.com/in/hiring-" + str(self.sequence),
                             "Visible listed hiring contact", relationship_type="company_contact")
        data = dict(job_url="https://www.linkedin.com/jobs/view/" + str(1000 + self.sequence),
                    title="Analytics engineer", company=company or "Employer " + str(self.sequence), country="Germany",
                    observed_at=now(), posting_evidence="Visible 2 hours ago", posted_age_hours_upper_bound=3,
                    applicant_evidence="Visible 8 applicants", applicants_count=8,
                    applicant_indicator_type="exact_applicants", close_match=True,
                    match_evidence="Observed role requirements match referenced resume claims; eligibility not asserted",
                    contact_id=person['id'], contact_evidence="Meet the hiring team links this profile")
        data.update(updates)
        path = self.root / ("job-" + str(self.sequence) + ".json")
        path.write_text(json.dumps(data))
        return engagement.opportunity_add(self.s, path)['opportunity'], person

    def prepare(self, kind="inmail", job=None, person=None, session=None, store=None, **updates):
        if job is None:
            job, person = self.job()
        options = dict(target=person['profile_url'], response="A specific fit and one relevant question.",
                       context="Observed job and actual current invocation, reviewed resume claims.",
                       relationship_id=person['id'], session_id=session or self.session, opportunity_id=job['id'],
                       attachment=self.resume, details={"direct_dm_available": kind == "dm", "channel_evidence": "Visible compose route",
                       "selection_evidence": "Listed contact for this matching opening", "attachment_supported": True,
                       "subject": "Question about the analytics engineering opening"})
        options.update(updates)
        return workflow.prepare(store or self.s, kind, "native_linkedin", **options)['action']

    def observed(self, action):
        return dict(target_url=action['target_url'], response=action['response'],
                    subject=json.loads(action['details']['details_json']).get('subject'),
                    attachment_sha256=action['details']['attachment_sha256'])

    def test_preview_expired_and_wrong_mode_never_authorize_outreach(self):
        job, person = self.job()
        for session in (engagement.session_start(self.s, "recruiter_plus", 30, "Preview", True)['id'],
                        engagement.session_start(self.s, "engage_plus", 30, "Engagement only")['id']):
            with self.assertRaises(Error):
                self.prepare("dm", job, person, session)
        action = self.prepare("dm", job, person)
        future = (datetime.now(timezone.utc) + timedelta(minutes=31)).isoformat(timespec='seconds')
        with patch('socialmediaplus.engagement.now', return_value=future):
            with self.assertRaisesRegex(Error, "expired"):
                engagement.check_action(self.s, action['id'])
        self.assertEqual(self.s.one('SELECT COUNT(*) AS n FROM actions')['n'], 1)

    def test_strict_job_indicators_and_24_hour_expiry_are_not_inferred(self):
        for update in ({'applicants_count': None}, {'applicants_count': 10},
                       {'applicant_indicator_type': 'apply_clicks'}, {'applicant_indicator_type': 'unknown'},
                       {'close_match': False}, {'posted_age_hours_upper_bound': 25}):
            job, person = self.job(**update)
            self.assertFalse(job['eligibility']['eligible'])
            with self.assertRaisesRegex(Error, 'not eligible'):
                self.prepare('dm', job, person)
        job, person = self.job(applicants_count=None, applicants_upper_bound=9,
                               applicant_indicator_type='verified_under_10_filter', posted_age_hours_upper_bound=23.9)
        self.assertTrue(job['eligibility']['eligible'])
        action = self.prepare('dm', job, person)
        later = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec='seconds')
        with patch('socialmediaplus.engagement.now', return_value=later):
            with self.assertRaisesRegex(Error, '24-hours'):
                engagement.check_action(self.s, action['id'])

    def test_unknown_credit_free_dm_first_subject_and_attachment_guard(self):
        job, person = self.job()
        with self.assertRaisesRegex(Error, 'spending blocked'):
            self.prepare('inmail', job, person)
        self.assertEqual(self.s.one('SELECT COUNT(*) AS n FROM actions')['n'], 0)
        engagement.observe_balance(self.s, 10, 'Visible premium credit count')
        base = dict(direct_dm_available=False, channel_evidence='UI', selection_evidence='Fit', attachment_supported=True, subject='Role')
        for updates, message in (({'direct_dm_available': True}, 'free DM'), ({'subject': ''}, 'subject'),
                                 ({'attachment_supported': False}, 'visibly supports')):
            with self.assertRaisesRegex(Error, message):
                self.prepare('inmail', job, person, details={**base, **updates})
        wrong = self.root / 'other.pdf'
        wrong.write_bytes(b'%PDF-1.7\nwrong version')
        with self.assertRaisesRegex(Error, 'configured reviewed master'):
            self.prepare('inmail', job, person, attachment=wrong)
        other_job, other_person = self.job()
        with self.assertRaisesRegex(Error, 'linked to the observed'):
            self.prepare('dm', job, other_person)

    def test_uncertain_credit_holds_duplicate_block_and_reconciled_retry(self):
        engagement.observe_balance(self.s, 2, 'Visible two credits')
        job, person = self.job()
        action = self.prepare('inmail', job, person)
        self.assertEqual(engagement.inmail_status(self.s)['additional_credits_allowed'], 0)
        workflow.receipt(self.s, action['id'], 'uncertain', 'Composer timed out')
        with self.assertRaisesRegex(Error, 'Existing or recent outreach'):
            self.prepare('dm', job, person)
        with self.assertRaisesRegex(Error, 'uncertain outcomes'):
            workflow.retry(self.s, action['id'], 'Cannot assume absent')
        workflow.receipt(self.s, action['id'], 'failed', 'Verified no sent message and no credit use', reconcile=True)
        self.assertEqual(engagement.inmail_status(self.s)['additional_credits_allowed'], 1)
        retried = workflow.retry(self.s, action['id'], 'Absent confirmed in sent messages')
        self.assertEqual(retried['attempt'], 2)
        self.assertEqual(retried['inmail_reservation']['state'], 'reserved')
        self.assertEqual(engagement.inmail_status(self.s)['additional_credits_allowed'], 0)

    def test_confirmed_outreach_requires_matching_body_subject_pdf_and_shares_history(self):
        engagement.observe_balance(self.s, 10, 'Visible 10')
        action = self.prepare('inmail')
        for observed in (None, {**self.observed(action), 'response': 'Different'},
                         {**self.observed(action), 'subject': 'Different'},
                         {**self.observed(action), 'attachment_sha256': '0'*64}):
            with self.assertRaises(Error):
                workflow.receipt(self.s, action['id'], 'confirmed', 'Observed sent', remote_id='thread/1', observed_details=observed)
        result = workflow.receipt(self.s, action['id'], 'confirmed', 'Exact sent message and attachment visible',
                                  remote_id='thread/1', observed_details=self.observed(action))
        self.assertEqual(result['inmail_reservation']['state'], 'spent')
        self.assertIsNotNone(result['receipts'][0]['observed_details'])
        history = self.s.all('SELECT * FROM interactions')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['relationship_id'], action['relationship_id'])
        self.assertEqual(network.due(self.s, cooldown_hours=24)['queue'], [])
        self.assertTrue(reports.doctor(self.s)['ok'])

    def test_concurrent_preparations_cannot_overspend_session(self):
        engagement.observe_balance(self.s, 20, 'Visible 20')
        self.prepare('inmail')
        jobs = [self.job(), self.job()]
        def run(pair):
            separate = Store(self.root)
            try:
                return self.prepare('inmail', *pair, store=separate)['id']
            except Error as error:
                return str(error)
            finally:
                separate.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, jobs))
        self.assertEqual(sum(value.startswith('action_') for value in results), 1, results)
        self.assertEqual(engagement.inmail_status(self.s, self.session)['session_used_or_reserved'], 2)
        self.assertEqual(self.s.one('SELECT COUNT(*) AS n FROM actions')['n'], 2)

    def test_rolling_week_cap_and_company_contact_deduplication(self):
        engagement.observe_balance(self.s, 30, 'Visible 30')
        for index in range(5):
            if index % 2 == 0:
                self.session = engagement.session_start(self.s, 'recruiter_plus', 30, 'Another authorized session')['id']
            self.prepare('inmail')
        with self.assertRaisesRegex(Error, 'spending blocked'):
            self.prepare('inmail')
        self.assertEqual(engagement.inmail_status(self.s)['rolling_7_day_used_or_reserved'], 5)
        first_job, first_person = self.job(company='Same company')
        action = self.prepare('dm', first_job, first_person)
        second_job, second_person = self.job(company='Same company')
        with self.assertRaisesRegex(Error, 'Existing or recent outreach'):
            self.prepare('dm', second_job, second_person)
        workflow.receipt(self.s, action['id'], 'cancelled', 'Never submitted')
        self.prepare('dm', second_job, second_person)

    def test_unknown_expired_credit_and_uncertain_old_hold_stay_conservative(self):
        self.assertIsNone(engagement.inmail_status(self.s)['estimated_available_after_reservations'])
        engagement.observe_balance(self.s, 10, 'Visible 10')
        action = self.prepare('inmail')
        workflow.receipt(self.s, action['id'], 'uncertain', 'Unknown outcome')
        later = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat(timespec='seconds')
        with patch('socialmediaplus.engagement.now', return_value=later):
            status = engagement.inmail_status(self.s)
            self.assertEqual(status['additional_credits_allowed'], 0)
            self.assertEqual(status['rolling_7_day_used_or_reserved'], 1)
            self.assertFalse(status['balance_fresh'])

    def test_snapshots_and_subject_integrity_are_checked(self):
        job, person = self.job()
        action = self.prepare('dm', job, person)
        saved = self.root / action['details']['attachment_path']
        self.resume.write_bytes(b'%PDF-1.7\nchanged original')
        self.assertTrue(engagement.check_action(self.s, action['id'])['integrity_verified'])
        saved.write_bytes(b'changed snapshot')
        with self.assertRaisesRegex(Error, 'changed registered file'):
            engagement.check_action(self.s, action['id'])
        self.assertFalse(reports.doctor(self.s)['ok'])

    def test_reactions_and_attributed_reposts_require_session_and_dedupe(self):
        session = engagement.session_start(self.s, 'engage_plus', 30, 'SMP ENGAGE+ 30')['id']
        options = dict(target='https://www.linkedin.com/feed/update/urn:li:activity:777?commentUrn=99',
                       context='The exact observed comment merits agreement on its specific point.', details={'reaction': 'like'})
        with self.assertRaisesRegex(Error, 'require --session'):
            workflow.prepare(self.s, 'reaction', 'native_linkedin', **options)
        action = workflow.prepare(self.s, 'reaction', 'native_linkedin', session_id=session, **options)['action']
        with self.assertRaisesRegex(Error, 'already has'):
            workflow.prepare(self.s, 'reaction', 'native_linkedin', session_id=session, **options)
        workflow.receipt(self.s, action['id'], 'confirmed', 'Like button now pressed', remote_url=options['target'])
        with self.assertRaisesRegex(Error, 'exact final response'):
            workflow.prepare(self.s, 'repost', 'native_linkedin', session_id=session,
                             target='https://www.linkedin.com/feed/update/urn:li:activity:888', context='Original author and full post')

    def test_v4_migration_keeps_existing_actions_and_relationships(self):
        person = network.add(self.s, 'Peer', 'https://www.linkedin.com/in/peer', 'Observed role')
        action = workflow.prepare(self.s, 'comment', 'native_linkedin', target='https://www.linkedin.com/feed/update/urn:li:activity:123',
                                  response='Specific thought', context='Exact observed post', relationship_id=person['id'])['action']
        self.s.close()
        db = sqlite3.connect(self.root / 'data/socialmediaplus.sqlite3')
        for table in reversed(engagement.TABLES):
            db.execute('DROP TABLE ' + table)
        db.execute('UPDATE schema_version SET version=4')
        db.commit()
        db.close()
        self.s = Store(self.root)
        self.assertEqual(self.s.require('relationships', person['id']), person)
        self.assertEqual(self.s.require('actions', action['id']), action)
        self.assertEqual(self.s.one('SELECT version FROM schema_version')['version'], 7)
        self.assertEqual(self.s.one('SELECT COUNT(*) AS n FROM inmail_reservations')['n'], 0)

    def test_cli_contract_uses_isolated_root_and_preserves_multiline_body(self):
        script = str(Path(__file__).resolve().parents[1] / 'scripts/smp')
        def cli(*args):
            result = subprocess.run([sys.executable, script, '--root', str(self.root), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        session = cli('session', 'start', '--mode', 'engage_plus', '--authorization', 'SMP ENGAGE+ 30')['id']
        textfile = self.root / 'comment.md'
        textfile.write_text('One precise thought.\n\nA useful follow-up question?')
        action = cli('action', 'prepare', '--kind', 'repost', '--authority', 'native_linkedin', '--session', session,
                     '--target', 'https://www.linkedin.com/feed/update/urn:li:activity:989', '--response-file', str(textfile),
                     '--context', 'Full source post and original author context')['action']
        self.assertEqual(action['response'], textfile.read_text())
        self.assertTrue(cli('action', 'check', action['id'])['integrity_verified'])
        cli('session', 'end', session)
        self.assertEqual(cli('inmail', 'status')['additional_credits_allowed'], 0)

    def test_public_template_contains_no_resume_or_enabled_outreach(self):
        project = Path(__file__).resolve().parents[1]
        config = json.loads((project / 'templates/config/engagement-plus.json').read_text())
        self.assertEqual(config['resume']['path'], '')
        self.assertEqual(config['resume']['sha256'], '')
        self.assertEqual(config['outreach']['countries'], [])
        self.assertFalse(config['outreach']['enabled'])
        self.assertFalse(config['inmail']['enabled'])

    def test_refreshed_lower_credit_balance_blocks_existing_reservation(self):
        engagement.observe_balance(self.s, 5, 'Visible five credits')
        action = self.prepare('inmail')
        self.assertTrue(engagement.check_action(self.s, action['id'])['integrity_verified'])
        engagement.observe_balance(self.s, 0, 'Another manual message depleted credits')
        with self.assertRaisesRegex(Error, 'no longer cover'):
            engagement.check_action(self.s, action['id'])
        self.assertEqual(self.s.one('SELECT state FROM inmail_reservations')['state'], 'reserved')

    def test_applicant_type_needs_its_specific_evidence_and_no_conflicting_count(self):
        for updates in ({'applicants_count': None, 'applicants_upper_bound': 9},
                        {'applicant_indicator_type': 'verified_under_10_filter', 'applicants_upper_bound': None},
                        {'applicant_indicator_type': 'verified_under_10_filter', 'applicants_upper_bound': 9, 'applicants_count': 12}):
            job, person = self.job(**updates)
            self.assertFalse(job['eligibility']['eligible'])
            with self.assertRaisesRegex(Error, 'not eligible'):
                self.prepare('dm', job, person)

    def test_confirmation_rejects_tampered_action_fingerprint(self):
        action = self.prepare('dm')
        with self.s.transaction():
            self.s.db.execute('UPDATE actions SET response=? WHERE id=?', ('Unapproved replacement', action['id']))
        with self.assertRaisesRegex(Error, 'immutable evidence changed'):
            workflow.receipt(self.s, action['id'], 'confirmed', 'Visible result', remote_id='thread', observed_details=self.observed(action))
        self.assertEqual(self.s.require('actions', action['id'])['state'], 'prepared')

    def test_repost_mode_and_session_weekly_caps_cover_unresolved_attempts(self):
        def repost(session, target):
            return workflow.prepare(self.s, 'repost', 'native_linkedin', session_id=session, target=target,
                                    response='A specific useful reason to share this attributed source.', context='Original source and author observed')['action']
        with self.assertRaisesRegex(Error, 'outside this plus mode'):
            repost(self.session, 'https://www.linkedin.com/feed/update/urn:li:activity:100')
        session1 = engagement.session_start(self.s, 'engage_plus', 30, 'SMP ENGAGE+ 30')['id']
        first = repost(session1, 'https://www.linkedin.com/feed/update/urn:li:activity:101')
        with self.assertRaisesRegex(Error, 'Repost session'):
            repost(session1, 'https://www.linkedin.com/feed/update/urn:li:activity:102')
        workflow.receipt(self.s, first['id'], 'uncertain', 'Unknown browser result')
        session2 = engagement.session_start(self.s, 'engage_plus', 30, 'SMP ENGAGE+ 30')['id']
        repost(session2, 'https://www.linkedin.com/feed/update/urn:li:activity:103')
        session3 = engagement.session_start(self.s, 'engage_plus', 30, 'SMP ENGAGE+ 30')['id']
        with self.assertRaisesRegex(Error, 'Repost session'):
            repost(session3, 'https://www.linkedin.com/feed/update/urn:li:activity:104')


if __name__ == '__main__':
    unittest.main()
