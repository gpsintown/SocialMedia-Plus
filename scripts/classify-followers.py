#!/usr/bin/env python3
"""Propose private role buckets from visible LinkedIn follower cards, never write SQLite.

Headlines are self-descriptions, not verified current employment. Review the
resulting packet before using `smp relationship apply`; import the roster first.
"""
import argparse
import collections
import csv
import hashlib
import importlib.util
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from socialmediaplus.store import Error, canonical_url, timestamp

_spec = importlib.util.spec_from_file_location("smp_connection_classifier", ROOT / "scripts/classify-network.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

RULE_VERSION = "1.2.0"
MAX_ROSTER_BYTES = 25_000_000
MAX_ROWS = 25_000
# A headline can include a wish, a past employer, or a list of tools. None of
# those alone establishes the work the person presently describes themselves doing.
ASPIRATION = re.compile(r"\b(aspiring|seeking|looking for|open to (?:work|opportunit)|unemployed|future|wannabe|student|undergraduate|undergrad|graduate student|undergraduation|pursuing|studying|learner|fresher)\b", re.I)
HISTORICAL = re.compile(r"^(?:formerly\b|former\b|previously\b|past\b|no longer\b|ex[-.:\s]|retired\b)", re.I)
DEGREE_OPENING = re.compile(r"^(?:mba|bba|bca|mca|bcom|mcom|b\.?\s?tech|m\.?\s?tech|bsc|msc|b\.?eng|m\.?eng|bachelor\w*|master(?:['’]s|s)? (?:in|of)|master['’]s|masters\b|pgdm|ph\.?d)\b", re.I)
NON_ROLE_OPENING = re.compile(r"^(?:i\s+)?(?:help(?:ing)?|connect(?:ing)?|passionate|interested|enthusiast|learning|exploring|certified|certification|certificates?|trained|training in|skills?\s*[:\-]|we(?:'re| are)? hiring|hiring\b|#hiring|available for)\b", re.I)
CREDENTIAL_OPENING = re.compile(r"^(?:salesforce|ace|aws|oracle|microsoft)\s+certified\s+(?!senior\b|lead\b|principal\b)", re.I)
NON_ROLE_STATEMENT = re.compile(r"^(?:from\s+.+\s+to\s+|(?:non|not(?: a)?|no)\s+recruit\w*)", re.I)
ROLE = re.compile(r"\b(?:analyst|analytics|engineer\w*|architect\w*|scientist|developer\w*|administrator|specialist|consultant|manager|director|head|leader|chief|officer|vp|avp|dvp|vice president|supervisor|lead|statistician|researcher|professional|coordinator|steward|reviewer|strategist|professor|lecturer|teacher|faculty|instructor|trainer|tutor|educator|dean|recruit\w*|talent acquisition|talent (?:sourc\w*|scout|advisor)|human resources|hr|hrbp|people operations|founder|cofounder|owner|entrepreneur|ceo|coo|cfo|cto|cio|proprietor|partner|executive|sales|marketing|operations|finance|accountant|controller|lawyer|attorney|solicitor|doctor|physician|nurse|designer|coach|counsellor|journalist|editor|writer|photographer|personalberater\w*|personalreferent\w*|personalvermittler\w*|recruteur\w*|recruteuse\w*|recrutador\w*|selecci[oó]n de personal)\b", re.I)
GERMAN_RECRUITING = re.compile(r"\b(?:personalberater\w*|personalvermittler\w*|recruteur\w*|recruteuse\w*|recrutador\w*|selecci[oó]n de personal)\b", re.I)
GERMAN_HR = re.compile(r"\b(?:personalreferent\w*|personalmanagement|personalleiter\w*|personalentwicklung)\b", re.I)
PHONE = re.compile(r"(?<!\w)\+?\d[\d .()-]{7,}\d(?!\w)")


def clean_text(value):
    """Discard contact details from derived prose without changing profile IDs."""
    return PHONE.sub(lambda match: "[phone redacted]" if 10 <= sum(c.isdigit() for c in match[0]) <= 15 else match[0], base.clean(value))


def role_text(segment):
    segment = re.sub(r"\([^()]*\b(?:pl-?300|dp-?100|certifications?|certificates?)\b[^()]*\)", "", segment).strip()
    segment = re.split(r"\b(?:skilled|proficient) in\b", segment, maxsplit=1)[0].strip()
    # Employer names sometimes include 'Data', 'Technology' or 'Recruitment'.
    # Those words cannot convert an otherwise generic office/title role.
    employer = re.search(r"\s+(?:(?:at|bei|chez)\s+|@\s*)", segment)
    if employer:
        suffix = segment[employer.end():]
        segment = segment[:employer.start()]
        # Explicit parenthetical role scope remains useful ('Manager at EY
        # (Data & Analytics)'). An employer's name alone never supplies scope.
        domains = [value for value in re.findall(r"\(([^()]+)\)", suffix)
                   if re.search(r"\b(?:data|analytics|business intelligence|power\s*bi)\b", value)]
        if domains:
            segment += " (" + "; ".join(domains) + ")"
    # A long marketing sentence can mention ETL or AI after the actual role.
    # Keep a clear initial role, but retain rank+practitioner forms such as
    # 'Vice President, Senior Data Engineer', where rank alone is ambiguous.
    initial = segment.split(",", 1)[0].strip()
    if initial != segment and base.classify(initial)[0] != "unclassified":
        segment = initial
    grade = re.search(r"\(\s*(?:assistant|associate)\s+manager\b.*\)\s*$", segment)
    if grade and base.classify(segment[:grade.start()].strip())[0] in ("analytics_peer", "data_engineering_peer", "marketing_analytics"):
        # A practitioner title plus a parenthetical company grade does not
        # establish a team-management remit. Keep that rank in raw evidence.
        segment = segment[:grade.start()].strip()
    return segment


def headline_segments(headline):
    text = clean_text(headline)
    return [base.normalized(part).strip(" \t-–—:") for part in re.split(r"[|•·;/\n]+|\s+[Il]\s+", text) if part.strip()]


def excluded_segment(segment):
    return any(pattern.search(segment) for pattern in (ASPIRATION, HISTORICAL, NON_ROLE_OPENING, DEGREE_OPENING, CREDENTIAL_OPENING, NON_ROLE_STATEMENT))


def classify_headline(headline):
    """Reuse the coarse title taxonomy only after isolating actual role claims."""
    segments = headline_segments(headline)
    if not segments:
        return "unclassified", "low", "missing_headline", "No visible professional headline was collected.", []
    eligible, skipped = [], []
    degree_context = any(DEGREE_OPENING.search(part) for part in segments)
    for segment in segments:
        if excluded_segment(segment):
            skipped.append(segment)
            continue
        segment = role_text(segment)
        explicit_job = re.search(r"\b(?:analyst|engineer|architect|scientist|developer|programmer|manager|director|head|officer|professor|teacher|trainer|lecturer|recruiter|consultant|specialist|founder|owner|ceo|chief|professional)\b", segment)
        if degree_context and re.search(r"\bengineering\b", segment) and not explicit_job:
            skipped.append(segment)
            continue
        if re.search(r"\b(?:school|college|university|escola|universidad|universidade)\b", segment) and not explicit_job:
            skipped.append(segment)
            continue
        # Tool lists, field names and self-praise do not establish a role.
        extra_role = re.search(r"\b(?:accountant|trader|physiotherapist|presenter|actor|artist|advisor|coaching|management|expert|programmer|paraprofessional)\b", segment)
        if not (ROLE.search(segment) or GERMAN_HR.search(segment) or extra_role):
            skipped.append(segment)
            continue
        # "Data analytics enthusiast" is not an analyst position. Keep this
        # condition local to the segment so a separate real role can still count.
        if re.search(r"\b(?:enthusiast|enthusiastic|certified|certification|certificates?|learning|course|bootcamp)\b", segment) and not re.search(r"\b(?:at|@)\b|\b(?:analyst|engineer\w*|consultant|manager|scientist|developer\w*|architect\w*|recruit\w*)\b", segment):
            skipped.append(segment)
            continue
        classification_title = segment
        if re.search(r"\btraining\b", segment) and not re.search(r"\b(?:teacher|trainer|professor|educator|instructor|lecturer|tutor)\b|\btraining (?:manager|lead|director|coordinator|specialist|consultant)\b", segment):
            classification_title = re.sub(r"\b(?:in )?training\b", "", segment)
        result = base.classify(classification_title)
        # Preserve explicit title taxonomy precedence. A manufacturing sector,
        # quality qualifier or profession being recruited must not override
        # 'Data Analyst' or 'Recruiter' in the same actual role statement.
        if GERMAN_RECRUITING.search(segment):
            result = ("recruiting_talent", "high", "explicit_multilingual_recruiting", "An explicit recruiting/advisory title is visible; hiring sector, authority and current activity remain unverified.")
        elif GERMAN_HR.search(segment) and result[0] not in ("analytics_peer", "analytics_leader", "data_engineering_peer", "marketing_analytics"):
            result = ("recruiting_talent", "medium", "explicit_multilingual_hr", "An explicit HR/personnel title is visible; direct recruiting responsibility is not established.")
        elif result[0] != "unclassified":
            pass
        elif re.search(r"\boffice (?:manager|administrator)\b", segment):
            result = ("business_stakeholder", "medium", "explicit_office_operations", "An explicit office management/administration role is visible; an employer's recruitment business does not establish that this person recruits.")
        elif re.search(r"\b(?:accountant|accounting|trader|options strategist|manufacturing|facilities management|maintenance manager|segment development manager|marketplace director|client partner|account management|inventory management|business analysis|pmo|paid media (?:planning|strategy)|ads expert)\b", segment):
            result = ("business_stakeholder", "medium", "explicit_business_role_headline", "An explicit accounting, trading, business analysis, commercial or operations function is visible; reporting ownership, buying intent and hiring responsibility remain unverified.")
        elif re.search(r"\b(?:quality analyst|(?:cyber )?risk and compliance|structural consultant|physiotherapist|leadership coaching|radio presenter|voice actor|dubbing artist|automation (?:strategist|leader)|copilot activation leader|programmer)\b", segment):
            result = ("other_professional", "medium", "explicit_other_role_headline", "A specific professional role or advisory domain is visible; analytics specialization is not established.")
        elif re.search(r"\bdata professional\b", segment):
            result = ("analytics_peer", "medium", "explicit_data_professional", "An explicit general data profession is visible; specialization and technical depth remain unverified.")
        # A bare 'analytics' field matches the title classifier but is not a
        # sufficient professional role in a freeform headline.
        if result[0] in ("analytics_peer", "data_engineering_peer", "marketing_analytics") and not re.search(r"\b(?:analyst|engineers?|architects?|scientist|developers?|administrator|specialist|consultant|manager|director|head|leader|chief|vp|lead|statistician|researcher|professional|coordinator|steward|reviewer|strategist)\b", segment):
            skipped.append(segment)
            continue
        if result[0] != "unclassified":
            eligible.append((result, segment))
    if not eligible:
        # Some clear headlines separate the role and its domain with a pipe.
        # Use only explicit role/domain pairs, never geography or an employer's
        # business. Partner rank alone does not prove a management remit.
        active = [role_text(part) for part in segments if not excluded_segment(part)]
        data_scope = [part for part in active if re.search(r"\b(?:data (?:and|&) analytics|data (?:and|&) ai|ai (?:and|&) data)\b", part)]
        data_roles = [part for part in active if re.search(r"\b(?:partner|consultant)\b", part)]
        if data_scope and data_roles:
            return "analytics_peer", "medium", "headline_explicit_separated_data_role", "A consulting/partner role and an explicit data/analytics domain are both self-described. Management remit and current responsibilities remain unverified.", list(dict.fromkeys(data_roles[:1] + data_scope[:1]))
        if any(re.search(r"\bprincipal\b", part) for part in active) and any(re.search(r"\bschool\b", part) for part in active):
            return "educator_community", "medium", "headline_explicit_school_principal", "A principal role and a named school are visible in the headline; no subject, influence or hiring remit is inferred.", active
        return "unclassified", "low", "insufficient_current_role_evidence", "Visible wording did not establish a conservative role bucket; review professional context when relevant. Aspirations, historical roles and tools alone were not treated as employment.", []
    # A person's first stated role anchors the bucket. Later buzzwords or a
    # sector served by the first role do not override it (e.g. recruiters of BI).
    result, selected = eligible[0]
    reason = result[3] + " Based on a self-described headline, not independent employment verification."
    return result[0], result[1], "headline_" + result[2], reason, [selected]


def read_roster(path):
    raw = path.read_bytes()
    if len(raw) > MAX_ROSTER_BYTES:
        raise ValueError("Follower roster exceeds the 25 MB input limit.")
    document = json.loads(raw)
    if not isinstance(document, dict) or not isinstance(document.get("rows"), list):
        raise ValueError("Follower roster must be an object containing rows[].")
    if len(document["rows"]) > MAX_ROWS:
        raise ValueError("Follower roster exceeds the 25,000 row input limit.")
    if not isinstance(document.get("collection_complete"), bool):
        raise ValueError("Follower roster needs an explicit collection_complete boolean.")
    expected = document.get("expected_count")
    if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int) or expected < 0):
        raise ValueError("expected_count must be a nonnegative integer or null.")
    rows = []
    for i, row in enumerate(document["rows"], 1):
        if not isinstance(row, dict):
            raise ValueError("Follower roster rows must be objects.")
        selected = {key: clean_text(row.get(key)) if key in ("name", "headline") else base.clean(row.get(key))
                    for key in ("name", "headline", "profile_url", "source_url", "observed_at")}
        selected["observed_at"] = selected["observed_at"] or base.clean(document.get("observed_at"))
        if any(len(value) > 8000 for value in selected.values()):
            raise ValueError("Follower roster fields exceed the 8,000 character limit.")
        selected["row_number"] = i
        rows.append(selected)
    return rows, {"roster": str(path), "roster_sha256": hashlib.sha256(raw).hexdigest(),
                  "source_url": base.clean(document.get("source_url")), "expected_count": expected,
                  "collection_complete": document["collection_complete"]}


def generate(root, roster, output, reviews=None):
    allowed = set(json.loads((root / "config/settings.json").read_text())["relationship_buckets"])
    rows, source = read_roster(roster)
    if reviews:
        existing_rows = json.loads(reviews.read_text())["reviews"]
        existing = {canonical_url(r["profile_url"], profile=True): r for r in existing_rows}
    else:
        existing = base.existing_reviews(root)
    saved_reviews = [{key: (clean_text(row.get(key)) if key == "bucket_evidence" else base.clean(row.get(key))) if isinstance(row.get(key), str) else row.get(key)
                      for key in ("id", "profile_url", "bucket", "bucket_evidence", "last_reviewed_at")}
                     for row in existing.values() if row.get("bucket") != "unclassified" or row.get("bucket_evidence") or row.get("last_reviewed_at")]
    snapshot = json.dumps({"reviews": sorted(saved_reviews, key=lambda row: row["profile_url"])}, ensure_ascii=False, indent=2) + "\n"
    base.private_write(output / "preserved-reviews.json", snapshot)
    source.update(review_snapshot_sha256=hashlib.sha256(snapshot.encode()).hexdigest(), configured_buckets=sorted(allowed))
    proposals, seen = [], set()
    for row in rows:
        issue = None
        try:
            url = canonical_url(row["profile_url"], profile=True)
        except (Error, ValueError):
            url = None
            issue = "missing_profile_url" if not row["profile_url"] else "invalid_profile_url"
        duplicate = bool(url and url in seen)
        if url:
            seen.add(url)
        try:
            observed = timestamp(row["observed_at"])
        except Error:
            observed = None
            issue = issue or "missing_or_invalid_observation_time"
        try:
            source_url = canonical_url(row["source_url"] or source["source_url"])
            if not source_url.startswith("https://www.linkedin.com/"):
                raise ValueError("Not a LinkedIn source.")
        except (Error, ValueError):
            source_url = None
            issue = issue or "missing_or_invalid_source_url"
        record = existing.get(url, {})
        preserve = bool(record and (record.get("bucket") != "unclassified" or record.get("bucket_evidence") or record.get("last_reviewed_at")))
        bucket, confidence, rule, review_reason, role_segments = classify_headline(row["headline"])
        suggestion = bucket
        evidence = ("Provisional visible follower-card role classification. Headline: " + (row["headline"] or "[missing]") +
                    "; selected role text: " + (" | ".join(role_segments) or "[none]") + "; observed_at: " + str(observed) +
                    "; source: " + str(source_url) + "; roster row " + str(row["row_number"]) + "; rule: " + rule +
                    "; classifier " + RULE_VERSION + ". Headline is self-described; current activity and hiring relevance are unverified.")
        if preserve:
            bucket, confidence, rule = record["bucket"], "preserved", "preserve_existing_review"
            evidence = clean_text(record.get("bucket_evidence") or "Existing review retained.")
            review_reason = "Existing reviewed bucket retained; headline-only suggestion was " + suggestion + "."
        if bucket not in allowed:
            raise ValueError("Classifier generated a bucket absent from configuration: " + bucket)
        proposals.append({"row_number": row["row_number"], "profile_url": url, "name": row["name"], "headline": row["headline"],
                          "observed_at": observed, "source_url": source_url, "proposed_bucket": bucket,
                          "confidence": confidence, "evidence": evidence, "rule": rule, "role_segments": role_segments,
                          "apply": bool(url and not issue and not duplicate and not preserve and bucket != "unclassified"),
                          "existing_relationship_id": record.get("id"), "preserve_existing_review": preserve,
                          "review_reason": review_reason, "unresolved_reason": issue, "duplicate_profile_url": duplicate,
                          "geography": None, "geography_inference": "not_performed"})
    unique = [p for p in proposals if p["profile_url"] and not p["duplicate_profile_url"]]
    summary = {"source_rows": len(proposals), "unique_valid_profile_urls": len(seen),
               "expected_follower_count": source["expected_count"], "source_collection_complete": source["collection_complete"],
               "missing_from_expected_count": max(source["expected_count"] - len(seen), 0) if source["expected_count"] is not None else None,
               "identity_count_matches_expected": len(seen) == source["expected_count"] if source["expected_count"] is not None else None,
               "full_inventory_accounted_for": bool(source["collection_complete"] and source["expected_count"] is not None and len(seen) == source["expected_count"]),
               "duplicate_profile_rows": sum(p["duplicate_profile_url"] for p in proposals),
               "invalid_or_missing_evidence_rows": sum(bool(p["unresolved_reason"]) for p in proposals),
               "preserved_reviewed_profiles": sum(p["preserve_existing_review"] for p in unique),
               "proposed_updates": sum(p["apply"] for p in proposals),
               "bucket_distribution_unique_profiles": dict(sorted(collections.Counter(p["proposed_bucket"] for p in unique).items())),
               "proposed_update_buckets": dict(sorted(collections.Counter(p["proposed_bucket"] for p in proposals if p["apply"]).items())),
               "confidence_distribution_unique_profiles": dict(sorted(collections.Counter(p["confidence"] for p in unique).items())),
               "rules": dict(sorted(collections.Counter(p["rule"] for p in unique).items()))}
    packet = {"schema_version": 1, "classifier_version": RULE_VERSION,
              "classifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "base_classifier_version": base.RULE_VERSION,
              "base_classifier_sha256": hashlib.sha256((ROOT / "scripts/classify-network.py").read_bytes()).hexdigest(),
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": source,
              "authority": "proposal_only_no_database_mutation", "summary": summary,
              "interpretation": "apply=true means eligible for review, not approved. Existing reviews are retained. Headline evidence is not verified employment, residence, interest, influence, or a current conversation.",
              "proposals": proposals}
    base.private_write(output / "role-proposals.json", json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    columns = list(proposals[0]) if proposals else ["profile_url", "proposed_bucket", "apply"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in proposals:
        writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for key, value in row.items()})
    base.private_write(output / "role-proposals.csv", stream.getvalue())
    base.private_write(output / "role-summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    examples = {}
    for item in unique:
        examples.setdefault(item["rule"], [])
        if item["headline"] not in examples[item["rule"]] and len(examples[item["rule"]]) < 12:
            examples[item["rule"]].append(item["headline"])
    base.private_write(output / "role-rule-examples.json", json.dumps(examples, ensure_ascii=False, indent=2) + "\n")
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--roster", type=Path, required=True, help="Path to your observed follower roster")
    parser.add_argument("--output", type=Path, help="Defaults to a classification directory beside the roster.")
    parser.add_argument("--reviews", type=Path, help="Replay a preserved-reviews.json instead of reading current database reviews.")
    args = parser.parse_args()
    roster = args.roster.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else roster.parent / "classification"
    try:
        packet = generate(args.root.expanduser().resolve(), roster, output, args.reviews.expanduser().resolve() if args.reviews else None)
    except (Error, ValueError, OSError, KeyError) as exc:
        raise SystemExit("Follower classification could not complete: " + str(exc))
    print(json.dumps({"proposal_json": str(output / "role-proposals.json"), "summary": packet["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
