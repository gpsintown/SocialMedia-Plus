"""Plus-mode evidence, bounded outreach and credit reservations. No remote calls."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .store import Error, canonical_url, digest, dump, ident, now, timestamp

PLUS_KINDS = ("reaction", "repost", "dm", "inmail")
OUTREACH = ("dm", "inmail")
TABLES = ("engagement_sessions", "opportunities", "action_details", "receipt_details", "inmail_balances", "inmail_reservations")


def policy(s):
    result = {"inmail": {"per_session": 2, "rolling_7_days": 5, "reserve": 1, "balance_max_age_minutes": 60},
              "outreach": {"company_cooldown_days": 7, "job_observation_max_age_minutes": 60},
              "engage": {"reposts_per_session": 1, "reposts_rolling_7_days": 2}, "resume": {}}
    numeric_keys = {section: tuple(values) for section, values in result.items() if section != "resume"}
    path = s.root / "config/engagement-plus.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise Error("config/engagement-plus.json must be an object.")
        for section in result:
            if section in value:
                if not isinstance(value[section], dict):
                    raise Error("Invalid engagement-plus policy section: " + section)
                result[section].update(value[section])
    for section, names in numeric_keys.items():
        for name in names:
            value = result[section][name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise Error("Plus policy values must be positive integers: " + name)
    return result


def session_start(s, mode, minutes, authorization, preview=False):
    if mode not in ("engage_plus", "recruiter_plus") or not 1 <= minutes <= 120:
        raise Error("Use engage_plus/recruiter_plus and a 1–120 minute session.")
    if not authorization.strip():
        raise Error("Record the actual current user invocation as authorization evidence.")
    started = now()
    row = dict(id=ident("session"), mode=mode, authorization=authorization, preview=int(preview),
               started_at=started, ends_at=(datetime.fromisoformat(started) + timedelta(minutes=minutes)).isoformat(timespec="seconds"))
    with s.transaction():
        s.insert("engagement_sessions", row)
    return session_show(s, row["id"])


def session_show(s, session_id):
    row = s.require("engagement_sessions", session_id)
    row["actions"] = s.all("SELECT a.id,a.kind,a.state,a.target_url FROM actions a JOIN action_details d ON d.action_id=a.id WHERE d.session_id=? ORDER BY a.created_at", (session_id,))
    return row


def session_end(s, session_id):
    with s.transaction():
        s.require("engagement_sessions", session_id)
        s.db.execute("UPDATE engagement_sessions SET closed_at=COALESCE(closed_at,?) WHERE id=?", (now(), session_id))
    return session_show(s, session_id)


def active_session(s, session_id, kind):
    if kind in OUTREACH:
        settings = policy(s)
        if settings["outreach"].get("enabled") is not True:
            raise Error("Enable outreach in local config/engagement-plus.json after configuring your hiring preferences.")
        if kind == "inmail" and settings["inmail"].get("enabled") is not True:
            raise Error("InMail is disabled in local config/engagement-plus.json.")
    if not session_id:
        raise Error("Plus actions require --session from the current live invocation.")
    row = s.require("engagement_sessions", session_id)
    if row["preview"] or row["closed_at"] or not row["started_at"] <= now() < row["ends_at"]:
        raise Error("This session is preview, closed or expired; no live action may be prepared or submitted.")
    allowed = {"engage_plus": ("comment", "reply", "like", "visit", "reaction", "repost"),
               "recruiter_plus": ("comment", "reply", "like", "visit", "reaction", "dm", "inmail")}
    if kind not in allowed.get(row["mode"], ()):
        raise Error("Action kind is outside this plus mode's authorized action set.")
    return row


def _required_text(data, field):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise Error("Opportunity requires observed " + field + ".")
    return value.strip()


def opportunity_add(s, file):
    raw = Path(file).expanduser().read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise Error("Opportunity file must be a JSON object.")
    url = canonical_url(_required_text(data, "job_url"))
    if not re.fullmatch(r"https://www\.linkedin\.com/jobs/view/(?:[^/?]+-)?\d+(?:\?[^#]*)?", url):
        raise Error("Use the observed LinkedIn /jobs/view/ URL for this opening.")
    # The job identity is the displayed numeric ID, not tracking or a title slug.
    job_id = re.search(r"(\d+)(?:\?.*)?$", url).group(1)
    url = "https://www.linkedin.com/jobs/view/" + job_id
    observed = timestamp(_required_text(data, "observed_at"))
    if observed > now():
        raise Error("An opportunity observation cannot be in the future.")
    for field in ("title", "company", "country", "posting_evidence", "applicant_evidence", "match_evidence"):
        _required_text(data, field)
    countries = policy(s)["outreach"].get("countries", [])
    if not isinstance(countries, list) or not countries or any(not isinstance(country, str) or not country.strip() for country in countries):
        raise Error("Configure outreach.countries in config/engagement-plus.json before recording hiring opportunities.")
    if data["country"] not in countries:
        raise Error("The observed country is outside the configured outreach.countries selection.")
    if not isinstance(data.get("close_match"), bool):
        raise Error("close_match must be true or false, supported by match_evidence.")
    if data.get("applicant_indicator_type") not in ("exact_applicants", "verified_under_10_filter", "apply_clicks", "unknown"):
        raise Error("Record applicant_indicator_type as exact_applicants, verified_under_10_filter, apply_clicks or unknown.")
    for field in ("applicants_count", "applicants_upper_bound"):
        value = data.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise Error(field + " must be a non-negative integer or null; unknown is not zero.")
    age = data.get("posted_age_hours_upper_bound")
    if age is not None and (isinstance(age, bool) or not isinstance(age, (int, float)) or not 0 <= age <= 100000):
        raise Error("posted_age_hours_upper_bound must be a non-negative finite number or null.")
    if data.get("posted_at"):
        data["posted_at"] = timestamp(data["posted_at"])
        if data["posted_at"] > observed:
            raise Error("Posting time cannot follow its observation.")
    contact_id = data.get("contact_id")
    if contact_id:
        s.require("relationships", contact_id)
        _required_text(data, "contact_evidence")
    data.update(job_url=url, observed_at=observed)
    normalized = dump(data)
    checksum = digest(normalized)
    with s.transaction():
        old = s.one("SELECT id FROM opportunities WHERE sha256=?", (checksum,))
        if old:
            return dict(existing=True, opportunity=opportunity_show(s, old["id"]))
        item = dict(id=ident("job"), job_url=url, company=data["company"], title=data["title"], country=data["country"],
                    observed_at=observed, contact_id=contact_id, evidence_json=normalized,
                    source_path="data/opportunities/" + checksum + ".json", sha256=checksum, created_at=now())
        path = s.managed(item["source_path"])
        if path.exists():
            s.read_checked(item["source_path"], checksum)
        else:
            s.write(item["source_path"], normalized, exclusive=True)
        s.insert("opportunities", item)
    return dict(existing=False, opportunity=opportunity_show(s, item["id"]))


def opportunity_show(s, opportunity_id):
    row = s.require("opportunities", opportunity_id)
    s.read_checked(row["source_path"], row["sha256"])
    row["evidence"] = json.loads(row.pop("evidence_json"))
    row["eligibility"] = eligibility(row["evidence"], policy(s)["outreach"]["job_observation_max_age_minutes"])
    return row


def eligibility(data, max_age_minutes=60):
    elapsed = (datetime.fromisoformat(now()) - datetime.fromisoformat(data["observed_at"])).total_seconds() / 3600
    if data.get("posted_at"):
        age = (datetime.fromisoformat(now()) - datetime.fromisoformat(data["posted_at"])).total_seconds() / 3600
    else:
        age = data.get("posted_age_hours_upper_bound")
        age = age + elapsed if age is not None else None
    count = data.get("applicants_count")
    upper = data.get("applicants_upper_bound")
    applicants = count if count is not None else upper
    reasons = []
    if age is None or not 0 <= age < 24:
        reasons.append("Last-24-hours posting is unverified or has expired.")
    if applicants is None or applicants >= 10:
        reasons.append("Fewer than 10 applicants is unverified or outside the requested range.")
    if data.get("applicant_indicator_type") not in ("exact_applicants", "verified_under_10_filter"):
        reasons.append("Apply clicks or unknown applicant indicators do not establish fewer than 10 applicants.")
    if data.get("applicant_indicator_type") == "exact_applicants" and count is None:
        reasons.append("An exact applicant observation requires its visible numeric count.")
    if data.get("applicant_indicator_type") == "verified_under_10_filter" and upper != 9:
        reasons.append("A verified under-10 filter requires an explicit upper bound of 9 for this listing.")
    if count is not None and upper is not None and count > upper:
        reasons.append("Applicant evidence is inconsistent.")
    if data.get("close_match") is not True:
        reasons.append("A close resume match has not been established.")
    if elapsed < 0 or elapsed * 60 > max_age_minutes:
        reasons.append("Refresh the visible job evidence before outreach; this observation has expired.")
    return dict(eligible=not reasons, reasons=reasons, maximum_age_hours=age,
                observed_applicant_count=count, observed_applicant_upper_bound=upper,
                note="Visible applicant indicators are observations, not verified completed-application totals.")


def observe_balance(s, balance, evidence, observed_at=None):
    if isinstance(balance, bool) or not isinstance(balance, int) or balance < 0 or not evidence.strip():
        raise Error("InMail balance needs a non-negative observed integer and source evidence.")
    instant = timestamp(observed_at) if observed_at else now()
    if instant > now():
        raise Error("Balance observation cannot be in the future.")
    item = dict(id=ident("balance"), balance=balance, observed_at=instant, evidence=evidence, created_at=now())
    with s.transaction():
        s.insert("inmail_balances", item)
    return item


def inmail_status(s, session_id=None):
    limits = policy(s)["inmail"]
    instant = now()
    cutoff = (datetime.fromisoformat(instant) - timedelta(days=7)).isoformat(timespec="seconds")
    balance = s.one("SELECT * FROM inmail_balances ORDER BY observed_at DESC,rowid DESC LIMIT 1")
    holds = s.all("SELECT * FROM inmail_reservations WHERE state IN ('reserved','uncertain')")
    spent = s.all("SELECT * FROM inmail_reservations WHERE state='spent'")
    weekly = len(holds) + sum(row["reserved_at"] >= cutoff for row in spent)
    session_used = None if session_id is None else sum(row["session_id"] == session_id for row in holds + spent)
    fresh = balance is not None and 0 <= (datetime.fromisoformat(instant) - datetime.fromisoformat(balance["observed_at"])).total_seconds() <= limits["balance_max_age_minutes"] * 60
    # Every unresolved hold is deducted even if a later visible balance might already
    # reflect it. This is deliberately conservative until its outcome is reconciled.
    charged_since = sum(row["updated_at"] >= balance["observed_at"] for row in spent) if balance else 0
    remaining = max(0, balance["balance"] - len(holds) - charged_since) if fresh else None
    allowance = 0 if remaining is None else max(0, min(remaining - limits["reserve"], limits["rolling_7_days"] - weekly, limits["per_session"] - (session_used or 0)))
    return dict(observation=balance, balance_fresh=fresh, outstanding_reservations=len(holds),
                estimated_available_after_reservations=remaining, rolling_7_day_used_or_reserved=weekly,
                session_used_or_reserved=session_used, additional_credits_allowed=allowance,
                policy=limits,
                note="No inferred credit refunds. Refresh visible balance; uncertain attempts remain reserved.")


def reserve_credit(s, action_id, session_id):
    active_session(s, session_id, "inmail")
    status = inmail_status(s, session_id)
    if status["additional_credits_allowed"] < 1:
        raise Error("InMail spending blocked: unknown/stale balance, reserve floor, session cap or rolling seven-day cap.")
    s.db.execute("""INSERT INTO inmail_reservations(action_id,session_id,balance_id,state,reserved_at,updated_at)
                    VALUES (?,?,?,'reserved',?,?) ON CONFLICT(action_id) DO UPDATE SET
                    session_id=excluded.session_id,balance_id=excluded.balance_id,state='reserved',
                    reserved_at=excluded.reserved_at,updated_at=excluded.updated_at""",
                 (action_id, session_id, status["observation"]["id"], now(), now()))


def check_repost_budget(s, session_id, exclude_action=None):
    limits = policy(s)["engage"]
    cutoff = (datetime.fromisoformat(now()) - timedelta(days=7)).isoformat(timespec="seconds")
    rows = s.all("""SELECT d.session_id FROM actions a JOIN action_details d ON d.action_id=a.id
                   WHERE a.kind='repost' AND a.id!=? AND
                   (a.state IN ('prepared','uncertain') OR (a.state='confirmed' AND a.updated_at>=?))""", (exclude_action or "", cutoff))
    if len(rows) >= limits["reposts_rolling_7_days"] or sum(row["session_id"] == session_id for row in rows) >= limits["reposts_per_session"]:
        raise Error("Repost session or rolling seven-day cap reached; unresolved attempts still count.")


def check_outreach(s, kind, target, relationship_id, opportunity_id, details, exclude_action=None):
    if not relationship_id or not opportunity_id:
        raise Error("DM/InMail requires a known --relationship and --opportunity.")
    person = s.require("relationships", relationship_id)
    if target != person["profile_url"]:
        raise Error("DM/InMail target must be the linked recipient's canonical profile URL.")
    job = opportunity_show(s, opportunity_id)
    if job["contact_id"] != relationship_id or not job["evidence"].get("contact_evidence"):
        raise Error("The recipient must be the contact actually linked to the observed opening.")
    if not job["eligibility"]["eligible"]:
        raise Error("Job is not eligible for outreach: " + " ".join(job["eligibility"]["reasons"]))
    if not isinstance(details.get("direct_dm_available"), bool) or not details.get("channel_evidence") or not details.get("selection_evidence"):
        raise Error("Outreach details require direct_dm_available, channel_evidence and selection_evidence.")
    if kind == "inmail" and details["direct_dm_available"]:
        raise Error("Use the available free DM route before spending an InMail credit.")
    if kind == "dm" and not details["direct_dm_available"]:
        raise Error("A DM requires observed free direct-message access.")
    cutoff = (datetime.fromisoformat(now()) - timedelta(days=policy(s)["outreach"]["company_cooldown_days"])).isoformat(timespec="seconds")
    prior = s.one("""SELECT a.id FROM actions a JOIN action_details d ON d.action_id=a.id
                    LEFT JOIN opportunities j ON j.id=d.opportunity_id
                    WHERE a.kind IN ('dm','inmail') AND a.id!=? AND
                    (a.state IN ('prepared','uncertain') OR (a.state='confirmed' AND a.updated_at>=?)) AND
                    (a.relationship_id=? OR j.job_url=? OR lower(trim(j.company))=lower(trim(?))) LIMIT 1""",
                  (exclude_action or "", cutoff, relationship_id, job["job_url"], job["company"]))
    if prior:
        raise Error("Existing or recent outreach already covers this contact/job/company: " + prior["id"] + ". Reconcile uncertainty or await a relevant reply; do not send another cold approach.")


def preflight(s, kind, authority, target, response, context, relationship_id, session_id, opportunity_id, attachment, details):
    active_session(s, session_id, kind)
    if authority != "native_linkedin":
        raise Error("Plus actions currently use the actual Chrome/native_linkedin route.")
    if not isinstance(details, dict) or not context or not context.strip():
        raise Error("Plus actions need observed context and a details JSON object.")
    if kind in ("dm", "inmail", "repost") and (not response or not response.strip()):
        raise Error("DM, InMail and attributed reposts require exact final response text.")
    if kind == "reaction" and details.get("reaction") != "like":
        raise Error("The currently authorized reaction is like; record details.reaction='like'.")
    if kind == "repost":
        check_repost_budget(s, session_id)
    if kind in OUTREACH:
        check_outreach(s, kind, target, relationship_id, opportunity_id, details)
        if details.get("attachment_supported") is not True:
            raise Error("Hold outreach until the selected composer visibly supports the resume attachment.")
        if kind == "inmail" and not str(details.get("subject", "")).strip():
            raise Error("InMail requires the exact final subject in its details JSON.")
        if not attachment:
            raise Error("Recruiter outreach requires the reviewed master resume PDF attachment.")
    elif attachment or opportunity_id:
        raise Error("Resume attachments and opportunity links are only for DM/InMail actions.")
    attachment_data = None
    if attachment:
        path = Path(attachment).expanduser().resolve()
        raw = path.read_bytes()
        if path.suffix.lower() != ".pdf" or not raw.startswith(b"%PDF-"):
            raise Error("Resume attachment must be a readable PDF.")
        expected = policy(s)["resume"]
        if expected.get("sha256") and digest(raw) != expected["sha256"]:
            raise Error("Attachment is not the configured reviewed master resume version.")
        if expected.get("path"):
            s.read_checked(expected["path"], expected.get("sha256") or digest(raw))
        attachment_data = dict(raw=raw, sha256=digest(raw), name=path.name)
    return attachment_data


def details_fingerprint(action, details):
    signed = {key: action.get(key) for key in ("kind", "target_url", "response", "parent_context", "relationship_id", "authority")}
    signed.update({key: details.get(key) for key in ("session_id", "opportunity_id", "details_json", "attachment_sha256", "attachment_name")})
    return digest(dump(signed))


def save_details(s, action, session_id, opportunity_id, details, attachment):
    record = dict(action_id=action["id"], session_id=session_id, opportunity_id=opportunity_id, details_json=dump(details))
    if attachment:
        record.update(attachment_path="data/action-attachments/" + action["id"] + ".pdf",
                      attachment_sha256=attachment["sha256"], attachment_name=attachment["name"])
        s.write(record["attachment_path"], attachment["raw"], exclusive=True)
    record["fingerprint"] = details_fingerprint(action, record)
    s.insert("action_details", record)
    if action["kind"] == "inmail":
        reserve_credit(s, action["id"], session_id)


def check_action(s, action_id, live=True):
    action = s.require("actions", action_id)
    detail = s.one("SELECT * FROM action_details WHERE action_id=?", (action_id,))
    if not detail:
        if action["kind"] in PLUS_KINDS:
            raise Error("Plus action is missing its session/evidence record.")
        return {"id": action_id, "state": action["state"], "details": None}
    if details_fingerprint(action, detail) != detail["fingerprint"]:
        raise Error("Action content or immutable evidence changed after preparation.")
    if detail["attachment_path"]:
        s.read_checked(detail["attachment_path"], detail["attachment_sha256"])
    if live:
        if action["state"] != "prepared":
            raise Error("Only a prepared action may be submitted. Reconcile uncertainty before retrying.")
        active_session(s, detail["session_id"], action["kind"])
        if action["kind"] in OUTREACH:
            check_outreach(s, action["kind"], action["target_url"], action["relationship_id"], detail["opportunity_id"], json.loads(detail["details_json"]), action_id)
        if action["kind"] == "repost":
            check_repost_budget(s, detail["session_id"], action_id)
        if action["kind"] == "inmail":
            reservation = s.one("SELECT * FROM inmail_reservations WHERE action_id=?", (action_id,))
            if not reservation or reservation["state"] != "reserved":
                raise Error("InMail is missing an active credit reservation.")
            budget = inmail_status(s, detail["session_id"])
            if not budget["balance_fresh"]:
                raise Error("Refresh the visible InMail balance before submitting.")
            if (budget["estimated_available_after_reservations"] < budget["policy"]["reserve"] or
                    budget["session_used_or_reserved"] > budget["policy"]["per_session"] or
                    budget["rolling_7_day_used_or_reserved"] > budget["policy"]["rolling_7_days"]):
                raise Error("Current InMail balance/caps no longer cover this reservation while preserving the reserve.")
    return dict(id=action_id, state=action["state"], details=detail, integrity_verified=True,
                instruction="Verify the actual account, recipient/target, exact text and registered attachment in Chrome before submitting once. This check does not send.")


def receipt_credit(s, action_id, state):
    mapping = {"confirmed": "spent", "uncertain": "uncertain", "failed": "released", "cancelled": "released"}
    s.db.execute("UPDATE inmail_reservations SET state=?,updated_at=? WHERE action_id=?", (mapping[state], now(), action_id))


def verify_outreach_receipt(s, action, observed):
    check_action(s, action["id"], live=False)
    if not isinstance(observed, dict):
        raise Error("Confirmed DM/InMail requires --observed-details-file containing actual target_url, response, attachment_sha256 and InMail subject.")
    detail = s.one("SELECT * FROM action_details WHERE action_id=?", (action["id"],))
    if not detail:
        raise Error("Outreach is missing its exact preparation record.")
    expected = json.loads(detail["details_json"])
    if not observed.get("target_url") or canonical_url(observed["target_url"], profile=True) != action["target_url"]:
        raise Error("Observed recipient does not match the prepared target.")
    if observed.get("response") != action["response"] or observed.get("attachment_sha256") != detail["attachment_sha256"]:
        raise Error("Observed message body or attachment hash differs from the prepared version; keep the attempt uncertain until reconciled.")
    if action["kind"] == "inmail" and observed.get("subject") != expected.get("subject"):
        raise Error("Observed InMail subject differs from the prepared version.")
    return dump(observed)
