"""Version approval and human-observed platform receipts; never a publisher."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .store import Error, canonical_url, digest, dump, ident, now, timestamp
from . import engagement


FORMATS = ("text", "image", "document", "article", "video")
KINDS = ("schedule", "publish", "comment", "reply", "like", "visit") + engagement.PLUS_KINDS
AUTHORITIES = ("native_linkedin", "official_api", "postiz", "user_manual")


def content_show(s, content_id):
    row = s.require("content", content_id)
    row["evidence"] = json.loads(row.pop("evidence_json"))
    row["versions"] = s.all("SELECT * FROM versions WHERE content_id=? ORDER BY version", (content_id,))
    row["assets"] = s.all("SELECT * FROM assets WHERE content_id=? ORDER BY created_at,id", (content_id,))
    row["actions"] = s.all("SELECT * FROM actions WHERE content_id=? ORDER BY created_at,id", (content_id,))
    row["approvals"] = s.all("SELECT * FROM approvals WHERE content_id=? ORDER BY created_at,id", (content_id,))
    return row


def assert_editable(s, content_id):
    active = s.one("SELECT id,state FROM actions WHERE content_id=? AND state IN ('prepared','uncertain','confirmed','published') AND kind IN ('schedule','publish')", (content_id,))
    if active:
        raise Error("Content is locked by action " + active["id"] + " (" + active["state"] + "). Reconcile or cancel the remote schedule before editing; published content needs a new draft.")


def file_text(file):
    path = Path(file).expanduser().resolve()
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Error("Content file must be readable UTF-8 text.") from exc
    if not text.strip():
        raise Error("Content cannot be empty.")
    return raw


def content_add(s, file, title, pillar="unclassified", audience="unclassified", format="text", evidence=()):
    raw = file_text(file)
    if format not in FORMATS:
        raise Error("Unsupported content format.")
    content_id, created = ident("post"), now()
    with s.transaction():
        duplicate = s.one("SELECT content_id FROM versions WHERE sha256=?", (digest(raw),))
        if duplicate:
            raise Error("This exact content is already registered as " + duplicate["content_id"])
        authority = s.settings.get("publishing_mode", "native_linkedin")
        if authority not in AUTHORITIES:
            raise Error("Configured publishing_mode is not a supported authority.")
        s.insert("content", dict(id=content_id, title=title, pillar=pillar, audience=audience, format=format, publishing_authority=authority,
                                evidence_json=dump(list(evidence)), created_at=created, updated_at=created))
        path = "content/versions/" + content_id + "/v001.md"
        s.write(path, raw, exclusive=True)
        s.insert("versions", dict(content_id=content_id, version=1, path=path, sha256=digest(raw), created_at=created))
    return content_show(s, content_id)


def content_revise(s, content_id, file, evidence=None):
    raw = file_text(file)
    with s.transaction():
        row = s.require("content", content_id)
        assert_editable(s, content_id)
        duplicate = s.one("SELECT content_id FROM versions WHERE sha256=?", (digest(raw),))
        if duplicate:
            raise Error("This exact content version is already registered as " + duplicate["content_id"])
        version = row["current_version"] + 1
        path = "content/versions/" + content_id + "/v" + str(version).zfill(3) + ".md"
        s.write(path, raw, exclusive=True)
        s.insert("versions", dict(content_id=content_id, version=version, path=path, sha256=digest(raw), created_at=now()))
        s.db.execute("UPDATE content SET current_version=?,status='draft',updated_at=?,evidence_json=? WHERE id=?",
                     (version, now(), dump(evidence) if evidence is not None else row["evidence_json"], content_id))
    return content_show(s, content_id)


def set_slot(s, content_id, at, timezone):
    instant = timestamp(at, timezone)
    with s.transaction():
        s.require("content", content_id)
        assert_editable(s, content_id)
        s.db.execute("UPDATE content SET scheduled_at=?,schedule_timezone=?,status='draft',updated_at=? WHERE id=?", (instant, timezone, now(), content_id))
    return content_show(s, content_id)


def set_route(s, content_id, authority):
    if authority not in AUTHORITIES:
        raise Error("Unknown publishing authority.")
    with s.transaction():
        row = s.require("content", content_id)
        assert_editable(s, content_id)
        if row["publishing_authority"] != authority:
            s.db.execute("UPDATE content SET publishing_authority=?,status='draft',updated_at=? WHERE id=?", (authority, now(), content_id))
    return content_show(s, content_id)


def set_format(s, content_id, format):
    if format not in FORMATS:
        raise Error("Unsupported content format.")
    with s.transaction():
        row = s.require("content", content_id)
        if row["format"] != format:
            assert_editable(s, content_id)
            s.db.execute("UPDATE content SET format=?,status='draft',updated_at=? WHERE id=?", (format, now(), content_id))
    return content_show(s, content_id)


def asset_add(s, content_id, file, alt, source, metadata=None):
    if not alt.strip() or not source.strip():
        raise Error("Assets require alt text and rights/provenance source.")
    original = Path(file).expanduser().resolve()
    if not original.is_file():
        raise Error("Asset file does not exist.")
    raw = original.read_bytes()
    if not raw:
        raise Error("Asset file is empty.")
    asset_id = ident("asset")
    suffix = original.suffix.lower()
    if len(suffix) > 12 or not all(c.isalnum() or c == "." for c in suffix):
        suffix = ".bin"
    path = "assets/registered/" + asset_id + suffix
    with s.transaction():
        s.require("content", content_id)
        assert_editable(s, content_id)
        if s.one("SELECT id FROM assets WHERE content_id=? AND sha256=? AND active=1", (content_id, digest(raw))):
            raise Error("This asset is already attached to the content.")
        s.write(path, raw, exclusive=True)
        s.insert("assets", dict(id=asset_id, content_id=content_id, path=path, original_path=str(original), sha256=digest(raw),
                               alt_text=alt, source=source, metadata_json=dump(metadata or {}), created_at=now()))
        s.db.execute("UPDATE content SET status='draft',updated_at=? WHERE id=?", (now(), content_id))
    return s.require("assets", asset_id)


def asset_remove(s, asset_id):
    with s.transaction():
        row = s.require("assets", asset_id)
        assert_editable(s, row["content_id"])
        s.db.execute("UPDATE assets SET active=0 WHERE id=?", (asset_id,))
        s.db.execute("UPDATE content SET status='draft',updated_at=? WHERE id=?", (now(), row["content_id"]))
    return s.require("assets", asset_id)


def fingerprint(s, content_id):
    row = s.require("content", content_id)
    version = s.one("SELECT * FROM versions WHERE content_id=? AND version=?", (content_id, row["current_version"]))
    s.read_checked(version["path"], version["sha256"])
    assets = s.all("SELECT id,sha256,path,alt_text,source,metadata_json FROM assets WHERE content_id=? AND active=1 ORDER BY id", (content_id,))
    for asset in assets:
        s.read_checked(asset["path"], asset["sha256"])
    signed = {k: row[k] for k in ("id", "title", "pillar", "audience", "format", "platform", "publishing_authority", "current_version", "evidence_json", "scheduled_at", "schedule_timezone")}
    signed.update(sha256=version["sha256"], assets=assets,
                  profile_url=canonical_url(s.settings["profile_url"], profile=True))
    return digest(dump(signed))


def approve(s, content_id, by, evidence):
    if not by.strip() or not evidence.strip():
        raise Error("Approval requires approver and an explicit authorization reference.")
    with s.transaction():
        row = s.require("content", content_id)
        assert_editable(s, content_id)
        assets = s.all("SELECT * FROM assets WHERE content_id=? AND active=1", (content_id,))
        if row["format"] in ("image", "document", "video") and not assets:
            raise Error("This format requires a registered final asset before approval.")
        fp = fingerprint(s, content_id)
        approval_id = ident("approval")
        s.insert("approvals", dict(id=approval_id, content_id=content_id, fingerprint=fp, approved_by=by, evidence=evidence, created_at=now()))
        s.db.execute("UPDATE content SET status='approved',updated_at=? WHERE id=?", (now(), content_id))
    return {"id": approval_id, "content_id": content_id, "fingerprint": fp, "state": "approved", "advisories": content_check(s, content_id)["advisories"], "note": "Approval is a local record of the supplied authorization; nothing was posted."}


def content_check(s, content_id):
    row = s.require("content", content_id)
    version = s.one("SELECT * FROM versions WHERE content_id=? AND version=?", (content_id, row["current_version"]))
    text = s.read_checked(version["path"], version["sha256"]).read_text(encoding="utf-8")
    def normalize(value):
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", value.lower())).strip()
    normalized = normalize(text)
    hook = normalize(next((line for line in text.splitlines() if line.strip()), ""))
    comparisons = []
    for other in s.all("SELECT c.id,v.path,v.sha256 FROM content c JOIN versions v ON v.content_id=c.id AND v.version=c.current_version WHERE c.id!=?", (content_id,)):
        try:
            prior = s.read_checked(other["path"], other["sha256"]).read_text(encoding="utf-8")
            comparisons.append((other["id"], prior))
        except Error:
            continue
    comparisons += [(x["id"], x["text"]) for x in s.all("SELECT id,text FROM history WHERE kind IN ('shares','articles') AND text IS NOT NULL")]
    advisories = []
    for other_id, prior in comparisons:
        prior_norm = normalize(prior)
        similarity = SequenceMatcher(None, normalized, prior_norm).ratio()
        prior_hook = normalize(next((line for line in prior.splitlines() if line.strip()), ""))
        if similarity >= 0.78 or (len(hook) >= 30 and SequenceMatcher(None, hook, prior_hook).ratio() >= 0.85):
            advisories.append({"kind": "similar_wording_or_hook", "record_id": other_id, "similarity": round(similarity, 3), "action": "Review for repetition; this heuristic is advisory, not a platform score."})
    if not json.loads(row["evidence_json"]):
        advisories.append({"kind": "missing_evidence_references", "action": "Verify personal and factual claims; the CLI cannot establish their truth."})
    if row["format"] != "article" and len(text) > 3000:
        advisories.append({"kind": "feed_text_length", "characters": len(text), "action": "Review LinkedIn format limits before scheduling."})
    return {"content_id": content_id, "fingerprint": fingerprint(s, content_id), "advisories": advisories}


def prepare(s, kind, authority, content_id=None, target=None, response=None, context=None, relationship_id=None,
            session_id=None, opportunity_id=None, attachment=None, details=None):
    if kind not in KINDS:
        raise Error("Unsupported action kind.")
    if authority not in AUTHORITIES:
        raise Error("Unknown scheduling/action authority.")
    if content_id and kind not in ("schedule", "publish"):
        raise Error("Engagement actions use --target rather than --content.")
    target = canonical_url(target, profile=kind in engagement.OUTREACH) if target else None
    plus = kind in engagement.PLUS_KINDS or session_id is not None
    if not plus and (opportunity_id or attachment or details is not None):
        raise Error("Plus evidence/attachments require a --session.")
    with s.transaction():
        if relationship_id:
            s.require("relationships", relationship_id)
        fp, slot, attachment_data = None, None, None
        if plus:
            if kind in ("schedule", "publish"):
                raise Error("Plus sessions do not replace exact publishing approvals.")
            details = details or {}
            attachment_data = engagement.preflight(s, kind, authority, target, response, context, relationship_id,
                                                  session_id, opportunity_id, attachment, details)
            if kind in ("reaction", "repost"):
                duplicate = s.one("SELECT id FROM actions WHERE target_url=? AND kind IN (?,?) AND state IN ('prepared','uncertain','confirmed')", (target, kind, "like" if kind == "reaction" else kind))
                if duplicate:
                    raise Error("This target already has an active/completed reaction or repost: " + duplicate["id"])
        if kind in ("schedule", "publish"):
            if not content_id:
                raise Error("Publishing actions require --content.")
            row = s.require("content", content_id)
            fp = fingerprint(s, content_id)
            if not s.one("SELECT id FROM approvals WHERE content_id=? AND fingerprint=?", (content_id, fp)):
                raise Error("The exact current text, assets, destination and slot have not been approved.")
            slot = row["scheduled_at"]
            if kind == "schedule" and not slot:
                raise Error("Set content slot before approval and preparing a schedule.")
            if kind == "schedule" and slot <= now():
                raise Error("A new schedule must be in the future.")
            if kind == "publish" and slot and slot > now():
                raise Error("Immediate publication would bypass the approved future slot. Use the approved schedule action.")
            active = s.one("SELECT * FROM actions WHERE content_id=? AND kind IN ('schedule','publish') AND state IN ('prepared','uncertain','confirmed','published')", (content_id,))
            if active:
                if active["kind"] == kind and active["fingerprint"] == fp and active["authority"] == authority:
                    return {"existing": True, "action": active, "instruction": "Do not submit again. Resolve the existing action using its receipt or reconciliation."}
                raise Error("This content already has an active publishing authority/action: " + active["id"])
            if authority != row["publishing_authority"]:
                raise Error("Action authority differs from the approved per-content route. Use content route, then approve that exact route before preparing.")
        else:
            if not target:
                raise Error("Engagement actions require an exact --target URL.")
            if kind in ("comment", "reply") and (not response or not context):
                raise Error("Comments/replies require exact response text and parent context.")
            if kind == "reply" and "comment" not in target.lower():
                # Do not require a particular LinkedIn URL encoding; full context is authoritative.
                if len(context.strip()) < 20:
                    raise Error("Replies need the original post and parent comment in --context.")
        key_data = [kind, content_id, fp, target, response, slot]
        if plus:
            key_data += [details, opportunity_id, attachment_data["sha256"] if attachment_data else None]
        key = digest(dump(key_data))
        existing = s.one("SELECT * FROM actions WHERE idempotency_key=?", (key,))
        if existing:
            return {"existing": True, "action": existing, "instruction": "Do not resubmit. An explicitly reconciled failed attempt can use action retry."}
        action_id, created = ident("action"), now()
        s.insert("actions", dict(id=action_id, kind=kind, content_id=content_id, fingerprint=fp, target_url=target,
                                 response=response, parent_context=context, authority=authority, idempotency_key=key,
                                 relationship_id=relationship_id,
                                 scheduled_at=slot, created_at=created, updated_at=created))
        if plus:
            engagement.save_details(s, s.require("actions", action_id), session_id, opportunity_id, details, attachment_data)
    return {"existing": False, "action": action_show(s, action_id) if plus else s.require("actions", action_id), "instruction": "Prepared locally only. Execute only under the project authorization workflow, then record observed evidence. This CLI does not contact LinkedIn."}


def receipt(s, action_id, state, evidence, remote_url=None, remote_id=None, observed_at=None, reconcile=False, observed_details=None):
    if state not in ("confirmed", "uncertain", "failed", "cancelled"):
        raise Error("Unsupported receipt state.")
    if not evidence.strip():
        raise Error("A receipt requires observed evidence, not an intended outcome.")
    if state == "confirmed" and not (remote_url or remote_id):
        raise Error("Confirmed actions require a remote URL or remote ID.")
    remote_url = canonical_url(remote_url) if remote_url else None
    observed_at = timestamp(observed_at) if observed_at else now()
    with s.transaction():
        row = s.require("actions", action_id)
        detail_snapshot = engagement.verify_outreach_receipt(s, row, observed_details) if state == "confirmed" and row["kind"] in engagement.OUTREACH else None
        if row["state"] == "published":
            raise Error("Published history is immutable; record a separate correction.")
        if reconcile:
            if state == "uncertain":
                raise Error("Reconciliation must establish confirmed, failed or cancelled state.")
            if row["state"] == "confirmed" and state != "cancelled":
                raise Error("A confirmed schedule can only be reconciled as cancelled or marked published.")
            if row["state"] == "confirmed" and row["kind"] != "schedule":
                raise Error("Completed actions cannot be cancelled locally.")
        elif row["state"] != "prepared":
            raise Error("Action is " + row["state"] + "; use action reconcile with remote-state evidence, not another attempt.")
        if row["content_id"] and state == "confirmed":
            competing = s.one("SELECT id FROM actions WHERE content_id=? AND id!=? AND kind IN ('schedule','publish') AND state IN ('prepared','uncertain','confirmed','published')", (row["content_id"], action_id))
            if competing:
                raise Error("Another publishing action is active: " + competing["id"] + ". Resolve the competing remote state first.")
            if fingerprint(s, row["content_id"]) != row["fingerprint"]:
                raise Error("Registered files changed after preparation. Resolve the remote action before correcting records.")
        final_state = "published" if state == "confirmed" and row["kind"] == "publish" else state
        receipt_id = ident("receipt")
        s.insert("receipts", dict(id=receipt_id, action_id=action_id, state=final_state, evidence=evidence,
                                  remote_url=remote_url, remote_id=remote_id, observed_at=observed_at, created_at=now()))
        if detail_snapshot:
            s.insert("receipt_details", dict(receipt_id=receipt_id, evidence_json=detail_snapshot, sha256=digest(detail_snapshot)))
        s.db.execute("UPDATE actions SET state=?,remote_url=COALESCE(?,remote_url),remote_id=COALESCE(?,remote_id),updated_at=? WHERE id=?", (final_state, remote_url, remote_id, now(), action_id))
        if row["kind"] == "inmail":
            engagement.receipt_credit(s, action_id, state)
        if row["content_id"]:
            content_state = {"published": "published", "confirmed": "scheduled", "uncertain": "uncertain", "failed": "approved", "cancelled": "draft"}[final_state]
            competing = s.one("SELECT id FROM actions WHERE content_id=? AND id!=? AND kind IN ('schedule','publish') AND state IN ('prepared','uncertain','confirmed','published')", (row["content_id"], action_id))
            # Historical reconciliation must not overwrite a newer version/authority.
            same_version = False
            try:
                same_version = fingerprint(s, row["content_id"]) == row["fingerprint"]
            except Error:
                pass
            if not competing and same_version:
                s.db.execute("UPDATE content SET status=?,updated_at=? WHERE id=?", (content_state, now(), row["content_id"]))
        elif state == "confirmed":
            add_interaction(s, row["target_url"], row["kind"], observed_at, evidence, row["response"], row["parent_context"], relationship_id=row["relationship_id"], action_id=action_id, transaction=False)
    return action_show(s, action_id)


def publication(s, action_id, evidence, remote_url, observed_at=None):
    instant = timestamp(observed_at) if observed_at else now()
    remote_url = canonical_url(remote_url)
    if not evidence.strip():
        raise Error("Publication requires observed evidence.")
    with s.transaction():
        row = s.require("actions", action_id)
        if row["kind"] != "schedule" or row["state"] != "confirmed":
            raise Error("Only a confirmed schedule can be marked published.")
        if row["scheduled_at"] and instant < row["scheduled_at"]:
            raise Error("Publication observation precedes the scheduled instant; reconcile the actual schedule first.")
        s.insert("receipts", dict(id=ident("receipt"), action_id=action_id, state="published", evidence=evidence,
                                  remote_url=remote_url, observed_at=instant, created_at=now()))
        s.db.execute("UPDATE actions SET state='published',remote_url=?,updated_at=? WHERE id=?", (remote_url, now(), action_id))
        s.db.execute("UPDATE content SET status='published',updated_at=? WHERE id=?", (now(), row["content_id"]))
    return action_show(s, action_id)


def retry(s, action_id, evidence):
    if not evidence.strip():
        raise Error("Retry requires evidence that the preceding attempt did not take effect remotely.")
    with s.transaction():
        row = s.require("actions", action_id)
        if row["state"] not in ("failed", "cancelled"):
            raise Error("Only failed/cancelled actions may retry; uncertain outcomes must be reconciled first.")
        if row["kind"] == "schedule" and row["scheduled_at"] and row["scheduled_at"] <= now():
            raise Error("The scheduled instant has passed. Assign a new slot and obtain approval before preparing a new action.")
        if row["content_id"]:
            if fingerprint(s, row["content_id"]) != row["fingerprint"]:
                raise Error("Content changed; approve and prepare the new version instead.")
            other = s.one("SELECT id FROM actions WHERE content_id=? AND id!=? AND state IN ('prepared','uncertain','confirmed','published')", (row["content_id"], action_id))
            if other:
                raise Error("Another action is active: " + other["id"])
        detail = s.one("SELECT * FROM action_details WHERE action_id=?", (action_id,))
        if detail:
            engagement.check_action(s, action_id, live=False)
            engagement.active_session(s, detail["session_id"], row["kind"])
            if row["kind"] in engagement.OUTREACH:
                engagement.check_outreach(s, row["kind"], row["target_url"], row["relationship_id"], detail["opportunity_id"], json.loads(detail["details_json"]), action_id)
            if row["kind"] == "inmail":
                engagement.reserve_credit(s, action_id, detail["session_id"])
            if row["kind"] == "repost":
                engagement.check_repost_budget(s, detail["session_id"], action_id)
        s.insert("receipts", dict(id=ident("receipt"), action_id=action_id, state="retry_authorized", evidence=evidence, observed_at=now(), created_at=now()))
        s.db.execute("UPDATE actions SET state='prepared',attempt=attempt+1,updated_at=? WHERE id=?", (now(), action_id))
    return action_show(s, action_id)


def action_show(s, action_id):
    row = s.require("actions", action_id)
    row["receipts"] = s.all("SELECT * FROM receipts WHERE action_id=? ORDER BY created_at,id", (action_id,))
    for saved_receipt in row["receipts"]:
        saved_receipt["observed_details"] = s.one("SELECT * FROM receipt_details WHERE receipt_id=?", (saved_receipt["id"],))
    row["details"] = s.one("SELECT * FROM action_details WHERE action_id=?", (action_id,))
    row["inmail_reservation"] = s.one("SELECT * FROM inmail_reservations WHERE action_id=?", (action_id,))
    return row


def add_interaction(s, target, kind, occurred_at, source, response=None, context=None, relationship_id=None,
                    outcome=None, action_id=None, transaction=True):
    if transaction:
        with s.transaction():
            return add_interaction(s, target, kind, occurred_at, source, response, context, relationship_id, outcome, action_id, False)
    target = canonical_url(target)
    instant = timestamp(occurred_at)
    if kind not in ("comment", "reply", "like", "visit", "conversation", "repost", "reaction", "dm", "inmail"):
        raise Error("Invalid interaction kind.")
    if not source.strip():
        raise Error("Interactions require source evidence.")
    if relationship_id:
        s.require("relationships", relationship_id)
    else:
        person = s.one("SELECT id FROM relationships WHERE profile_url=?", (target,))
        relationship_id = person["id"] if person else None
    key = digest(dump([target, kind, instant, response]))
    existing = s.one("SELECT * FROM interactions WHERE dedup_key=?", (key,))
    if existing:
        return {"existing": True, "interaction": existing}
    record = dict(id=ident("interaction"), relationship_id=relationship_id, action_id=action_id,
                  target_url=target, kind=kind, response=response, parent_context=context, state="confirmed",
                  occurred_at=instant, source=source, outcome=outcome, dedup_key=key, created_at=now())
    s.insert("interactions", record)
    return record
