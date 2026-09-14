"""Private imports of followers actually observed in the user's LinkedIn UI.

No website access occurs here. Snapshots assert incoming follower membership only;
unseen profiles are never inferred from totals and absent profiles are not removed.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

from .network import observe_membership
from .store import Error, canonical_url, digest, dump, ident, now, timestamp


def _text(value, field, required=False, maximum=4000):
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise Error("Follower " + field + " must be " + ("nonempty " if required else "") + "text.")
    return value.strip() or None


def _source(value):
    source = canonical_url(_text(value, "source_url", required=True))
    if urlsplit(source).hostname != "www.linkedin.com":
        raise Error("Follower source_url must be an observed LinkedIn page.")
    return source


def import_followers(s, file, observed_at=None):
    path = Path(file).expanduser().resolve()
    if path.stat().st_size > 25 * 1024 * 1024:
        raise Error("Follower snapshot exceeds the 25 MB import limit.")
    raw = path.read_bytes()
    checksum = digest(raw)
    existing = s.one("SELECT * FROM imports WHERE kind='followers' AND sha256=?", (checksum,))
    if existing:
        # A recorded import is not sufficient evidence that its private source
        # still exists unchanged. Refuse replay success if provenance was lost.
        s.read_checked(existing["stored_path"], existing["sha256"])
        existing["summary"] = json.loads(existing.pop("summary_json"))
        return {"existing": True, "import": existing}
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise Error("Follower snapshot must be valid JSON.") from exc
    if isinstance(document, list):
        document = {"rows": document}
    if not isinstance(document, dict) or not isinstance(document.get("rows"), list):
        raise Error("Follower snapshot requires {rows:[...]} or a row list.")
    rows = document["rows"]
    if len(rows) > 100000:
        raise Error("Follower snapshot exceeds the 100,000 row limit.")
    expected = document.get("expected_count")
    if expected is not None and (type(expected) is not int or expected < 0):
        raise Error("Follower expected_count must be a nonnegative integer or null.")
    complete = document.get("collection_complete", False)
    if type(complete) is not bool:
        raise Error("Follower collection_complete must be true or false.")
    default_at = observed_at or document.get("observed_at")
    default_source = document.get("source_url")
    if default_at:
        default_at = timestamp(default_at)
    if default_source:
        default_source = _source(default_source)
    if not rows and (not default_at or not default_source):
        raise Error("An empty follower snapshot needs observed_at and source_url evidence.")
    parsed, unresolved, seen, duplicates = [], [], set(), 0
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise Error("Every follower row must be an object.")
        instant = timestamp(row.get("observed_at") or default_at)
        source_url = _source(row.get("source_url") or default_source)
        name = _text(row.get("name"), "name", maximum=1000)
        headline = _text(row.get("headline"), "headline")
        try:
            url = canonical_url(_text(row.get("profile_url"), "profile_url", required=True), profile=True)
        except Error:
            unresolved.append({"row": index, "reason": "missing_or_invalid_profile_url"})
            continue
        if not name:
            unresolved.append({"row": index, "reason": "missing_name"})
            continue
        if url in seen:
            duplicates += 1
            continue
        seen.add(url)
        parsed.append(dict(profile_url=url, name=name, headline=headline, observed_at=instant, source_url=source_url))
    snapshot_at = max(([default_at] if default_at else []) + [row["observed_at"] for row in parsed], default=None)
    if not snapshot_at:
        raise Error("Follower snapshot needs an explicit observation timestamp.")
    if complete and unresolved:
        state = "collection_exhausted_unresolved_rows"
    elif complete and expected is None:
        state = "collection_exhausted_count_unavailable"
    elif complete and expected == len(parsed):
        state = "complete_observed_snapshot"
    elif complete:
        state = "collection_exhausted_count_mismatch"
    else:
        state = "partial_inventory"
    stored = "data/imports/" + checksum + ".followers.json"
    summary = dict(inserted=0, existing_profiles=0, memberships_added=0, observed_at=snapshot_at,
                   expected_count=expected, input_rows=len(rows), unique_profiles=len(parsed), duplicate_rows=duplicates,
                   unresolved_rows=unresolved, source_url=default_source, collection_complete=complete,
                   completeness=state, connection_overlap_in_snapshot=0,
                   note="Positive incoming-follower observations; missing profiles do not establish an unfollow. Counts are as observed, not a live census.")
    with s.transaction():
        if s.one("SELECT id FROM imports WHERE kind='followers' AND sha256=?", (checksum,)):
            raise Error("This follower snapshot was already processed by another session.")
        for row in parsed:
            person = s.one("SELECT id FROM relationships WHERE profile_url=?", (row["profile_url"],))
            if person:
                person_id = person["id"]
                summary["existing_profiles"] += 1
            else:
                person_id = ident("person")
                s.insert("relationships", dict(id=person_id, profile_url=row["profile_url"], name=row["name"],
                    position=row["headline"], relationship_type="follower", source="observed_ui:" + stored,
                    created_at=now(), updated_at=now()))
                summary["inserted"] += 1
            if not s.one("SELECT 1 FROM relationship_memberships WHERE relationship_id=? AND membership='follower'", (person_id,)):
                summary["memberships_added"] += 1
            if s.one("SELECT 1 FROM relationship_memberships WHERE relationship_id=? AND membership='connection'", (person_id,)):
                summary["connection_overlap_in_snapshot"] += 1
            observe_membership(s, person_id, "follower", row["observed_at"], "observed_ui:" + stored,
                               row["source_url"], row["name"], row["headline"])
        # Store the unchanged supplied snapshot; the register contains only selected fields.
        # A process may have saved bytes before its database transaction rolled back.
        # Reuse only an identical snapshot; never overwrite changed source evidence.
        target = s.managed(stored)
        if target.exists():
            s.read_checked(stored, checksum)
        else:
            s.write(stored, raw, exclusive=True)
        item = dict(id=ident("import"), kind="followers", sha256=checksum, source_path=str(path),
                    stored_path=stored, imported_at=now(), summary_json=dump(summary))
        s.insert("imports", item)
    item["summary"] = summary
    item.pop("summary_json")
    return {"existing": False, "import": item}


def coverage(s):
    summaries = []
    for row in s.all("SELECT rowid AS import_order,id,stored_path,imported_at,summary_json FROM imports WHERE kind='followers'"):
        summary = json.loads(row.pop("summary_json"))
        summaries.append({**row, **summary})
    latest = max(summaries, key=lambda item: (item["observed_at"], item["imported_at"], item["import_order"]), default=None)
    if latest:
        latest.pop("import_order")
    total = s.one("SELECT COUNT(*) AS n FROM relationship_memberships WHERE membership='follower'")["n"]
    overlap = s.one("""SELECT COUNT(*) AS n FROM relationship_memberships f
        JOIN relationship_memberships c ON c.relationship_id=f.relationship_id AND c.membership='connection'
        WHERE f.membership='follower'""")["n"]
    buckets = s.all("""SELECT r.bucket,COUNT(*) AS profiles FROM relationships r
        JOIN relationship_memberships m ON m.relationship_id=r.id AND m.membership='follower'
        GROUP BY r.bucket ORDER BY r.bucket""")
    return dict(registered_followers=total, registered_follower_connection_overlap=overlap,
                follower_only_profiles=total - overlap, follower_buckets=buckets,
                latest_follower_snapshot=latest,
                follower_coverage_note="Registered followers are the union of positive observations. Latest snapshot coverage is separate; unseen profiles are not treated as unfollows.")
