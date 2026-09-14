import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from socialmediaplus import imports
from socialmediaplus.store import Error, Store


class Archive2026Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s = Store(self.root, create=True)

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def file(self, name, content):
        path = self.root / name
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def archive(self, files):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return self.file("export.zip", output.getvalue())

    def test_numbered_allowlist_is_anchored_and_private_categories_ignored(self):
        for name, expected in [("Shares_184702752", "shares"), ("comments_12", "comments"),
                               ("InstantReposts_12", "instant_reposts"), ("Reactions", "reactions")]:
            self.assertEqual(imports.archive_section(name), expected)
        for name in ("Messages_Shares_12", "Shares_12_backup", "MyComments", "Shares_private", "Messages_12"):
            self.assertIsNone(imports.archive_section(name))
        path = self.archive({
            "Shares_12.csv": "Date,ShareLink,ShareCommentary\n2026-09-12,https://www.linkedin.com/posts/example,Observed content\n",
            "Messages_12.csv": "From,Body\nPrivate,SECRET MESSAGE\n",
            "Shares_12_backup.csv": "Date,ShareLink,ShareCommentary\n2026-09-12,https://example.test,SECRET BACKUP\n",
        })
        summary = imports.import_file(self.s, "archive", path)["import"]["summary"]
        self.assertEqual(summary["selected_files"], ["Shares_12.csv"])
        self.assertEqual(len(summary["ignored_files"]), 2)
        self.assertNotIn("SECRET", json.dumps(self.s.all("SELECT * FROM history")))
        self.assertEqual(self.s.all("SELECT * FROM relationships"), [])

    def test_share_media_rows_merge_without_losing_assets_or_inventing_posts(self):
        path = self.file("Shares_12.csv", "Date,ShareLink,ShareCommentary,MediaUrl\n"
                         "2026-09-12 09:00:00,https://www.linkedin.com/posts/example,One post,https://example.test/one.jpg\n"
                         "2026-09-12 09:00:00,https://www.linkedin.com/posts/example,One post,https://example.test/two.jpg\n")
        summary = imports.import_file(self.s, "archive", path)["import"]["summary"]
        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["merged_share_rows"], 1)
        row = self.s.one("SELECT * FROM history")
        self.assertIsNone(row["occurred_at"])
        raw = json.loads(row["raw_json"])
        self.assertEqual(raw["_export"]["date_status"], "zone_unspecified")
        self.assertIsNone(raw["_export"]["time_zone"])
        self.assertEqual(len(raw["_export"]["source_rows"]), 2)
        self.assertEqual(raw["_export"]["media_urls"], ["https://example.test/one.jpg", "https://example.test/two.jpg"])
        self.assertTrue(imports.import_file(self.s, "archive", path)["existing"])

    def test_numbered_standalone_reposts_and_same_target_comments_are_distinct(self):
        target = "https://www.linkedin.com/feed/update/urn%3Ali%3Aactivity%3A123"
        comments = self.file("Comments_12.csv", f"Date,Link,Message\n2026-09-12 09:00:00,{target},First comment\n2026-09-12 09:00:00,{target},Second comment\n")
        imports.import_file(self.s, "archive", comments)
        repost = self.file("InstantReposts_12.csv", f"Date,Link\n2026-09-12 09:00:00,{target}\n")
        imports.import_file(self.s, "archive", repost)
        self.assertEqual(self.s.one("SELECT COUNT(*) n FROM history WHERE kind='comments'")["n"], 2)
        self.assertEqual(self.s.one("SELECT COUNT(*) n FROM history WHERE kind='instant_reposts'")["n"], 1)
        self.assertEqual(self.s.all("SELECT * FROM relationships"), [])
        same = self.archive({"Comments_12.csv": comments.read_text()})
        summary = imports.import_file(self.s, "archive", same)["import"]["summary"]
        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["updated"], 2)

    def test_malformed_multiline_comment_preserves_every_word_and_provenance(self):
        text = ('Date,Link,Message\n'
                '2026-09-12 09:00:00,https://www.linkedin.com/posts/a,"Before "inner quotes", detail.\n\nFinal line."\n'
                '2026-09-11 09:00:00,https://www.linkedin.com/posts/b,A separate comment\n')
        path = self.file("Comments_12.csv", text)
        summary = imports.import_file(self.s, "archive", path)["import"]["summary"]
        self.assertEqual(summary["inserted"], 2)
        self.assertEqual(summary["recovered_comments"], 1)
        row = self.s.one("SELECT * FROM history WHERE target_url='https://www.linkedin.com/posts/a'")
        self.assertEqual(row["text"], 'Before "inner quotes", detail.\n\nFinal line.')
        raw = json.loads(row["raw_json"])
        self.assertEqual(raw["_export"]["parsing"], "final_column_boundary_recovery")
        self.assertIn('"Before "inner quotes", detail.', raw["_export"]["raw_block"])
        self.assertEqual(raw["_export"]["line_start"], 2)
        self.assertEqual(raw["_export"]["line_end"], 4)
        self.assertIsNone(row["occurred_at"])

    def test_valid_multiline_payload_with_date_url_line_is_not_split(self):
        text = ('Date,Link,Message\n'
                '2026-09-12 09:00:00,https://www.linkedin.com/posts/a,"A quoted example:\n'
                '2026-09-11 09:00:00,https://www.linkedin.com/posts/b,example text\nEnd."\n')
        summary = imports.import_file(self.s, "archive", self.file("Comments.csv", text))["import"]["summary"]
        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["recovered_comments"], 0)
        self.assertIn("example text\nEnd.", self.s.one("SELECT text FROM history")["text"])

    def test_ambiguous_malformed_record_is_quarantined_including_raw_source(self):
        text = ('Date,Link,Message\n'
                '2026-09-12 09:00:00,https://www.linkedin.com/posts/a,"Broken "quote\n'
                '2026-09-11 09:00:00,https://www.linkedin.com/posts/b,possibly embedded text\n')
        result = imports.import_file(self.s, "archive", self.file("Comments_12.csv", text))["import"]
        self.assertEqual(result["summary"]["inserted"], 0)
        self.assertEqual(result["summary"]["quarantined_records"], 2)
        self.assertEqual(len(result["summary"]["quarantine"]), 1)
        self.assertEqual(self.s.all("SELECT * FROM history"), [])
        self.assertEqual((self.root / result["stored_path"]).read_text(), text)

    def test_only_explicit_export_offset_becomes_an_instant(self):
        path = self.file("Reactions_12.csv", "Date,Type,Link\n2026-09-12T09:00:00+02:00,LIKE,https://www.linkedin.com/posts/a\n")
        imports.import_file(self.s, "archive", path)
        row = self.s.one("SELECT * FROM history")
        self.assertEqual(row["occurred_at"], "2026-09-12T07:00:00+00:00")
        self.assertEqual(json.loads(row["raw_json"])["_export"]["date_status"], "explicit_offset")


if __name__ == "__main__":
    unittest.main()
