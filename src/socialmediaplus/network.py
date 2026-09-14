"""Evidence-backed relationship classification and bounded review queues."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from .store import Error, canonical_url, digest, dump, ident, now, timestamp


BUCKETS = ("analytics_peer", "data_engineering_peer", "analytics_leader", "recruiting_talent",
           "business_stakeholder", "marketing_analytics", "educator_community", "other_professional", "unclassified")
MEMBERSHIPS = ("connection", "follower", "peer", "creator", "company_contact")


def observe_membership(s, relationship_id, membership, observed_at, source, source_url=None, name=None, headline=None):
    """Record positive source evidence inside the caller's transaction; absence is not an unfollow."""
    if membership not in MEMBERSHIPS or not source:
        raise Error("Membership needs a supported type and observed source.")
    instant = timestamp(observed_at)
    values = dict(relationship_id=relationship_id, membership=membership, observed_at=instant,
                  source=source, source_url=source_url, name=name, headline=headline)
    checksum = digest(dump(values))
    if not s.one("SELECT id FROM membership_observations WHERE dedup_key=?", (checksum,)):
        s.insert("membership_observations", dict(id=ident("membership"), dedup_key=checksum, **values))
    s.db.execute("""INSERT INTO relationship_memberships
        (relationship_id,membership,first_observed_at,last_observed_at,source) VALUES (?,?,?,?,?)
        ON CONFLICT(relationship_id,membership) DO UPDATE SET
        first_observed_at=MIN(first_observed_at,excluded.first_observed_at),
        source=CASE WHEN excluded.last_observed_at>=last_observed_at THEN excluded.source ELSE source END,
        last_observed_at=MAX(last_observed_at,excluded.last_observed_at)""",
        (relationship_id, membership, instant, instant, source))


def memberships(s, relationship_id):
    return s.all("SELECT * FROM relationship_memberships WHERE relationship_id=? ORDER BY membership", (relationship_id,))


def list_people(s, bucket=None, membership=None, exclude_membership=None):
    selected = _membership_filter(membership)
    excluded = _membership_filter(exclude_membership)
    sql, params = "SELECT r.* FROM relationships r WHERE 1=1", []
    if bucket:
        sql += " AND r.bucket=?"
        params.append(bucket)
    if selected:
        sql += " AND EXISTS (SELECT 1 FROM relationship_memberships m WHERE m.relationship_id=r.id AND m.membership IN (" + ",".join("?" for _ in selected) + "))"
        params.extend(selected)
    if excluded:
        sql += " AND NOT EXISTS (SELECT 1 FROM relationship_memberships m WHERE m.relationship_id=r.id AND m.membership IN (" + ",".join("?" for _ in excluded) + "))"
        params.extend(excluded)
    rows = s.all(sql + " ORDER BY r.name", params)
    for row in rows:
        row["memberships"] = memberships(s, row["id"])
    return rows


def _membership_filter(value):
    selected = [value] if isinstance(value, str) else list(value or [])
    if any(member not in MEMBERSHIPS for member in selected):
        raise Error("Unknown relationship membership filter.")
    return sorted(set(selected))


def add(s, name, url, source, company=None, position=None, relationship_type="connection"):
    if not name.strip() or not source.strip():
        raise Error("Relationships require a name and observed source.")
    url = canonical_url(url, profile=True)
    with s.transaction():
        existing = s.one("SELECT * FROM relationships WHERE profile_url=?", (url,))
        if existing:
            observe_membership(s, existing["id"], relationship_type, now(), source, name=name, headline=position)
            return {"existing": True, "relationship": existing}
        item = dict(id=ident("person"), name=name, profile_url=url, source=source, company=company, position=position,
                    relationship_type=relationship_type, created_at=now(), updated_at=now())
        s.insert("relationships", item)
        observe_membership(s, item["id"], relationship_type, item["created_at"], source, name=name, headline=position)
    return s.require("relationships", item["id"])


def update(s, relationship_id, bucket=None, evidence=None, geography=None, geography_evidence=None,
           topic=None, reviewed_at=None, next_review=None, skip=None, clear_skip=False):
    changes = {"updated_at": now()}
    if bucket is not None:
        if bucket not in s.settings.get("relationship_buckets", BUCKETS):
            raise Error("Unknown relationship bucket.")
        if bucket != "unclassified" and not evidence:
            raise Error("Classification requires --evidence from an observed professional source.")
        changes.update(bucket=bucket, bucket_evidence=evidence)
    if geography is not None:
        if not geography_evidence:
            raise Error("Geography requires --geography-evidence; do not infer location from names.")
        changes.update(geography=geography, geography_evidence=geography_evidence)
    if topic is not None:
        changes["topic"] = topic
    if reviewed_at:
        changes["last_reviewed_at"] = timestamp(reviewed_at, s.settings["timezone"], validate_offset=False)
    if next_review:
        changes["next_review_at"] = timestamp(next_review, s.settings["timezone"], validate_offset=False)
    if skip is not None or clear_skip:
        changes["skip_reason"] = None if clear_skip else skip
    with s.transaction():
        s.require("relationships", relationship_id)
        s.db.execute("UPDATE relationships SET " + ",".join(k + "=?" for k in changes) + " WHERE id=?", list(changes.values()) + [relationship_id])
    return s.require("relationships", relationship_id)


def due(s, as_of=None, limit=None, bucket=None, priority="conversations", cooldown_hours=24, membership=None, exclude_membership=None):
    instant = timestamp(as_of, s.settings["timezone"], validate_offset=False) if as_of else now()
    limit = limit if limit is not None else s.settings.get("pilot", {}).get("daily_shortlist_limit", s.settings.get("daily_queue_limit", 8))
    if not 1 <= int(limit) <= 100:
        raise Error("Review queue limit must be from 1 to 100.")
    if priority not in ("conversations", "rotation") or not 0 <= cooldown_hours <= 720:
        raise Error("Use conversations/rotation priority and a cooldown from 0 to 720 hours.")
    selected = [bucket] if isinstance(bucket, str) else list(bucket or [])
    if not selected and priority == "conversations":
        selected = s.settings.get("daily_priority_buckets", ["analytics_peer", "data_engineering_peer", "analytics_leader", "marketing_analytics"])
    if any(name not in s.settings.get("relationship_buckets", BUCKETS) for name in selected):
        raise Error("Unknown relationship review bucket.")
    cutoff = (datetime.fromisoformat(instant) - timedelta(days=30)).isoformat(timespec="seconds")
    cooldown = (datetime.fromisoformat(instant) - timedelta(hours=cooldown_hours)).isoformat(timespec="seconds")
    sql = """WITH candidates AS (
             SELECT r.*, MAX(i.occurred_at) AS last_interaction_at, COUNT(i.id) AS recorded_interactions,
             MAX(CASE WHEN i.kind IN ('comment','reply','conversation','dm','inmail') AND i.occurred_at>=? THEN i.occurred_at END) AS recent_exchange_at
             FROM relationships r LEFT JOIN interactions i ON i.relationship_id=r.id AND i.state='confirmed' AND i.occurred_at<=?
             WHERE (r.skip_reason IS NULL OR r.skip_reason='') AND (r.next_review_at IS NULL OR r.next_review_at<=?)
             GROUP BY r.id) SELECT * FROM candidates WHERE 1=1"""
    params = [cutoff, instant, instant]
    selected_memberships = _membership_filter(membership)
    excluded_memberships = _membership_filter(exclude_membership)
    if selected_memberships:
        sql += " AND EXISTS (SELECT 1 FROM relationship_memberships m WHERE m.relationship_id=candidates.id AND m.membership IN (" + ",".join("?" for _ in selected_memberships) + ") AND m.first_observed_at<=?)"
        params.extend(selected_memberships + [instant])
    if excluded_memberships:
        sql += " AND NOT EXISTS (SELECT 1 FROM relationship_memberships m WHERE m.relationship_id=candidates.id AND m.membership IN (" + ",".join("?" for _ in excluded_memberships) + ") AND m.first_observed_at<=?)"
        params.extend(excluded_memberships + [instant])
    if priority == "conversations":
        sql += " AND (recent_exchange_at IS NOT NULL"
        if selected:
            sql += " OR bucket IN (" + ",".join("?" for _ in selected) + ")"
            params.extend(selected)
        sql += ") AND (last_interaction_at IS NULL OR last_interaction_at<=?)"
        params.append(cooldown)
        sql += " ORDER BY CASE WHEN recent_exchange_at IS NOT NULL THEN 0 ELSE 1 END, recent_exchange_at DESC,COALESCE(last_interaction_at,'') ASC,COALESCE(last_reviewed_at,'') ASC,name ASC LIMIT ?"
    else:
        if selected:
            sql += " AND bucket IN (" + ",".join("?" for _ in selected) + ")"
            params.extend(selected)
        sql += " ORDER BY COALESCE(last_interaction_at,'') ASC,COALESCE(last_reviewed_at,'') ASC,name ASC LIMIT ?"
    params.append(int(limit))
    rows = s.all(sql, params)
    for row in rows:
        row["memberships"] = [item for item in memberships(s, row["id"]) if item["first_observed_at"] <= instant]
        if priority == "conversations" and row["recent_exchange_at"]:
            row["reason"] = "A past comment, reply, message or conversation was recorded within 30 days; review the thread context. No unanswered reply is implied."
        elif priority == "conversations":
            row["reason"] = "Professional role evidence matches a selected bucket; current profile and content have not been checked."
        elif row["bucket"] == "unclassified":
            row["reason"] = "Professional relevance unclassified; review supplied evidence first."
        else:
            row["reason"] = "Inventory review due; verify current relevance before engaging."
    return {"as_of": instant, "limit": int(limit), "priority": priority, "selected_buckets": selected,
            "selected_memberships": selected_memberships,
            "excluded_memberships": excluded_memberships,
            "exchange_lookback_days": 30 if priority == "conversations" else None,
            "contact_cooldown_hours": cooldown_hours if priority == "conversations" else None,
            "queue": rows, "note": "A local evidence-based review shortlist; no current profile/content review, unanswered message, or engagement authorization is implied."}


def apply_proposal(s, file, evidence):
    """Apply explicitly selected local role classifications in one transaction."""
    if not evidence.strip():
        raise Error("Applying classifications requires a review-decision reference.")
    raw = Path(file).read_bytes()
    document = json.loads(raw)
    proposals = document.get("proposals") if isinstance(document, dict) else document
    if not isinstance(proposals, list):
        raise Error("Classification input must be a proposal list or {proposals:[...]}.")
    checksum = digest(raw)
    result = {"updated": 0, "preserved_reviewed": 0, "not_selected": 0, "proposal_sha256": checksum}
    allowed = s.settings.get("relationship_buckets", BUCKETS)
    seen = set()
    with s.transaction():
        for item in proposals:
            if not isinstance(item, dict):
                raise Error("Every classification proposal must be an object.")
            if item.get("apply") is not True:
                result["not_selected"] += 1
                continue
            url = canonical_url(item.get("profile_url") or "", profile=True)
            if url in seen:
                raise Error("Multiple selected proposals target the same profile URL.")
            seen.add(url)
            person = s.one("SELECT * FROM relationships WHERE profile_url=?", (url,))
            if not person:
                raise Error("A selected profile URL has not been imported into the relationship register.")
            if (person["bucket"] != "unclassified" and person["bucket_evidence"]) or item.get("preserve_existing_review"):
                result["preserved_reviewed"] += 1
                continue
            bucket, grounding = item.get("proposed_bucket"), item.get("evidence")
            if bucket not in allowed or bucket == "unclassified" or not isinstance(grounding, str) or not grounding.strip():
                raise Error("Selected proposals need a classified professional bucket and exact source evidence.")
            confidence = item.get("confidence", "unspecified")
            reference = evidence + " | proposal_sha256=" + checksum + " | confidence=" + str(confidence) + " | " + grounding
            # A classification review is not a review/visit of current profile content.
            s.db.execute("UPDATE relationships SET bucket=?,bucket_evidence=?,updated_at=? WHERE id=?", (bucket, reference, now(), person["id"]))
            result["updated"] += 1
    return result
