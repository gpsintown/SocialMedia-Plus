import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from socialmediaplus import imports, network, reports, workflow
from socialmediaplus.store import Error, Store, canonical_url


class FollowerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.s = Store(self.root, create=True)
        self.at = "2026-09-13T10:00:00+00:00"
        self.source = "https://www.linkedin.com/mynetwork/network-manager/people-follow/followers/"

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def row(self, slug="one", **changes):
        return dict(profile_url="https://www.linkedin.com/in/" + slug, name=slug.title(), headline="Analytics lead", **changes)

    def snapshot(self, rows, name="snapshot.json", **changes):
        data = dict(observed_at=self.at, source_url=self.source, expected_count=3,
                    collection_complete=False, rows=rows)
        data.update(changes)
        path = self.root / name
        path.write_text(json.dumps(data))
        return path

    def test_overlap_preserves_profile_classification_review_and_history(self):
        person = network.add(self.s, "Existing name", "https://www.linkedin.com/in/one", "Export", position="Old role")
        network.update(self.s, person["id"], bucket="analytics_leader", evidence="Reviewed role", reviewed_at=self.at, next_review="2026-09-20T10:00:00+00:00", skip="Follow up later")
        workflow.add_interaction(self.s, person["profile_url"], "comment", self.at, "Observed UI", relationship_id=person["id"])
        before = self.s.require("relationships", person["id"])
        snapshot = self.snapshot([self.row()])
        output = imports.import_file(self.s, "followers", snapshot)["import"]["summary"]
        self.assertEqual(self.s.require("relationships", person["id"]), before)
        self.assertEqual(output["connection_overlap_in_snapshot"], 1)
        self.assertEqual(output["inserted"], 0)
        self.assertEqual([m["membership"] for m in network.memberships(self.s, person["id"])], ["connection", "follower"])
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM interactions")["n"], 1)
        observed = self.s.one("SELECT headline FROM membership_observations WHERE membership='follower'")
        self.assertEqual(observed["headline"], "Analytics lead")

    def test_raw_snapshot_private_idempotent_and_duplicate_urls_canonical(self):
        first, duplicate = self.row(), self.row()
        duplicate["profile_url"] = "https://linkedin.com/in/one/?utm_source=example"
        snapshot = self.snapshot([first, duplicate])
        result = imports.import_file(self.s, "followers", snapshot)["import"]
        self.assertEqual(result["summary"]["unique_profiles"], 1)
        self.assertEqual(result["summary"]["duplicate_rows"], 1)
        stored = self.root / result["stored_path"]
        self.assertEqual(stored.read_bytes(), snapshot.read_bytes())
        self.assertEqual(os.stat(stored).st_mode & 0o777, 0o600)
        self.assertTrue(imports.import_file(self.s, "followers", snapshot)["existing"])
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM membership_observations")["n"], 1)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM actions")["n"], 0)

    def test_observed_english_locale_profile_dedupes_but_subpages_remain_invalid(self):
        canonical = "https://www.linkedin.com/in/example-m%C3%A9mber-123"
        observed = canonical + "/en/"
        self.assertEqual(canonical_url(observed, profile=True), canonical)
        self.assertEqual(canonical_url(observed), canonical + "/en")
        for suffix in ("/recent-activity/", "/details/", "/anything/", "/en/recent-activity/", "/enough/"):
            with self.subTest(suffix=suffix), self.assertRaises(Error):
                canonical_url(canonical + suffix, profile=True)
        first, second = self.row(), self.row()
        first["profile_url"], second["profile_url"] = observed, canonical
        snapshot = self.snapshot([first, second])
        result = imports.import_file(self.s, "followers", snapshot)["import"]
        self.assertEqual(result["summary"]["unique_profiles"], 1)
        self.assertEqual(self.s.one("SELECT profile_url FROM relationships")["profile_url"], canonical)
        self.assertEqual((self.root / result["stored_path"]).read_bytes(), snapshot.read_bytes())
        self.assertIn(observed, (self.root / result["stored_path"]).read_text())

    def test_replay_refuses_missing_or_changed_preserved_snapshot_without_mutation(self):
        original = self.snapshot([self.row()])
        result = imports.import_file(self.s, "followers", original)["import"]
        stored = self.root / result["stored_path"]
        before = {table: self.s.all("SELECT * FROM " + table) for table in
                  ("relationships", "relationship_memberships", "membership_observations", "imports")}
        for state in ("changed", "missing"):
            with self.subTest(state=state):
                if state == "changed":
                    stored.write_text('{"rows":[]}')
                else:
                    stored.unlink()
                with self.assertRaisesRegex(Error, "Missing or changed registered file"):
                    imports.import_file(self.s, "followers", original)
                for table, rows in before.items():
                    self.assertEqual(self.s.all("SELECT * FROM " + table), rows)
        stored.write_bytes(original.read_bytes())
        self.assertTrue(imports.import_file(self.s, "followers", original)["existing"])

    def test_connection_import_after_follower_keeps_both_memberships(self):
        imports.import_file(self.s, "followers", self.snapshot([self.row()]))
        person = self.s.one("SELECT * FROM relationships")
        network.update(self.s, person["id"], bucket="analytics_leader", evidence="Observed follower headline")
        csv = self.root / "Connections.csv"
        csv.write_text("First Name,Last Name,URL,Company,Position,Connected On\nOne,Example,https://www.linkedin.com/in/one,Example,Analyst,12 Sep 2026\n")
        imports.import_file(self.s, "connections", csv)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM relationships")["n"], 1)
        self.assertEqual(reports.coverage(self.s)["registered_connections"], 1)
        self.assertEqual(reports.coverage(self.s)["registered_follower_connection_overlap"], 1)
        self.assertEqual(self.s.require("relationships", person["id"])["bucket"], "analytics_leader")

    def test_bad_row_rolls_back_entire_import(self):
        invalid = self.row("two", observed_at="not-a-time")
        with self.assertRaises(Error):
            imports.import_file(self.s, "followers", self.snapshot([self.row(), invalid]))
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM relationships")["n"], 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM imports")["n"], 0)
        self.assertEqual(list((self.root / "data/imports").iterdir()), [])

    def test_unresolved_rows_retained_and_count_match_does_not_imply_finished(self):
        bad = self.row("bad")
        bad["profile_url"] = ""
        summary = imports.import_file(self.s, "followers", self.snapshot([self.row(), bad], expected_count=1, collection_complete=True))["import"]["summary"]
        self.assertEqual(summary["completeness"], "collection_exhausted_unresolved_rows")
        self.assertEqual(summary["unresolved_rows"], [{"row": 2, "reason": "missing_or_invalid_profile_url"}])
        incomplete = imports.import_file(self.s, "followers", self.snapshot([self.row()], "second.json", expected_count=1))["import"]["summary"]
        self.assertEqual(incomplete["completeness"], "partial_inventory")

    def test_snapshot_coverage_separate_from_union_and_older_import(self):
        imports.import_file(self.s, "followers", self.snapshot([self.row()], expected_count=1, collection_complete=True))
        older = self.snapshot([self.row("two")], "older.json", observed_at="2026-09-12T10:00:00+00:00", expected_count=1, collection_complete=True)
        imports.import_file(self.s, "followers", older)
        coverage = reports.coverage(self.s)
        self.assertEqual(coverage["registered_followers"], 2)
        self.assertEqual(coverage["latest_follower_snapshot"]["observed_at"], self.at)
        self.assertEqual(coverage["latest_follower_snapshot"]["unique_profiles"], 1)
        self.assertEqual(coverage["latest_follower_snapshot"]["completeness"], "complete_observed_snapshot")
        self.assertEqual(coverage["follower_only_profiles"], 2)

    def test_empty_unknown_and_zero_count_are_distinct(self):
        unknown = imports.import_file(self.s, "followers", self.snapshot([], expected_count=None, collection_complete=True))["import"]["summary"]
        self.assertEqual(unknown["completeness"], "collection_exhausted_count_unavailable")
        zero = imports.import_file(self.s, "followers", self.snapshot([], "zero.json", expected_count=0, collection_complete=True))["import"]["summary"]
        self.assertEqual(zero["completeness"], "complete_observed_snapshot")
        with self.assertRaisesRegex(Error, "nonnegative integer"):
            imports.import_file(self.s, "followers", self.snapshot([], "invalid.json", expected_count=True))

    def test_mixed_and_membership_filtered_queues_dedupe_and_keep_cooldown(self):
        connection = network.add(self.s, "Connection", "https://www.linkedin.com/in/connection", "Export")
        imports.import_file(self.s, "followers", self.snapshot([self.row(), self.row("connection")]))
        for row in self.s.all("SELECT id FROM relationships"):
            network.update(self.s, row["id"], bucket="analytics_peer", evidence="Explicit role")
        all_people = network.due(self.s)["queue"]
        self.assertEqual(len(all_people), 2)
        self.assertEqual(len(network.due(self.s, membership="follower")["queue"]), 2)
        self.assertEqual(len(network.due(self.s, membership=["follower", "connection"])["queue"]), 2)
        self.assertEqual(network.due(self.s, membership="connection")["queue"][0]["id"], connection["id"])
        from socialmediaplus.store import now
        workflow.add_interaction(self.s, connection["profile_url"], "comment", now(), "Observed", relationship_id=connection["id"])
        self.assertEqual(len(network.due(self.s, membership="follower")["queue"]), 1)
        with self.assertRaisesRegex(Error, "membership"):
            network.due(self.s, membership="following")

    def test_membership_union_and_exclusions_select_follower_only_without_duplicates(self):
        follower = network.add(self.s, "Follower", "https://www.linkedin.com/in/follower", "Visible follower list", relationship_type="follower")
        connection = network.add(self.s, "Connection", "https://www.linkedin.com/in/connection", "Export")
        both = network.add(self.s, "Both", "https://www.linkedin.com/in/both", "Export")
        network.add(self.s, "Both", both["profile_url"], "Visible follower list", relationship_type="follower")
        for person in (follower, connection, both):
            network.update(self.s, person["id"], bucket="analytics_peer", evidence="Explicit professional role")
        combined = network.list_people(self.s, membership=["connection", "follower"])
        self.assertEqual({p["id"] for p in combined}, {follower["id"], connection["id"], both["id"]})
        selected = network.list_people(self.s, membership="follower", exclude_membership="connection")
        self.assertEqual([p["id"] for p in selected], [follower["id"]])
        queue = network.due(self.s, membership=["connection", "follower"], exclude_membership=["connection", "connection"])
        self.assertEqual([p["id"] for p in queue["queue"]], [follower["id"]])
        self.assertEqual(queue["selected_memberships"], ["connection", "follower"])
        self.assertEqual(queue["excluded_memberships"], ["connection"])
        self.assertEqual(network.due(self.s, exclude_membership=["connection", "follower"])["queue"], [])
        with self.assertRaisesRegex(Error, "membership"):
            network.list_people(self.s, exclude_membership="invented")
        with self.assertRaisesRegex(Error, "membership"):
            network.due(self.s, exclude_membership="invented")
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM actions")["n"], 0)

    def test_follower_only_exclusion_preserves_cooldown_and_uses_observation_time(self):
        from socialmediaplus.store import now
        follower = network.add(self.s, "Follower", "https://www.linkedin.com/in/follower", "Follower list", relationship_type="follower")
        network.update(self.s, follower["id"], bucket="analytics_peer", evidence="Explicit role")
        workflow.add_interaction(self.s, follower["profile_url"], "comment", now(), "Observed comment", relationship_id=follower["id"])
        self.assertEqual(network.due(self.s, membership="follower", exclude_membership="connection")["queue"], [])
        selected = network.due(self.s, membership="follower", exclude_membership="connection", cooldown_hours=0)
        self.assertEqual([p["id"] for p in selected["queue"]], [follower["id"]])
        # A later connection observation does not retroactively exclude an
        # incoming follower from an earlier inventory snapshot.
        with self.s.transaction():
            network.observe_membership(self.s, follower["id"], "connection", "2099-01-01T00:00:00+00:00", "Later connection export")
        historical = network.due(self.s, membership="follower", exclude_membership="connection", cooldown_hours=0)
        self.assertEqual([p["id"] for p in historical["queue"]], [follower["id"]])
        future = network.due(self.s, as_of="2099-01-02T00:00:00+00:00", membership="follower", exclude_membership="connection")
        self.assertEqual(future["queue"], [])

    def test_v3_migration_keeps_relationship_and_history(self):
        person = network.add(self.s, "Existing", "https://www.linkedin.com/in/existing", "Original export")
        network.update(self.s, person["id"], bucket="analytics_peer", evidence="BI analyst")
        workflow.add_interaction(self.s, person["profile_url"], "visit", self.at, "Observed", relationship_id=person["id"])
        before = self.s.require("relationships", person["id"])
        self.s.close()
        with closing(sqlite3.connect(self.root / "data/socialmediaplus.sqlite3")) as db:
            db.execute("DROP TABLE membership_observations")
            db.execute("DROP TABLE relationship_memberships")
            db.execute("UPDATE schema_version SET version=3")
            db.commit()
        self.s = Store(self.root)
        self.assertEqual(self.s.require("relationships", person["id"]), before)
        self.assertEqual(network.memberships(self.s, person["id"])[0]["membership"], "connection")
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM interactions")["n"], 1)
        self.assertEqual(self.s.one("SELECT version FROM schema_version")["version"], 7)

    def test_cli_import_coverage_and_daily_with_follower_filter(self):
        script = Path(__file__).resolve().parents[1] / "scripts/smp"
        snapshot = self.snapshot([self.row()])
        def run(*args):
            result = subprocess.run([sys.executable, str(script), "--root", str(self.root), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(run("import", "followers", str(snapshot))["import"]["summary"]["inserted"], 1)
        self.assertEqual(run("relationship", "coverage")["registered_followers"], 1)
        self.assertEqual(len(run("relationship", "list", "--membership", "follower", "--exclude-membership", "connection")), 1)
        due = run("relationship", "due", "--membership", "follower", "--exclude-membership", "connection", "--priority", "rotation")
        self.assertEqual(len(due["queue"]), 1)
        self.assertEqual(due["excluded_memberships"], ["connection"])
        result = run("daily", "--membership", "follower", "--exclude-membership", "connection", "--priority", "rotation")
        report = json.loads(Path(result["json"]).read_text())
        self.assertEqual(report["relationships"]["selected_memberships"], ["follower"])
        self.assertEqual(report["relationships"]["excluded_memberships"], ["connection"])
        self.assertEqual(len(report["relationships"]["queue"]), 1)
        self.assertIn("Excluded memberships: connection.", Path(result["markdown"]).read_text())


if __name__ == "__main__":
    unittest.main()
