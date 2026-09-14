import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from socialmediaplus import reports
from socialmediaplus.store import Error, Store, dump, ident


class HistoryLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s = Store(self.root, create=True)
        self.post = "https://www.linkedin.com/feed/update/urn:li:activity:123"

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def row(self, kind="comments", target=None, text="A specific imported comment", at=None, raw=None):
        identifier = ident("history")
        with self.s.transaction():
            self.s.insert("history", dict(id=identifier, kind=kind, target_url=target or self.post,
                                        text=text, occurred_at=at, source="imports/private.zip#Comments.csv",
                                        raw_json=dump(raw or {}), dedup_key=identifier))
        return identifier

    def test_exact_target_matches_colon_encoding_but_not_other_identities(self):
        expected = self.row(target=self.post.replace(":li:activity:", "%3Ali%3aactivity%3A"))
        self.row(target=self.post.replace("activity", "ugcPost"))
        self.row(target=self.post + "?commentUrn=urn%3Ali%3Acomment%3A1")
        self.row(target=self.post.replace("123", "1234"))
        result = reports.history_list(self.s, target=self.post + "/?utm_source=test")
        self.assertEqual([r["id"] for r in result["records"]], [expected])
        comment = reports.history_list(self.s, target=self.post + "?commentUrn=urn:li:comment:1")
        self.assertEqual(comment["returned"], 1)
        self.assertNotEqual(comment["records"][0]["id"], expected)
        self.assertEqual(reports.history_list(self.s, target=self.post + "?commentUrn=urn:li:comment:2")["returned"], 0)

    def test_filters_are_parameterized_literal_and_composable(self):
        expected = self.row(text="Discuss 100%_growth without guessing")
        self.row(kind="reactions", text="100%_growth")
        self.row(text="1000 growth")
        result = reports.history_list(self.s, ["comments", "instant_reposts"], query="100%_GROWTH")
        self.assertEqual([r["id"] for r in result["records"]], [expected])
        self.assertEqual(reports.history_list(self.s, ["comments') OR 1=1 --"])["returned"], 0)
        self.assertEqual(reports.history_list(self.s, query="' OR 1=1 --")["returned"], 0)

    def test_source_date_and_recovery_are_preserved_without_private_raw_block(self):
        self.row(raw={"message": "private original", "_export": {
            "raw_date": "2026-09-13 10:02:30", "time_zone": None,
            "date_status": "zone_unspecified", "parsing": "final_column_boundary_recovery",
            "record_number": 9, "line_start": 12, "line_end": 14,
            "raw_block": "private exact CSV block", "source": "private source",
            "source_rows": [{"text": "private multiasset raw row"}, {"text": "private second row"}],
            "media_urls": ["https://example.test/first", "https://example.test/second"],
            "recovery_limits": "Internal quotes preserved; escape semantics unresolved.",
        }})
        changes = self.s.db.total_changes
        result = reports.history_list(self.s)
        row = result["records"][0]
        self.assertEqual(row["source"], "imports/private.zip#Comments.csv")
        self.assertEqual(row["raw_date"], "2026-09-13 10:02:30")
        self.assertEqual(row["date_status"], "zone_unspecified")
        self.assertIsNone(row["occurred_at"])
        self.assertIsNone(row["time_zone"])
        self.assertTrue(row["recovered_record"])
        self.assertEqual(row["export_evidence"]["line_end"], 14)
        self.assertEqual(row["export_evidence"]["source_row_count"], 2)
        self.assertEqual(row["export_evidence"]["media_urls"], ["https://example.test/first", "https://example.test/second"])
        self.assertIn("escape semantics unresolved", row["export_evidence"]["recovery_limits"])
        self.assertEqual(row["evidence_type"], "imported_history_not_live_receipt")
        self.assertNotIn("private exact CSV block", json.dumps(result))
        self.assertNotIn("private multiasset raw row", json.dumps(result))
        self.assertNotIn("raw_json", row)
        self.assertNotIn("relationship_id", row)
        self.assertEqual(self.s.db.total_changes, changes)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM interactions")["n"], 0)
        self.assertEqual(self.s.one("SELECT COUNT(*) AS n FROM receipts")["n"], 0)

    def test_recent_source_dates_are_usable_without_inventing_utc_instants(self):
        older = self.row(at="2026-09-11T10:00:00+00:00")
        unknown = self.row(raw={"date": "not a recognized date"})
        newest = self.row(raw={"_export": {"raw_date": "2026-09-13 20:00:00", "date_status": "zone_unspecified"}})
        records = reports.history_list(self.s)["records"]
        self.assertEqual([r["id"] for r in records], [newest, older, unknown])
        self.assertIsNone(records[0]["occurred_at"])
        self.assertEqual(records[0]["ordering_date_basis"], "original_source_date")
        self.assertEqual(records[-1]["ordering_date_basis"], "unavailable")

    def test_limits_and_input_validation(self):
        for index in range(23):
            self.row(text=str(index))
        default = reports.history_list(self.s)
        self.assertEqual(default["returned"], 20)
        self.assertTrue(default["has_more"])
        self.assertFalse(reports.history_list(self.s, limit=100)["has_more"])
        for limit in (0, -1, 101, True, "20"):
            with self.assertRaises(Error):
                reports.history_list(self.s, limit=limit)
        for query in ("", "  ", "x" * 201):
            with self.assertRaises(Error):
                reports.history_list(self.s, query=query)
        with self.assertRaises(Error):
            reports.history_list(self.s, target="https://example.com/feed/update/urn:li:activity:123")
        with self.assertRaises(Error):
            reports.history_list(self.s, kinds=["x"] * 21)

    def test_cli_contract_uses_isolated_root(self):
        expected = self.row(kind="reactions", text="LIKE")
        script = Path(__file__).resolve().parents[1] / "scripts/smp"
        result = subprocess.run([sys.executable, str(script), "history", "list", "--root", str(self.root),
                                 "--kind", "reactions", "--kind", "comments", "--target", self.post,
                                 "--query", "like", "--limit", "1"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual([r["id"] for r in data["records"]], [expected])
        self.assertEqual(data["privacy"], "private_local_history")


if __name__ == "__main__":
    unittest.main()
