import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from socialmediaplus.store import Error, Store, canonical_url, timestamp
from socialmediaplus import imports, network, reports, workflow


def workbook(sheets):
    output = io.BytesIO()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(output, "w") as z:
        sheet_list, rels = [], []
        for i, (name, rows) in enumerate(sheets.items(), 1):
            sheet_list.append('<sheet name="' + escape(name) + '" sheetId="' + str(i) + '" r:id="rId' + str(i) + '"/>')
            rels.append('<Relationship Id="rId' + str(i) + '" Target="worksheets/sheet' + str(i) + '.xml"/>')
            xml_rows = []
            for j, row in enumerate(rows, 1):
                cells = []
                for k, value in enumerate(row):
                    cells.append('<c r="' + chr(65 + k) + str(j) + '" t="inlineStr"><is><t>' + escape(str(value)) + '</t></is></c>')
                xml_rows.append('<row>' + ''.join(cells) + '</row>')
            z.writestr('xl/worksheets/sheet' + str(i) + '.xml', '<worksheet xmlns="' + ns + '"><sheetData>' + ''.join(xml_rows) + '</sheetData></worksheet>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="' + ns + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(sheet_list) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships>' + ''.join(rels) + '</Relationships>')
    return output.getvalue()


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s = Store(self.root, create=True)
        self.s.settings["profile_url"] = "https://www.linkedin.com/in/example-member/"
        self.future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(timespec="seconds")

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def file(self, name, content):
        path = self.root / name
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def draft(self, text="One actual technical observation with a useful, specific tradeoff.", format="text"):
        return workflow.content_add(self.s, self.file("draft.md", text), "A draft", "analytics", "peers", format, ["user supplied experience"])["id"]

    def scheduled(self):
        post = self.draft()
        workflow.set_slot(self.s, post, self.future, "UTC")
        workflow.approve(self.s, post, "user", "explicit authorization in test fixture")
        action = workflow.prepare(self.s, "schedule", "native_linkedin", post)["action"]["id"]
        return post, action

    def test_timezone_dst_and_offset_validation(self):
        self.assertEqual(timestamp("2026-09-14T09:00:00", "Asia/Kolkata"), "2026-09-14T03:30:00+00:00")
        with self.assertRaisesRegex(Error, "does not exist"):
            timestamp("2026-03-29T02:30:00", "Europe/Berlin")
        with self.assertRaisesRegex(Error, "ambiguous"):
            timestamp("2026-10-25T02:30:00", "Europe/Berlin")
        self.assertEqual(timestamp("2026-10-25T02:30:00+02:00", "Europe/Berlin"), "2026-10-25T00:30:00+00:00")
        with self.assertRaisesRegex(Error, "does not match"):
            timestamp("2026-09-14T09:00:00+00:00", "Asia/Kolkata")

    def test_approval_invalidation_by_revision_slot_and_asset(self):
        post = self.draft()
        workflow.approve(self.s, post, "user", "approval")
        workflow.set_slot(self.s, post, self.future, "UTC")
        with self.assertRaisesRegex(Error, "not been approved"):
            workflow.prepare(self.s, "schedule", "postiz", post)
        workflow.approve(self.s, post, "user", "approval with slot")
        workflow.asset_add(self.s, post, self.file("image.png", b"a real file snapshot"), "Description", "user-owned fixture")
        with self.assertRaisesRegex(Error, "not been approved"):
            workflow.prepare(self.s, "schedule", "postiz", post)
        workflow.approve(self.s, post, "user", "approval with asset")
        workflow.content_revise(self.s, post, self.file("new.md", "A different final version."))
        with self.assertRaisesRegex(Error, "not been approved"):
            workflow.prepare(self.s, "schedule", "postiz", post)

    def test_asset_tampering_is_detected_before_action(self):
        post = self.draft(format="image")
        asset = workflow.asset_add(self.s, post, self.file("pic.png", b"pixel-data"), "Actual image", "owned")
        workflow.approve(self.s, post, "user", "approved")
        (self.root / asset["path"]).write_bytes(b"different pixels")
        with self.assertRaisesRegex(Error, "changed registered file"):
            workflow.prepare(self.s, "publish", "postiz", post)
        self.assertFalse(reports.doctor(self.s)["ok"])

    def test_format_change_invalidates_approval_and_preserves_version(self):
        post = self.draft()
        approval = workflow.approve(self.s, post, "user", "Approve exact text post")
        original_version = self.s.one("SELECT * FROM versions WHERE content_id=?", (post,))
        changed = workflow.set_format(self.s, post, "image")
        self.assertEqual(changed["format"], "image")
        self.assertEqual(changed["status"], "draft")
        self.assertNotEqual(workflow.fingerprint(self.s, post), approval["fingerprint"])
        self.assertEqual(self.s.one("SELECT * FROM versions WHERE content_id=?", (post,)), original_version)
        with self.assertRaisesRegex(Error, "not been approved"):
            workflow.prepare(self.s, "publish", "native_linkedin", post)
        with self.assertRaisesRegex(Error, "requires a registered final asset"):
            workflow.approve(self.s, post, "user", "Premature image approval")
        workflow.asset_add(self.s, post, self.file("format.png", b"fixture image"), "Fixture asset", "User-owned test fixture")
        workflow.approve(self.s, post, "user", "Approve final image and exact caption")
        self.assertEqual(workflow.prepare(self.s, "publish", "native_linkedin", post)["action"]["state"], "prepared")

    def test_format_noop_preserves_approval_and_active_action_blocks_changes(self):
        post = self.draft()
        workflow.approve(self.s, post, "user", "Approve exact text post")
        approved = self.s.require("content", post)
        with patch("socialmediaplus.workflow.now", return_value=self.future):
            workflow.set_format(self.s, post, "text")
        self.assertEqual(self.s.require("content", post), approved)
        action = workflow.prepare(self.s, "publish", "native_linkedin", post)["action"]
        before = self.s.require("content", post)
        with self.assertRaisesRegex(Error, "locked"):
            workflow.set_format(self.s, post, "image")
        self.assertEqual(self.s.require("content", post), before)
        self.assertEqual(self.s.require("actions", action["id"]), action)
        workflow.set_format(self.s, post, "text")
        self.assertEqual(self.s.require("content", post), before)

    def test_format_cli_dispatch_and_unsupported_format_leave_records_intact(self):
        post = self.draft()
        process = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/smp"),
                                  "--root", str(self.root), "content", "format", post, "--format", "document"],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["format"], "document")
        before = self.s.require("content", post)
        with self.assertRaisesRegex(Error, "Unsupported content format"):
            workflow.set_format(self.s, post, "unknown")
        self.assertEqual(self.s.require("content", post), before)

    def test_duplicate_authority_and_uncertain_retry(self):
        post, action = self.scheduled()
        self.assertTrue(workflow.prepare(self.s, "schedule", "native_linkedin", post)["existing"])
        with self.assertRaisesRegex(Error, "active publishing"):
            workflow.prepare(self.s, "schedule", "postiz", post)
        workflow.receipt(self.s, action, "uncertain", "Browser timed out; outcome unknown")
        with self.assertRaisesRegex(Error, "uncertain outcomes"):
            workflow.retry(self.s, action, "Try once more")
        with self.assertRaisesRegex(Error, "locked"):
            workflow.content_revise(self.s, post, self.file("revised.md", "Must stay locked."))
        workflow.receipt(self.s, action, "failed", "Verified empty remote queue", reconcile=True)
        result = workflow.retry(self.s, action, "Remote queue checked and action absent")
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(result["state"], "prepared")

    def test_future_slot_cannot_publish_immediately_and_expired_schedule_cannot_retry(self):
        post, action = self.scheduled()
        workflow.receipt(self.s, action, "failed", "Verified absent")
        with self.assertRaisesRegex(Error, "bypass the approved future slot"):
            workflow.prepare(self.s, "publish", "postiz", post)
        later = (datetime.fromisoformat(self.future) + timedelta(hours=1)).isoformat()
        with patch("socialmediaplus.workflow.now", return_value=later):
            with self.assertRaisesRegex(Error, "scheduled instant has passed"):
                workflow.retry(self.s, action, "No remote submission")

    def test_reconciliation_cannot_resurrect_competing_authority(self):
        post, old_action = self.scheduled()
        workflow.receipt(self.s, old_action, "failed", "Verified absent")
        later = (datetime.fromisoformat(self.future) + timedelta(hours=1)).isoformat()
        with patch("socialmediaplus.workflow.now", return_value=later):
            new_action = workflow.prepare(self.s, "publish", "native_linkedin", post)["action"]["id"]
            with self.assertRaisesRegex(Error, "Another publishing action is active"):
                workflow.receipt(self.s, old_action, "confirmed", "Old queue item found", remote_id="old-queue", reconcile=True)
        self.assertEqual(self.s.require("actions", new_action)["state"], "prepared")
        self.assertEqual(self.s.require("actions", old_action)["state"], "failed")

    def test_old_reconciliation_cannot_overwrite_new_version_status(self):
        post, old_action = self.scheduled()
        workflow.receipt(self.s, old_action, "failed", "Verified absent")
        workflow.content_revise(self.s, post, self.file("version-two.md", "A revised source-grounded version."))
        workflow.set_route(self.s, post, "postiz")
        workflow.approve(self.s, post, "user", "Approved revision")
        new_action = workflow.prepare(self.s, "schedule", "postiz", post)["action"]["id"]
        workflow.receipt(self.s, new_action, "confirmed", "New queue item visible", remote_id="new-queue")
        workflow.receipt(self.s, old_action, "cancelled", "Old item confirmed absent/cancelled", reconcile=True)
        self.assertEqual(self.s.require("content", post)["status"], "scheduled")
        self.assertEqual(self.s.require("actions", new_action)["state"], "confirmed")

    def test_authority_is_bound_per_content_not_live_global_config(self):
        post = self.draft()
        workflow.set_slot(self.s, post, self.future, "UTC")
        first = workflow.approve(self.s, post, "user", "Approve native LinkedIn schedule")
        self.s.settings["publishing_mode"] = "postiz"
        self.assertEqual(workflow.fingerprint(self.s, post), first["fingerprint"])
        with self.assertRaisesRegex(Error, "approved per-content route"):
            workflow.prepare(self.s, "schedule", "postiz", post)
        workflow.set_route(self.s, post, "postiz")
        with self.assertRaisesRegex(Error, "not been approved"):
            workflow.prepare(self.s, "schedule", "postiz", post)
        second = workflow.approve(self.s, post, "user", "Approve Postiz schedule instead")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        action = workflow.prepare(self.s, "schedule", "postiz", post)
        self.assertEqual(action["action"]["authority"], "postiz")
        with self.assertRaisesRegex(Error, "locked"):
            workflow.set_route(self.s, post, "user_manual")
        fresh = self.draft("Another distinct approved idea for a manual publication.")
        workflow.set_route(self.s, fresh, "user_manual")
        workflow.approve(self.s, fresh, "user", "Approve manual publication")
        self.assertEqual(workflow.prepare(self.s, "publish", "user_manual", fresh)["action"]["authority"], "user_manual")

    def test_schedule_receipts_and_publication_have_distinct_states(self):
        post, action = self.scheduled()
        with self.assertRaisesRegex(Error, "remote URL or remote ID"):
            workflow.receipt(self.s, action, "confirmed", "Looks scheduled")
        workflow.receipt(self.s, action, "confirmed", "Exact item visible in queue", remote_id="native queue item 1")
        self.assertEqual(self.s.require("content", post)["status"], "scheduled")
        after = (datetime.fromisoformat(self.future) + timedelta(minutes=1)).isoformat()
        workflow.publication(self.s, action, "Published post visible", "https://www.linkedin.com/posts/example-123", after)
        self.assertEqual(self.s.require("content", post)["status"], "published")
        self.assertEqual(len(workflow.action_show(self.s, action)["receipts"]), 2)

    def test_cancel_requires_reconciliation_and_allows_revision(self):
        post, action = self.scheduled()
        workflow.receipt(self.s, action, "confirmed", "Queue evidence", remote_id="q1")
        with self.assertRaisesRegex(Error, "locked"):
            workflow.asset_add(self.s, post, self.file("new.png", b"new"), "New asset", "owned")
        workflow.receipt(self.s, action, "cancelled", "Verified cancellation in native queue", reconcile=True)
        workflow.content_revise(self.s, post, self.file("after.md", "A revised edition after remote cancellation."))
        self.assertEqual(self.s.require("content", post)["current_version"], 2)

    def test_comment_urls_keep_precise_targets_and_dedupe(self):
        first = canonical_url("https://www.linkedin.com/feed/update/urn:li:activity:1/?commentUrn=comment1&utm_source=test")
        second = canonical_url("https://www.linkedin.com/feed/update/urn:li:activity:1/?commentUrn=comment2")
        self.assertNotEqual(first, second)
        a = workflow.prepare(self.s, "comment", "user_manual", target=first, response="A useful addition.", context="Original post context")
        b = workflow.prepare(self.s, "comment", "user_manual", target=first, response="A useful addition.", context="Original post context")
        self.assertTrue(b["existing"])
        self.assertEqual(a["action"]["id"], b["action"]["id"])

    def test_confirmed_profile_and_post_actions_link_relationship_history(self):
        person = network.add(self.s, "Example", "https://www.linkedin.com/in/example", "Observed profile")
        visit = workflow.prepare(self.s, "visit", "user_manual", target=person["profile_url"])["action"]["id"]
        workflow.receipt(self.s, visit, "confirmed", "User visited profile", remote_url=person["profile_url"])
        comment = workflow.prepare(self.s, "comment", "user_manual", target="https://www.linkedin.com/posts/example-1", response="Specific point", context="Original relevant context", relationship_id=person["id"])["action"]["id"]
        workflow.receipt(self.s, comment, "confirmed", "Comment visible", remote_id="comment-1")
        self.assertEqual(network.due(self.s, priority="rotation")["queue"][0]["recorded_interactions"], 2)

    def test_import_connections_idempotent_unclassified_no_email(self):
        p = self.file("Connections.csv", "Notes about export\n\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\nAda,Example,https://linkedin.com/in/ada-example/,private@example.test,Example,Analytics lead,12 Sep 2026\n")
        out = imports.import_file(self.s, "connections", p)
        self.assertEqual(out["import"]["summary"]["inserted"], 1)
        self.assertTrue(imports.import_file(self.s, "connections", p)["existing"])
        row = self.s.one("SELECT * FROM relationships")
        self.assertEqual(row["bucket"], "unclassified")
        self.assertNotIn("email", row)
        with self.assertRaisesRegex(Error, "evidence"):
            network.update(self.s, row["id"], bucket="analytics_leader")
        network.update(self.s, row["id"], bucket="analytics_leader", evidence="Observed headline", geography="Germany", geography_evidence="Profile explicitly lists Berlin")
        self.assertEqual(network.due(self.s)["queue"][0]["geography"], "Germany")

    def test_native_xlsx_ranked_tables_keep_url_metric_alignment(self):
        first, second = "https://www.linkedin.com/posts/a", "https://www.linkedin.com/posts/b"
        raw = workbook({
            "DISCOVERY": [["Overall Performance", "9/1/2026 - 9/12/2026"], ["Impressions", "1000"], ["Members reached", "700"]],
            "TOP POSTS": [["Maximum of 50 posts"], [], ["Post URL", "Post Publish Date", "Engagements", "", "Post URL", "Post Publish Date", "Impressions"],
                          [first, "9/1/2026", "9", "", second, "9/2/2026", "300"], [second, "9/2/2026", "4", "", first, "9/1/2026", "200"]],
            "ENGAGEMENT": [["Date", "Impressions", "Engagements"], ["9/1/2026", "0", "-1"], ["9/2/2026", "10", "1"]],
            "FOLLOWERS": [["Total followers on 9/12/2026", "50"], [], ["Date", "New followers"], ["9/1/2026", "1"]],
            "AUDIENCE DEMOGRAPHICS": [["Top Demographics", "Value", "Percentage"], ["Location", "Berlin", "< 1%"]],
        })
        result = imports.import_file(self.s, "metrics", self.file("analytics.xlsx", raw), "2026-09-12T12:00:00+00:00")
        first_metrics = {x["metric"]: x["value"] for x in self.s.all("SELECT * FROM metrics WHERE target_url=?", (first,))}
        self.assertEqual(first_metrics, {"engagements": 9.0, "impressions": 200.0})
        self.assertEqual(self.s.one("SELECT value FROM metrics WHERE metric='impressions' AND window='day:2026-09-01'")["value"], 0)
        self.assertEqual(self.s.one("SELECT value FROM metrics WHERE metric='engagements' AND window='day:2026-09-01'")["value"], -1)
        self.assertEqual(json.loads(self.s.one("SELECT raw_json FROM history")["raw_json"])["percentage_reported"], "< 1%")
        self.assertGreater(result["import"]["summary"]["inserted"], 5)

    def test_unknown_metrics_stay_unavailable_and_rates_require_same_age(self):
        post = self.draft()
        at = "2026-09-12T12:00:00+00:00"
        for name, value in (("impressions", "100"), ("reactions", "3"), ("comments", "2"), ("reposts", None)):
            imports.metric_add(self.s, name, value, "observed UI", at, "24h", post)
        group = reports.performance(self.s)["groups"][0]
        self.assertIsNone(group["metrics"]["reposts"]["value"])
        self.assertIsNone(group["engagement_rate"]["value"])
        imports.metric_add(self.s, "reposts", 0, "observed UI", at, "24h", post)
        # New same-time observation replaces unavailability by insertion order.
        self.assertEqual(reports.performance(self.s)["groups"][0]["engagement_rate"]["value"], 0.05)
        imports.metric_add(self.s, "comments", 4, "observed UI", "2026-09-13T12:00:00+00:00", "24h", post)
        self.assertIsNone(reports.performance(self.s)["groups"][0]["engagement_rate"]["value"])

    def test_metric_scope_cannot_mix_account_totals_with_post_medians(self):
        post = self.draft()
        with self.assertRaisesRegex(Error, "Account metrics cannot"):
            imports.metric_add(self.s, "impressions", 10000, "UI", "2026-09-12T12:00:00+00:00", "7d", post, scope="account")
        with self.assertRaisesRegex(Error, "Post metrics require"):
            imports.metric_add(self.s, "impressions", 100, "UI", "2026-09-12T12:00:00+00:00", "7d", scope="post")

    def test_historical_daily_reports_select_measurement_day_not_import_time(self):
        imports.metric_add(self.s, "impressions", 12, "export", "2026-09-12T12:00:00+00:00", "day:2026-08-04", scope="account")
        imports.metric_add(self.s, "impressions", 99, "export", "2026-09-12T12:00:00+00:00", "day:2026-08-12", scope="account")
        result = reports.performance(self.s, "2026-08-02T18:30:00+00:00", "2026-08-09T18:30:00+00:00")
        self.assertEqual(result["daily_account_totals"]["impressions"]["sum_measured"], 12)
        self.assertEqual(result["observations"], 1)

    def test_metric_bad_value_rolls_back_whole_import(self):
        p = self.file("bad.csv", "Metric,Value\nImpressions,100\nReactions,invented\n")
        with self.assertRaises(Error):
            imports.import_file(self.s, "metrics", p)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM metrics")["n"], 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM imports")["n"], 0)

    def test_archive_selects_only_allowed_files_and_rejects_traversal(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            z.writestr("Shares.csv", "Date,ShareLink,ShareCommentary\n2026-09-12,https://www.linkedin.com/posts/a,Actual shared perspective\n")
            z.writestr("Messages.csv", "From,Body\nPrivate,Not selected\n")
            z.writestr("Profile.csv", "First Name,Headline,Birth Date,Address,Email\nExample,Analytics,1990-01-01,Private address,private@example.test\n")
        result = imports.import_file(self.s, "archive", self.file("archive.zip", output.getvalue()))
        self.assertEqual(result["import"]["summary"]["selected_files"], ["Shares.csv", "Profile.csv"])
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM history")["n"], 2)
        profile = json.loads(self.s.one("SELECT raw_json FROM history WHERE kind='profile'")["raw_json"])
        self.assertEqual(profile, {"firstname": "Example", "headline": "Analytics"})
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../Connections.csv", "bad")
        with self.assertRaisesRegex(Error, "Unsafe"):
            imports.import_file(self.s, "archive", self.file("unsafe.zip", bad.getvalue()))

    def test_actual_archive_html_and_professional_csv_shapes_are_sanitized(self):
        output = io.BytesIO()
        published = '''<html><head><title>Title</title><style>SECRET STYLE</style></head><body>
<h1><a href="https://www.linkedin.com/pulse/article-example">A real article</a></h1>
<p class="created">Created on 2020-09-01 01:07</p><p class="published">Published on 2020-09-01 01:32</p>
<div><p>First paragraph &amp; detail.</p><p>Second <strong>paragraph</strong>.</p>
<script>SECRET SCRIPT</script><iframe src="https://external.invalid">SECRET EMBED</iframe><img src="https://external.invalid/image"></div></body></html>'''
        draft = '<html><head><title>Empty draft</title></head><body><h1>Empty draft</h1><p class="published">Published on ---</p><div></div></body></html>'
        with zipfile.ZipFile(output, "w") as z:
            z.writestr("Articles/Articles/a.html", published)
            z.writestr("Articles/Articles/draft.html", draft)
            z.writestr("Skills.csv", "Name\nPower BI\nSQL\n")
            z.writestr("Certifications.csv", "Name,Authority,License Number,Email\nProfessional certification,Issuer,SECRET-LICENSE,private@example.test\n")
            z.writestr("Positions.csv", "Company Name,Title,Description,Location,Started On,Finished On\nExample,Analyst,Public professional work,City,Sep 2020,\n")
            z.writestr("Messages.csv", "THIS PAYLOAD IS NOT READ")
            z.writestr("Connections.csv", "First Name,Last Name,URL,Email Address,Company,Position,Connected On\nNo,URL,,private@example.test,Example,Analyst,1 Sep 2020\n")
        out = imports.import_file(self.s, "archive", self.file("actual-format.zip", output.getvalue()))
        self.assertEqual(out["import"]["summary"]["article_states"], {"published": 1, "unpublished": 1})
        self.assertEqual(out["import"]["summary"]["unresolved_connections"], 1)
        article = self.s.one("SELECT * FROM history WHERE kind='articles' AND target_url IS NOT NULL")
        data = json.loads(article["raw_json"])
        self.assertEqual(data["body"], "First paragraph & detail.\n\nSecond paragraph.")
        self.assertIsNone(article["occurred_at"])
        self.assertEqual(data["published_at_export"], "2020-09-01 01:32")
        all_history = json.dumps(self.s.all("SELECT * FROM history"))
        self.assertNotIn("SECRET", all_history)
        self.assertNotIn("private@example.test", all_history)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM history WHERE kind='skills'")["n"], 2)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM relationships")["n"], 0)

    def test_batch_classification_is_atomic_and_preserves_existing_review(self):
        one = network.add(self.s, "One", "https://www.linkedin.com/in/one", "Archive")
        two = network.add(self.s, "Two", "https://www.linkedin.com/in/two", "Archive")
        network.update(self.s, two["id"], bucket="analytics_leader", evidence="Reviewed title")
        selected = {"profile_url": one["profile_url"], "proposed_bucket": "analytics_peer", "evidence": "Position: BI analyst", "apply": True, "confidence": "high"}
        preserve = dict(selected, profile_url=two["profile_url"])
        proposal = self.file("proposal.json", json.dumps({"proposals": [selected, preserve]}))
        result = network.apply_proposal(self.s, proposal, "Reviewed source-grounded role proposal")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["preserved_reviewed"], 1)
        self.assertEqual(self.s.require("relationships", two["id"])["bucket"], "analytics_leader")
        self.assertIsNone(self.s.require("relationships", one["id"])["last_reviewed_at"])
        fresh = network.add(self.s, "Three", "https://www.linkedin.com/in/three", "Archive")
        bad = self.file("bad-proposal.json", json.dumps([dict(selected, profile_url=fresh["profile_url"]), dict(selected, profile_url="https://www.linkedin.com/in/not-imported")]))
        with self.assertRaisesRegex(Error, "not been imported"):
            network.apply_proposal(self.s, bad, "Decision")
        self.assertEqual(self.s.require("relationships", fresh["id"])["bucket"], "unclassified")

    def test_daily_priority_uses_recorded_exchanges_roles_and_contact_cooldown(self):
        unknown = network.add(self.s, "A unknown role", "https://www.linkedin.com/in/unknown", "Archive")
        expert = network.add(self.s, "B analytics", "https://www.linkedin.com/in/expert", "Archive")
        recent = network.add(self.s, "C recently contacted", "https://www.linkedin.com/in/recent", "Archive")
        exchange = network.add(self.s, "Z past exchange", "https://www.linkedin.com/in/exchange", "Archive")
        for person in (expert, recent):
            network.update(self.s, person["id"], bucket="analytics_peer", evidence="Position explicitly says BI analyst")
        workflow.add_interaction(self.s, "https://www.linkedin.com/posts/past", "comment", "2026-09-10T10:00:00+00:00", "Observed comment", relationship_id=exchange["id"])
        workflow.add_interaction(self.s, recent["profile_url"], "visit", "2026-09-12T11:00:00+00:00", "Observed visit", relationship_id=recent["id"])
        result = network.due(self.s, "2026-09-12T12:00:00+00:00", 8)
        self.assertEqual([x["id"] for x in result["queue"]], [exchange["id"], expert["id"]])
        self.assertIn("No unanswered reply is implied", result["queue"][0]["reason"])
        self.assertIn("have not been checked", result["queue"][1]["reason"])
        self.assertEqual(result["contact_cooldown_hours"], 24)
        self.assertIn(unknown["id"], [x["id"] for x in network.due(self.s, "2026-09-12T12:00:00+00:00", 8, priority="rotation")["queue"]])
        network.update(self.s, exchange["id"], next_review="2026-09-20T12:00:00+00:00")
        self.assertEqual([x["id"] for x in network.due(self.s, "2026-09-12T12:00:00+00:00", 8)["queue"]], [expert["id"]])

    def test_reports_do_not_start_pilot_or_schedule_posts(self):
        post = self.draft()
        plan = reports.plan_week(self.s, "2026-09-14")
        self.assertEqual(len(plan["summary"]["slots"]), 3)
        self.assertEqual(plan["summary"]["slots"][0]["proposed_utc"], "2026-09-14T09:00:00+00:00")
        self.assertEqual(self.s.require("content", post)["status"], "draft")
        self.assertEqual(reports.review(self.s, eight_week=True)["summary"]["state"], "awaiting_first_publication")
        self.assertTrue(Path(reports.daily(self.s)["markdown"]).exists())

    def test_plan_preserves_assigned_slots_and_partial_network_coverage(self):
        post = self.draft()
        workflow.set_slot(self.s, post, "2026-09-16T14:00:00", "Asia/Kolkata")
        plan = reports.plan_week(self.s, "2026-09-14")["summary"]
        actual = next(x for x in plan["slots"] if x["content_id"] == post)
        self.assertEqual(actual["proposed_utc"], "2026-09-16T08:30:00+00:00")
        self.assertEqual(actual["time_basis"], "registered_slot")
        (self.root / "profile").mkdir()
        (self.root / "profile/baseline.json").write_text(json.dumps({"metrics": [{"name": "connections", "value": 1358}]}))
        network.add(self.s, "Example", "https://www.linkedin.com/in/example", "visible sample")
        coverage = reports.status(self.s)["network_coverage"]
        self.assertEqual(coverage["registered_connections"], 1)
        self.assertEqual(coverage["expected_connections_observed"], 1358)
        self.assertEqual(coverage["completeness"], "partial_inventory")

    def test_cli_root_after_subcommand_and_real_json_output(self):
        script = Path(__file__).resolve().parents[1] / "scripts/smp"
        result = subprocess.run([sys.executable, str(script), "status", "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["root"], str(self.root.resolve()))

    def test_near_duplicate_hook_advisory(self):
        first = self.draft("The dashboard was fast, but the definitions were still wrong.\nWe changed the review process and recorded the tradeoff.")
        second = self.draft("The dashboard was fast, but the definitions were still wrong.\nA different observation belongs in this example.")
        self.assertTrue(any(x["record_id"] == first for x in workflow.content_check(self.s, second)["advisories"] if "record_id" in x))


if __name__ == "__main__":
    unittest.main()
