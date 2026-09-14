#!/usr/bin/env python3
"""Propose private role buckets from Connections.csv; never mutate SQLite.

Only the selected Connections.csv member is opened. Email columns are discarded.
Run with --self-test for the bounded classifier contract, or --help for usage.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from socialmediaplus.store import Error, canonical_url

RULE_VERSION = "1.2.0"
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def clean(value):
    return EMAIL.sub("[email redacted]", str(value or "").strip())


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def hit(pattern, text):
    return bool(re.search(pattern, text))


def classify(position):
    """Professional role only; confidence describes title fit, never interest."""
    title = normalized(position)
    if not title:
        return "unclassified", "low", "missing_position", "No exported position; review the current profile when relevant."
    if hit(r"\b(aspiring|seeking|looking for|open to work|unemployed)\b", title):
        return "unclassified", "low", "non_role_or_aspiration", "A target or availability statement does not establish a current role."
    if hit(r"\b(recruit\w*|talent acquisition|talent attract\w*|talent sourc\w*|talent souc\w*|talent scout|staffing|hiring|candidate manager)\b", title):
        return "recruiting_talent", "high", "explicit_recruitment", "Explicit recruiting or talent acquisition responsibility; relevance to analytics hiring still needs review."
    analytics = hit(r"\banalytics?\b|\bdata (analyst|science|scientist|visuali[sz]ation)\b|\bbusiness intelligence\b|\bbi\b|\bpower\s*bi\b|\btableau\b|\bdax\b|\bquantitative (analyst|researcher|analytics)\b|\bstatistician\b|\bstatistical (analyst|model\w*)\b|\bmetric\w* and visuali[sz]ation\b|\breporting (analyst|developer|engineer)\b", title)
    engineering = hit(r"\bdata (engineer\w*|architect\w*|warehouse\w*|platform\w*|pipeline\w*)\b|\bdata solutions architect\b|\bdata\s*(?:&|and)\s*ai (engineer\w*|architect\w*)\b|\banalytics engineer\w*\b|\b(etl|elt|dataops)\b|\bdatabase (engineer\w*|architect\w*|developer\w*|administrator)\b|\bsql developer\b|\bengenheiro de dados\b", title)
    data_domain = analytics or engineering or hit(r"\bdata\b", title)
    if analytics and hit(r"\b(marketing|customer analytics|web analytics|campaign|attribution)\b", title):
        return "marketing_analytics", "high", "explicit_marketing_analytics", "Marketing/customer context and explicit analytics work are both present."
    if hit(r"\bmedia measurement\b|\bprogrammatic analyst\b", title):
        return "marketing_analytics", "medium", "explicit_media_measurement", "Explicit media measurement or programmatic analysis role; specific tools and measurement responsibilities need review."
    if hit(r"\b(professor|lecturer|teacher|faculty|instructor|trainer|tutor|teaching|postdoctoral|educator|dean|visiting fellow|learning and development|learning & development|learning experience|training)\b|\bl&d\b", title):
        return "educator_community", "high", "explicit_education", "Explicit teaching, training, educational or academic research role; subject relevance needs review."
    leadership = hit(r"\b(manager|director|head|leader|chief|vp|avp|dvp|vice president|supervisor)\b", title)
    rank = hit(r"\b(vp|avp|dvp|vice president)\b", title)
    practitioner = hit(r"\b(engineer\w*|scientist|consultant|specialist|analyst|architect\w*)\b", title)
    explicit_responsibility = hit(r"\b(manager|director|head|leader|chief|supervisor)\b", title)
    # Some employers use VP/AVP/DVP as practitioner grades. An explicit
    # engineer/scientist/etc. role is stronger evidence than the rank alone.
    if data_domain and rank and practitioner and not explicit_responsibility:
        peer = "data_engineering_peer" if engineering else "analytics_peer"
        return peer, "medium", "rank_with_explicit_practitioner_role", "Explicit practitioner role with an ambiguous VP/AVP/DVP rank; management remit is unverified. Classify by the work named, not assumed seniority."
    # A 'Lead Data Analyst/Engineer' may be an individual contributor. Do not
    # promote it to a leadership bucket merely because it starts with Lead.
    domain_lead = hit(r"\b(analytics|data|data governance|data strategy|data ops|data solutions|data science|data engineering) lead\b|\blead\s*[-:|]\s*data\b", title)
    if data_domain and (leadership or domain_lead):
        return "analytics_leader", "medium", "explicit_data_domain_leadership", "Title contains leadership or seniority wording in a data/analytics domain; management remit, team size and purchasing authority are unverified."
    if engineering:
        return "data_engineering_peer", "high", "explicit_data_engineering", "Explicit data engineering, architecture, warehousing, pipeline or database development role. Lead/seniority wording does not establish a management remit."
    if analytics:
        return "analytics_peer", "high", "explicit_analytics", "Explicit analytics, BI, data science, visualization or quantitative analysis role. Lead/seniority wording does not establish a management remit."
    if hit(r"\b(human resources|human capital|hr|hrbp|hris|chro|chief people officer|people ops|people operations|people and talent|people and culture|people & culture|head of people|talent team|talent management|talent operations|talent advisor|talent delivery|talent service|talent program|talent resource|talent mobility|talent strategist|talent builder)\b", title):
        return "recruiting_talent", "medium", "explicit_hr_or_talent", "Explicit HR/people/talent remit; direct recruiting responsibility is not established."
    if hit(r"\bdata (consultant|steward|quality|coordinator|specialist|strategist|governance|reviewer)\b|\bdatabase coordinator\b|\bdata\s*&\s*ai\b|\bai\s*&\s*data\b", title):
        return "analytics_peer", "medium", "adjacent_explicit_data_role", "Explicit data role relevant to analytics discussions; technical specialization needs review."
    if hit(r"\binsights? (analyst|lead)\b|\bindex quants\b", title):
        return "analytics_peer", "medium", "explicit_insights_role", "Explicit insights/quantitative role; data tooling and the type of analysis are unverified."
    if hit(r"\b(founder|co-founder|cofounder|ceo|coo|cfo|chief executive officer|chief operating officer|chief operations officer|chief financial officer|chief business officer|managing director|managing partner|proprietor|owner|entrepreneur)\b", title):
        return "business_stakeholder", "medium", "explicit_business_ownership", "Explicit business ownership or executive role; no claim that this person commissions analytics."
    if hit(r"\b(business (analyst|development|operations|support|manager|process|strategy|continuity)|account (manager|director|executive)|sales|marketing|advertising|programmatic|paid search|paid media|seo|sem|google ads|brand|media (strategy|strategist|buyer|manager|director)|social media|product (manager|owner|management|analyst|lead|growth|executive)|project (manager|management|delivery)|program manager|operations|ops (director|lead)|finance|financial|treasur\w*|controller|supply (chain|planning)|customer (success|service|support|experience|solutions)|client services|commerce|ecommerce|retail|commercial|growth|strategy|logistics|inventory)\b", title):
        return "business_stakeholder", "medium", "explicit_business_function", "Explicit business/product/operational function; reporting ownership and buying intent remain unverified."
    if hit(r"\b(software|engineer\w*|developer\w*|architect\w*|scientist|research\w*|designer|design|creative|lawyer|law|legal|attorney|solicitor|doctor|physician|nurse|perfusionist|psycholog\w*|psychotherapist|chemist|microbiologist|biotechnologist|bioinformatician|tax|audit\w*|cybersecurity|security|technology|technical|tech|technician|it|devops|cloud|sap|application support|system analyst|advisory|risk|cto|cio|chief technology officer|consulting|coach|counsellor|journalist|editor|editorial|writer|content|photographer|insurance|real estate|property|surveyor|migration (agent|consultant)|immigration consultant)\b", title):
        return "other_professional", "medium", "other_explicit_profession", "An explicit professional field is present; the title does not establish analytics/data engineering specialization."
    if hit(r"\b(manager|director|associate|partner|consultant|analyst|president|vice president|executive|specialist|lead|senior|supervisor)\b", title):
        return "unclassified", "low", "generic_role_without_domain", "Seniority/title alone does not establish professional relevance or analytics leadership."
    return "unclassified", "low", "insufficient_role_signal", "No conservative role rule matched; inspect current professional context if this connection becomes relevant."


def read_connections(archive):
    with ZipFile(archive) as zipped:
        matches = [i for i in zipped.infolist() if Path(i.filename).name.casefold() == "connections.csv"]
        if len(matches) != 1 or matches[0].file_size > 25_000_000:
            raise ValueError("Expected exactly one Connections.csv member smaller than 25 MB.")
        raw = zipped.read(matches[0])
        member = matches[0].filename
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header = next((i for i, r in enumerate(rows[:60]) if "Position" in r and "URL" in r), None)
    if header is None:
        raise ValueError("Connections.csv header was not recognized.")
    selected = []
    for row_number, row in enumerate(rows[header + 1:], header + 2):
        if not any(str(v).strip() for v in row):
            continue
        source = dict(zip(rows[header], row))
        # Whitelist fields. Never copy the email field or arbitrary archive data.
        selected.append({"row_number": row_number, "name": clean(" ".join(x for x in (source.get("First Name"), source.get("Last Name")) if x)),
                         "company": clean(source.get("Company")), "position": clean(source.get("Position")), "url": clean(source.get("URL"))})
    return selected, {"archive": str(archive), "member": member, "member_sha256": hashlib.sha256(raw).hexdigest()}


def existing_reviews(root):
    path = root / "data/socialmediaplus.sqlite3"
    if not path.exists():
        return {}
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return {r["profile_url"]: dict(r) for r in db.execute("SELECT id,profile_url,bucket,bucket_evidence,last_reviewed_at FROM relationships")}
    finally:
        db.close()


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        temporary.chmod(0o600)
        stream.write(text)
    temporary.replace(path)


def generate(root, archive, output, reviews=None):
    config = json.loads((root / "config/settings.json").read_text(encoding="utf-8"))
    allowed = set(config["relationship_buckets"])
    source_rows, source = read_connections(archive)
    if reviews:
        snapshot = json.loads(reviews.read_text(encoding="utf-8"))
        existing = {r["profile_url"]: r for r in snapshot["reviews"]}
    else:
        existing = existing_reviews(root)
    snapshot = {"reviews": [{k: clean(v) if isinstance(v, str) else v for k, v in r.items()}
                            for r in sorted(existing.values(), key=lambda r: r["profile_url"])
                            if r["bucket"] != "unclassified" or r["bucket_evidence"] or r["last_reviewed_at"]]}
    snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    private_write(output / "preserved-reviews.json", snapshot_text)
    source["review_snapshot_sha256"] = hashlib.sha256(snapshot_text.encode()).hexdigest()
    source["configured_buckets"] = sorted(allowed)
    proposals, seen = [], set()
    for row in source_rows:
        invalid_reason = None
        try:
            url = canonical_url(row["url"], profile=True)
        except (Error, AttributeError):
            url = None
            invalid_reason = "missing_profile_url" if not row["url"] else "invalid_profile_url"
        duplicate = url in seen if url else False
        if url:
            seen.add(url)
        record = existing.get(url, {})
        preserve = bool(record and (record["bucket"] != "unclassified" or record["bucket_evidence"] or record["last_reviewed_at"]))
        bucket, confidence, rule, review = classify(row["position"])
        suggested = bucket
        evidence = "Provisional exported role classification. Position: " + (row["position"] or "[missing]") + "; Company: " + (row["company"] or "[missing]") + "; rule: " + rule + "; source: Connections.csv row " + str(row["row_number"]) + "; classifier " + RULE_VERSION + "."
        if preserve:
            bucket, confidence, rule = record["bucket"], "preserved", "preserve_existing_review"
            evidence = clean(record["bucket_evidence"] or "Existing manual review retained.")
            review = "Existing reviewed bucket retained; title-only suggestion was " + suggested + "."
        if bucket not in allowed:
            raise ValueError("Classifier generated a bucket absent from configuration: " + bucket)
        proposals.append({"row_number": row["row_number"], "profile_url": url, "name": row["name"], "company": row["company"], "position": row["position"],
                          "proposed_bucket": bucket, "confidence": confidence, "evidence": evidence, "rule": rule,
                          "apply": bool(url and not duplicate and not preserve and bucket != "unclassified"),
                          "existing_relationship_id": record.get("id"), "preserve_existing_review": preserve,
                          "review_reason": review, "unresolved_reason": invalid_reason, "duplicate_profile_url": duplicate,
                          "geography": None, "geography_inference": "not_performed"})
    summary = {"source_rows": len(proposals), "unique_valid_profile_urls": len(seen),
               "missing_profile_urls": sum(p["unresolved_reason"] == "missing_profile_url" for p in proposals),
               "invalid_profile_urls": sum(p["unresolved_reason"] == "invalid_profile_url" for p in proposals),
               "duplicate_profile_rows": sum(p["duplicate_profile_url"] for p in proposals),
               "preserved_reviewed_rows": sum(p["preserve_existing_review"] for p in proposals),
               "proposed_updates": sum(p["apply"] for p in proposals),
               "bucket_distribution_all_rows": dict(sorted(collections.Counter(p["proposed_bucket"] for p in proposals).items())),
               "proposed_update_buckets": dict(sorted(collections.Counter(p["proposed_bucket"] for p in proposals if p["apply"]).items())),
               "confidence_distribution": dict(sorted(collections.Counter(p["confidence"] for p in proposals).items())),
               "rules": dict(sorted(collections.Counter(p["rule"] for p in proposals).items()))}
    packet = {"schema_version": 1, "classifier_version": RULE_VERSION, "classifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": source,
              "authority": "proposal_only_no_database_mutation", "summary": summary,
              "interpretation": "apply=true is eligibility proposed for review, not approval. Run the core relationship apply command only after reviewing this packet. Confidence is semantic role fit, not verified employment, interest, influence or buying intent.",
              "proposals": proposals}
    private_write(output / "role-proposals.json", json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    columns = list(proposals[0]) if proposals else []
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in proposals:
        writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
    private_write(output / "role-proposals.csv", stream.getvalue())
    private_write(output / "role-summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    # Titles only: these representative examples permit rule review without
    # copying names, companies or email addresses into an extra narrative file.
    examples = {}
    for p in proposals:
        items = examples.setdefault(p["rule"], [])
        if p["position"] not in items and len(items) < 12:
            items.append(p["position"])
    private_write(output / "role-rule-examples.json", json.dumps(examples, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"proposal_json": str(output / "role-proposals.json"), "proposal_csv": str(output / "role-proposals.csv"), "summary": summary}, ensure_ascii=False, indent=2))


def self_test():
    cases = {"Manager": "unclassified", "Founder": "business_stakeholder", "Director": "unclassified",
             "Senior Software Engineer": "other_professional", "Full Stack Developer": "other_professional",
             "Technical Recruiter - Data Engineering": "recruiting_talent", "HR Analytics Consultant": "analytics_peer",
             "Associate Manager - Business Intelligence": "analytics_leader", "Lead Data Analyst": "analytics_peer",
             "Lead Data Engineer": "data_engineering_peer", "Senior Data Architect/Developer": "data_engineering_peer",
             "Senior Manager - Data Engineering": "analytics_leader", "Digital Marketing Manager": "business_stakeholder",
             "Data Science Analyst II (Performance Marketing)": "marketing_analytics", "Assistant Professor": "educator_community",
             "Chief Data Officer": "analytics_leader", "Data & AI Architect": "data_engineering_peer",
             "Data & AI Engineer": "data_engineering_peer", "Data Solutions Architect": "data_engineering_peer",
             "Education & Government Solutions - Owner": "business_stakeholder", "Senior Content Writer": "other_professional",
             "Cybersecurity Consultant": "other_professional", "People & Culture Lead": "recruiting_talent",
             "Metric and Visualisation Lead": "analytics_peer", "Media Measurement Specialist": "marketing_analytics",
             "Consultant Senior Engineer 1 (AVP) - Analytics Engineering": "data_engineering_peer",
             "DVP / Data Scientist 3": "analytics_peer", "Vice President, Senior Data Engineer": "data_engineering_peer",
             "Lead Securities Quantitative Analytics Specialist(Vice President)": "analytics_peer",
             "AVP - Analytics Consultant": "analytics_peer", "Vice President, Analytics & Data": "analytics_leader",
             "Associate Vice President - AI & Data Science": "analytics_leader",
             "VP - Manager, Data Engineering": "analytics_leader",
             "": "unclassified", "Aspiring Data Analyst": "unclassified", "Recruiterin IT Freelance": "recruiting_talent"}
    for title, expected in cases.items():
        assert classify(title)[0] == expected, (title, classify(title), expected)
    for title in ("Lead Data Analyst", "Lead Data Engineer", "Analytics Lead", "AVP - Analytics Consultant"):
        assert "management remit" in classify(title)[3].lower(), title
    assert "@" not in clean("Contact person@example.test")
    print(json.dumps({"classifier_contract_cases": len(cases), "email_redaction": "pass", "status": "pass"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path, help="Path to an imported LinkedIn archive (required except --self-test)")
    parser.add_argument("--output", type=Path, help="Private output directory (defaults below --root/network)")
    parser.add_argument("--reviews", type=Path, help="Replay against a prior preserved-reviews.json instead of current database reviews.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        if not args.archive:
            parser.error("--archive is required")
        args.output = args.output or args.root / "network/classification"
        generate(args.root.expanduser().resolve(), args.archive.expanduser().resolve(), args.output.expanduser().resolve(), args.reviews.expanduser().resolve() if args.reviews else None)


if __name__ == "__main__":
    main()
