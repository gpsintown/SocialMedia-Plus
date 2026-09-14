"""Headline proposal behavior, using synthetic evidence and an isolated database."""
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("follower_classifier", ROOT / "scripts/classify-followers.py")
classifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classifier)

BUCKETS = ["analytics_peer", "data_engineering_peer", "analytics_leader", "recruiting_talent",
           "business_stakeholder", "marketing_analytics", "educator_community", "other_professional", "unclassified"]


class FollowerClassification(unittest.TestCase):
    def test_headline_roles_and_adjacent_noise(self):
        cases = {
            "Technical Recruiter | Hiring Data Engineers | Germany": "recruiting_talent",
            "Recruiterin IT Freelance": "recruiting_talent",
            "Personalberaterin IT | Recruitment": "recruiting_talent",
            "Personalreferentin | People and Culture": "recruiting_talent",
            "Recrutadora de Tecnologia": "recruiting_talent",
            "Senior Data Engineer | SQL | Python | AWS": "data_engineering_peer",
            "Lead Data Analyst | Ex-Amazon": "analytics_peer",
            "Head of Data Engineering": "analytics_leader",
            "Power BI Developer | Helping teams understand their numbers": "analytics_peer",
            "Marketing Analytics Manager": "marketing_analytics",
            "Software Engineer | Power BI | Analytics enthusiast": "other_professional",
            "Founder | Analytics enthusiast": "business_stakeholder",
            "Assistant Professor | Data Analytics": "educator_community",
            "Analytics Consultant\nFormer Software Engineer": "analytics_peer",
            "Vice President, Senior Data Engineer": "data_engineering_peer",
            "Office Manager at Vivid Healthcare - Recruitment Specialists": "business_stakeholder",
            "Microsoft Certified Senior Power BI Analyst, building dashboards with ETL/ELT": "analytics_peer",
            "Assistant Manager @ EY / Power BI / Tableau Developer / Data Analytics": "analytics_peer",
            "Manager at EY (Data & Analytics)": "analytics_leader",
            "Chartered Accountant": "business_stakeholder",
            "Manufacturing & Facilities Management Leader": "business_stakeholder",
            "Proprietary Trader | Options Strategist": "business_stakeholder",
            "Physiotherapist with expertise in pain management": "other_professional",
            "Advisor - Cyber Risk and Compliance": "other_professional",
            "Data Professional": "analytics_peer",
            "Principal Consultant | Data & AI": "analytics_peer",
            "Partner at EY | AI & Data": "analytics_peer",
            "Principal | The Iris School": "educator_community",
            "Data Analyst - Manufacturing": "analytics_peer",
            "Data Quality Analyst": "analytics_peer",
            "Technical Recruiter - Manufacturing": "recruiting_talent",
            "Data Science Analyst - Manufacturing Marketing": "marketing_analytics",
            "Software Engineer bei Personalberater Firma": "other_professional",
            "Counselor in Training (MHRS) & Project Manager (PMP)": "business_stakeholder",
            "Revit electrical training-power engineer at hospital": "other_professional",
            "Training Manager": "educator_community",
            "Power Programmer skilled in Product Management and Data Engineer": "other_professional",
            "Accounting Manager I Investment Evaluation I Financial Modelling I Risk Management": "business_stakeholder",
            "Audit Paraprofessional | Master’s in Professional Accounting": "other_professional",
            "Senior - Power BI Developer with EY GDS. (Assistant Manager (2))": "analytics_peer",
            "Senior Data Engineer (Associate Manager)": "data_engineering_peer",
            "Data Engineering Lead": "analytics_leader",
        }
        for text, bucket in cases.items():
            with self.subTest(headline=text):
                self.assertEqual(classifier.classify_headline(text)[0], bucket)

    def test_tools_aspirations_historical_roles_do_not_establish_current_role(self):
        cases = ["", "Power BI | SQL | Python", "Data Analytics", "Aspiring Data Analyst | Power BI",
                 "Former Data Scientist | Enjoying life", "Ex-Data Engineer | Open to work",
                 "We are hiring Data Engineers", "Helping data engineers find better jobs",
                 "Data enthusiast | Passionate about BI", "Certified Power BI Analyst",
                 "Student at Example University | SQL | Power BI", "Manager", "Germany | Australia",
                 "S&P Global | Fixed Income | MBA Finance(2023-2025)", "Ex. Trading and Operations at HRT",
                 "Director at AC Technology Group", "Manager at Data Recruitment Company",
                 "Power BI (PL-300: Power BI Data Analyst Associate)", "Former Principal Consultant | Data & AI",
                 "Consultant at Capgemini | Salesforce Certified MuleSoft Developer", "Non Recruitment",
                 "Marketing y Publicidad en Escola Técnica Girona", "PhD, MSc, BSc|Environmental Engineering",
                 "From a Pro to CEO", "Manager I Ex: CEO Example", "No longer Data Scientist", "Master’s in Professional Accounting",
                 "Analytics Engineering & BI | MS Fabric | Python | SQL | DP 203 Azure | DA 100 Power Bi | Snowflake",
                 "Data Engineering | Azure | SQL"]
        for text in cases:
            with self.subTest(headline=text):
                self.assertEqual(classifier.classify_headline(text)[0], "unclassified")

    def fixture(self, directory, rows, **metadata):
        root = Path(directory)
        (root / "config").mkdir()
        (root / "config/settings.json").write_text(json.dumps({"relationship_buckets": BUCKETS}))
        document = dict(rows=rows, source_url="https://www.linkedin.com/mynetwork/network-manager/people-follow/followers/",
                        observed_at="2026-09-13T12:00:00+00:00", expected_count=5, collection_complete=False)
        document.update(metadata)
        roster = root / "roster.json"
        roster.write_text(json.dumps(document))
        return root, roster, root / "out"

    def test_proposals_preserve_reviews_and_never_mutate_database(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [{"profile_url": "https://linkedin.com/in/reviewed/?trk=1", "name": "Reviewed Person", "headline": "Data Engineer"},
                    {"profile_url": "https://www.linkedin.com/in/new", "name": "New Person", "headline": "Personalberaterin"},
                    {"profile_url": "https://www.linkedin.com/in/unknown", "name": "Unknown", "headline": "Power BI"}]
            root, roster, output = self.fixture(directory, rows)
            (root / "data").mkdir()
            path = root / "data/socialmediaplus.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE relationships(id,profile_url,bucket,bucket_evidence,last_reviewed_at)")
            db.execute("INSERT INTO relationships VALUES(?,?,?,?,?)", ("person_existing", "https://www.linkedin.com/in/reviewed", "analytics_leader", "Existing source evidence", None))
            db.commit()
            db.close()
            original = path.read_bytes()
            packet = classifier.generate(root, roster, output)
            self.assertEqual(path.read_bytes(), original)
            kept, new, unknown = packet["proposals"]
            self.assertEqual(kept["proposed_bucket"], "analytics_leader")
            self.assertEqual(kept["evidence"], "Existing source evidence")
            self.assertFalse(kept["apply"])
            self.assertTrue(kept["preserve_existing_review"])
            self.assertTrue(new["apply"])
            self.assertEqual(new["observed_at"], "2026-09-13T12:00:00+00:00")
            self.assertIn("Personalberaterin", new["evidence"])
            self.assertFalse(unknown["apply"])
            self.assertEqual(packet["summary"]["proposed_updates"], 1)
            self.assertEqual(packet["summary"]["missing_from_expected_count"], 2)
            self.assertFalse(packet["source"]["collection_complete"])
            self.assertFalse(packet["summary"]["full_inventory_accounted_for"])
            self.assertIsNone(new["geography"])

    def test_duplicates_invalid_sources_and_times_are_not_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [{"profile_url": "https://www.linkedin.com/in/one", "name": "One", "headline": "Data Analyst"},
                    {"profile_url": "https://linkedin.com/in/one/", "name": "One Again", "headline": "Data Analyst"},
                    {"profile_url": "https://example.test/in/two", "name": "Not LinkedIn", "headline": "Data Analyst"},
                    {"profile_url": "https://www.linkedin.com/in/three", "name": "Bad time", "headline": "Data Analyst", "observed_at": "yesterday"},
                    {"profile_url": "https://www.linkedin.com/in/four", "name": "Bad source", "headline": "Data Analyst", "source_url": "https://example.test/"}]
            root, roster, output = self.fixture(directory, rows)
            packet = classifier.generate(root, roster, output)
            self.assertEqual([p["apply"] for p in packet["proposals"]], [True, False, False, False, False])
            self.assertEqual(packet["summary"]["duplicate_profile_rows"], 1)
            self.assertEqual(packet["summary"]["invalid_or_missing_evidence_rows"], 3)

    def test_private_outputs_redact_email_and_escape_csv_formulas(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [{"profile_url": "https://www.linkedin.com/in/new", "name": "=FORMULA()", "headline": "Data Analyst | person@example.test | +91 98765 43210"}]
            root, roster, output = self.fixture(directory, rows)
            classifier.generate(root, roster, output)
            for path in output.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("person@example.test", path.read_text())
                self.assertNotIn("98765", path.read_text())
            self.assertIn("'=FORMULA()", (output / "role-proposals.csv").read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)

    def test_replay_keeps_previously_reviewed_unclassified_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root, roster, output = self.fixture(directory, [{"profile_url": "https://www.linkedin.com/in/one", "name": "One", "headline": "Data Analyst"}])
            reviews = root / "reviews.json"
            reviews.write_text(json.dumps({"reviews": [{"id": "reviewed", "profile_url": "https://www.linkedin.com/in/one", "bucket": "unclassified", "bucket_evidence": "Conflicting current role evidence", "last_reviewed_at": "2026-09-12T12:00:00Z"}]}))
            packet = classifier.generate(root, roster, output, reviews=reviews)
            self.assertFalse(packet["proposals"][0]["apply"])
            self.assertEqual(packet["proposals"][0]["proposed_bucket"], "unclassified")

    def test_invalid_input_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, roster, output = self.fixture(directory, [], collection_complete="yes")
            with self.assertRaisesRegex(ValueError, "collection_complete"):
                classifier.generate(root, roster, output)

    def test_exhausted_visible_list_is_not_full_identity_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root, roster, output = self.fixture(directory, [{"profile_url": "https://www.linkedin.com/in/one", "name": "One", "headline": "Data Analyst"}], collection_complete=True)
            packet = classifier.generate(root, roster, output)
            self.assertTrue(packet["summary"]["source_collection_complete"])
            self.assertFalse(packet["summary"]["identity_count_matches_expected"])
            self.assertFalse(packet["summary"]["full_inventory_accounted_for"])
            self.assertEqual(packet["summary"]["missing_from_expected_count"], 4)


if __name__ == "__main__":
    unittest.main()
