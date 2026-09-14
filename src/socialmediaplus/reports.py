"""Derived content plans and measured reports. No generated personal anecdotes."""
import csv
import io
import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from . import __version__
from .network import due
from .followers import coverage as follower_coverage
from .store import Error, canonical_url, digest, dump, ident, now, timestamp
from .workflow import fingerprint
from . import engagement


def history_target(value):
    """Normalize observed target identity, without inferring alternate post IDs."""
    canonical = canonical_url(value)
    parsed = urlsplit(canonical)
    if parsed.hostname != "www.linkedin.com":
        raise Error("History target must be a LinkedIn HTTPS URL.")
    # Exports percent-encode the colons in a feed URN; the browser may not.
    # Never decode arbitrary path characters or collapse activity and ugcPost.
    path = parsed.path
    urn_path = re.sub(r"%3a", ":", path, flags=re.IGNORECASE)
    if re.fullmatch(r"/feed/update/urn:li:(activity|ugcPost|share):[0-9]+", urn_path):
        path = urn_path
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def history_metadata(raw_json):
    try:
        raw = json.loads(raw_json)
    except (ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    metadata = raw.get("_export", {})
    if not isinstance(metadata, dict):
        metadata = {}
    date_value = metadata.get("raw_date")
    if date_value is None:
        date_value = next((raw[k] for k in ("date", "createdat", "publisheddate", "time", "timestamp") if raw.get(k)), None)
    return metadata, date_value


def history_sort_date(occurred_at, raw_json):
    # The key is an approximate calendar ordering aid, never a new UTC instant.
    value = occurred_at or history_metadata(raw_json)[1]
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return None


def history_list(s, kinds=None, target=None, query=None, limit=20):
    """Bounded local evidence lookup; does not create or confirm interactions."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise Error("History limit must be between 1 and 100.")
    if kinds is not None and (not isinstance(kinds, (list, tuple)) or len(kinds) > 20 or
                              any(not isinstance(k, str) or not k or len(k) > 64 for k in kinds)):
        raise Error("Use at most 20 history kinds, each 1–64 characters.")
    if query is not None and (not isinstance(query, str) or not query.strip() or len(query) > 200):
        raise Error("History query must contain 1–200 characters.")
    kinds = list(dict.fromkeys(kinds or []))
    where, params = [], []
    if kinds:
        where.append("kind IN (" + ",".join("?" for _ in kinds) + ")")
        params.extend(kinds)
    normalized_target = history_target(target) if target is not None else None
    if normalized_target is not None:
        def stored_target(value):
            try:
                return history_target(value) if value else None
            except (Error, ValueError, TypeError):
                return None
        s.db.create_function("smp_history_target", 1, stored_target, deterministic=True)
        where.append("smp_history_target(target_url)=?")
        params.append(normalized_target)
    if query is not None:
        # instr is literal: %, _ and SQL-looking strings are data, not wildcards.
        where.append("instr(lower(COALESCE(text,'')),lower(?))>0")
        params.append(query)
    s.db.create_function("smp_history_date", 2, history_sort_date, deterministic=True)
    sql = "SELECT id,kind,target_url,text,occurred_at,source,raw_json,smp_history_date(occurred_at,raw_json) AS ordering_date FROM history"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ordering_date IS NULL,ordering_date DESC,id LIMIT ?"
    rows = s.all(sql, tuple(params + [limit + 1]))
    result = []
    for row in rows[:limit]:
        metadata, date_value = history_metadata(row.pop("raw_json"))
        row["raw_date"] = date_value
        row["date_status"] = metadata.get("date_status", "normalization_not_documented" if date_value else "missing")
        row["time_zone"] = metadata.get("time_zone")
        row["ordering_date_basis"] = ("normalized_occurred_at" if row["occurred_at"] else "original_source_date") if row["ordering_date"] else "unavailable"
        row["export_evidence"] = {key: metadata[key] for key in
                                  ("record_number", "line_start", "line_end", "parsing", "recovery_limits")
                                  if key in metadata}
        if isinstance(metadata.get("source_rows"), list):
            row["export_evidence"]["source_row_count"] = len(metadata["source_rows"])
        if isinstance(metadata.get("media_urls"), list):
            row["export_evidence"]["media_urls"] = [url for url in metadata["media_urls"] if isinstance(url, str)]
        row["recovered_record"] = metadata.get("parsing") == "final_column_boundary_recovery"
        row["evidence_type"] = "imported_history_not_live_receipt"
        result.append(row)
    return {
        "records": result, "returned": len(result), "has_more": len(rows) > limit,
        "filters": {"kinds": kinds, "target": normalized_target, "query": query, "limit": limit},
        "privacy": "private_local_history",
        "note": "Imported history is evidence of exported activity, not a current live receipt or proof of a relationship. A comment's exported target may identify only its parent post. An empty exact-target match does not rule out an unlinked or differently identified record.",
        "ordering": "Approximate descending calendar order: normalized occurred_at where available, otherwise a parseable original ISO source date. Unknown dates appear last. Source-local dates are not UTC instants; mixed or unspecified zones prevent exact chronology.",
    }


def status(s):
    return {
        "version": __version__, "root": str(s.root), "database": str(s.db_path),
        "profile_url": s.settings["profile_url"], "active_platforms": s.settings["active_platforms"],
        "publishing": "local_records_only_no_remote_execution",
        "content": s.all("SELECT status,COUNT(*) AS count FROM content GROUP BY status"),
        "relationships": s.one("SELECT COUNT(*) AS total,COUNT(CASE WHEN bucket='unclassified' THEN 1 END) AS unclassified FROM relationships"),
        "network_coverage": coverage(s),
        "metrics": s.all("SELECT availability,COUNT(*) AS count FROM metrics GROUP BY availability"),
        "history": s.all("SELECT kind,COUNT(*) AS count FROM history GROUP BY kind"),
        "unresolved_actions": s.all("SELECT id,kind,state,authority,content_id,target_url FROM actions WHERE state IN ('prepared','uncertain') ORDER BY created_at"),
        "imports": s.all("SELECT id,kind,stored_path,imported_at FROM imports ORDER BY imported_at DESC"),
        "inmail": engagement.inmail_status(s),
    }


def coverage(s):
    registered = s.one("SELECT COUNT(*) AS n FROM relationship_memberships WHERE membership='connection'")["n"]
    unresolved = s.one("SELECT COUNT(*) AS n FROM history WHERE kind='unresolved_connections'")["n"]
    baseline_path = s.root / "profile/baseline.json"
    expected, source = None, None
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        for item in baseline.get("metrics", []):
            if item.get("name") == "connections" and isinstance(item.get("value"), (int, float)):
                expected, source = item["value"], str(baseline_path)
    completeness = "unknown" if expected is None else ("inventory_with_unresolved_urls" if registered < expected and registered + unresolved >= expected else ("partial_inventory" if registered < expected else "count_matches_observation_not_guaranteed_current"))
    return {"registered_connections": registered, "expected_connections_observed": expected, "expected_count_source": source,
            "unresolved_connection_records": unresolved, "known_plus_unresolved": registered + unresolved,
            "completeness": completeness, "note": "Connection counts and incoming-follower observations are separate, overlapping populations; neither establishes current activity.",
            **follower_coverage(s)}


def doctor(s):
    issues = []
    check = s.one("PRAGMA quick_check")
    if list(check.values()) != ["ok"]:
        issues.append({"kind": "database", "detail": check})
    for row in s.all("SELECT path,sha256 FROM versions UNION ALL SELECT path,sha256 FROM assets UNION ALL SELECT attachment_path,attachment_sha256 FROM action_details WHERE attachment_path IS NOT NULL UNION ALL SELECT source_path,sha256 FROM opportunities"):
        try:
            s.read_checked(row["path"], row["sha256"])
        except Error as exc:
            issues.append({"kind": "file_integrity", "detail": str(exc)})
    for row in s.all("SELECT action_id FROM action_details"):
        try:
            engagement.check_action(s, row["action_id"], live=False)
        except Error as exc:
            issues.append({"kind": "action_integrity", "detail": str(exc)})
    for row in s.all("SELECT * FROM receipt_details"):
        if digest(row["evidence_json"]) != row["sha256"]:
            issues.append({"kind": "receipt_integrity", "detail": row["receipt_id"]})
    for row in s.all("SELECT * FROM content WHERE status='approved'"):
        try:
            fp = fingerprint(s, row["id"])
            if not s.one("SELECT id FROM approvals WHERE content_id=? AND fingerprint=?", (row["id"], fp)):
                issues.append({"kind": "stale_approval", "detail": row["id"]})
        except Error:
            pass
    if s.settings.get("active_platforms") != ["linkedin"]:
        issues.append({"kind": "phase_scope", "detail": "Phase one active_platforms must be [linkedin]."})
    return {"ok": not issues, "issues": issues, "timezone": s.settings["timezone"], "xlsx_import": "stdlib OOXML reader available",
            "remote_credentials_checked": False, "remote_account_connected": "not established by this CLI",
            "unresolved_actions": status(s)["unresolved_actions"]}


def artifact(s, folder, name, data, markdown):
    # Each run is an immutable view of the current records, never a second status source.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + ident("r").split("_")[1][:6]
    base = "reports/" + folder + "/" + name + "-" + stamp
    return {"json": s.write(base + ".json", json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", True),
            "markdown": s.write(base + ".md", markdown, True), "summary": data}


def local_day(s):
    return datetime.now(ZoneInfo(s.settings["timezone"])).date()


def plan_week(s, start=None):
    start_date = date.fromisoformat(start) if start else local_day(s) + timedelta(days=(7 - local_day(s).weekday()) % 7)
    pilot = s.settings.get("pilot", {})
    count = pilot.get("feed_posts_per_week", s.settings.get("weekly_post_count", 3))
    if not isinstance(count, int) or not 1 <= count <= 7:
        raise Error("Weekly post count must be 1–7.")
    windows = pilot.get("time_windows", ["09:00", "14:00"])
    start_utc = timestamp(start_date.isoformat(), s.settings["timezone"])
    end_utc = timestamp((start_date + timedelta(days=7)).isoformat(), s.settings["timezone"])
    assigned = s.all("SELECT * FROM content WHERE scheduled_at>=? AND scheduled_at<? AND status IN ('draft','approved','scheduled','uncertain') ORDER BY scheduled_at,created_at", (start_utc, end_utc))
    unassigned = s.all("SELECT * FROM content WHERE scheduled_at IS NULL AND status IN ('draft','approved') ORDER BY created_at")
    content = assigned + unassigned[:max(0, count - len(assigned))]
    warnings = []
    if len(assigned) > count:
        warnings.append("Already assigned items exceed the configured cadence; review the load before scheduling more.")
    occupied = [row["scheduled_at"] for row in assigned]
    if len(occupied) != len(set(occupied)):
        warnings.append("Two registered items share an exact assigned instant; resolve the calendar conflict.")
    pillars = s.settings.get("content_pillars", ["Verified experience", "Practical explanation", "Grounded opinion"])
    slots = []
    for index in range(max(count, len(assigned))):
        day = start_date + timedelta(days=round(index * 6 / max(1, count - 1)))
        # Three-post default uses Monday / Wednesday / Friday.
        if count == 3:
            day = start_date + timedelta(days=index * 2)
        local = day.isoformat() + "T" + windows[index % len(windows)] + ":00"
        content_row = content[index] if index < len(content) else None
        instant = content_row["scheduled_at"] if content_row and content_row["scheduled_at"] else timestamp(local, s.settings["timezone"])
        if not (content_row and content_row["scheduled_at"]):
            while instant in occupied:
                instant = (datetime.fromisoformat(instant) + timedelta(hours=5)).isoformat(timespec="seconds")
            occupied.append(instant)
        zones = {name: datetime.fromisoformat(instant).astimezone(ZoneInfo(name)).isoformat()
                 for name in [s.settings["timezone"]] + s.settings.get("display_timezones", [])}
        slots.append({"proposed_utc": instant, "local_times": zones, "content_id": content_row["id"] if content_row else None,
                      "title": content_row["title"] if content_row else "Brief required: " + pillars[index % len(pillars)],
                      "state": content_row["status"] if content_row else "needs_brief",
                      "time_basis": "registered_slot" if content_row and content_row["scheduled_at"] else "new_proposal",
                      "evidence": json.loads(content_row["evidence_json"]) if content_row else [],
                      "next_step": "Review exact draft, sources and assets; assign its slot before approval." if content_row else "Supply one actual observation or verified source; do not invent a personal story."})
    slots.sort(key=lambda item: item["proposed_utc"])
    data = {"start_date": start_date.isoformat(), "generated_at": now(), "slots": slots, "warnings": warnings,
            "scheduling_state": "proposal_only", "timing_basis": "experimental windows, not claimed optimal posting times",
            "profile_sources": [str(p.relative_to(s.root)) for p in sorted((s.root / "profile").glob("*.md"))]}
    lines = ["# Proposed LinkedIn week — " + start_date.isoformat(), "", "Generating this report performs no scheduling or approvals. Existing assigned slots are preserved.", ""]
    lines += ["Warning: " + item for item in warnings]
    for item in slots:
        lines += ["## " + item["title"], "", "- State: " + item["state"], "- Content ID: " + (item["content_id"] or "not registered"),
                  "- Proposed time: " + item["local_times"][s.settings["timezone"]], "- Evidence: " + ("; ".join(item["evidence"]) or "required"),
                  "- Next step: " + item["next_step"], ""]
    return artifact(s, "plans", "week-" + start_date.isoformat(), data, "\n".join(lines) + "\n")


def daily(s, day=None, limit=None, buckets=None, priority="conversations", cooldown_hours=24, membership=None, exclude_membership=None):
    selected = date.fromisoformat(day) if day else local_day(s)
    as_of = None if selected == local_day(s) else selected.isoformat() + "T23:59:59"
    queue = due(s, as_of, limit, buckets, priority, cooldown_hours, membership, exclude_membership)
    scheduled = s.all("SELECT id,title,status,scheduled_at FROM content WHERE status IN ('scheduled','uncertain') ORDER BY scheduled_at")
    data = {"date": selected.isoformat(), "generated_at": now(), "relationships": queue, "network_coverage": coverage(s),
            "unresolved_actions": status(s)["unresolved_actions"], "scheduled_content": scheduled,
            "recent_interactions": s.all("SELECT * FROM interactions ORDER BY occurred_at DESC LIMIT 20"),
            "discovery_note": "Use configured topic searches or supplied links. This report has not fetched current LinkedIn activity."}
    coverage_text = str(data["network_coverage"]["registered_connections"]) + " registered profile URLs and " + str(data["network_coverage"]["unresolved_connection_records"]) + " unresolved connection records; observed total " + str(data["network_coverage"]["expected_connections_observed"] or "unavailable") + ". Coverage: " + data["network_coverage"]["completeness"] + "."
    lines = ["# LinkedIn daily session — " + selected.isoformat(), "", "Resolve uncertain actions before attempting another submission. Review replies on your own posts and active exchanges first.", "", coverage_text, ""]
    followers = data["network_coverage"]
    latest = followers["latest_follower_snapshot"]
    lines += [str(followers["registered_followers"]) + " observed incoming followers, including " + str(followers["registered_follower_connection_overlap"]) + " registered connections. Latest follower snapshot: " + (latest["completeness"] + " at " + latest["observed_at"] if latest else "unavailable") + ".", ""]
    lines += ["## Relationship review queue", ""]
    lines += ["Selection: " + queue["priority"] + "; role buckets: " + (", ".join(queue["selected_buckets"]) or "all") + ".", queue["note"], ""]
    lines += ["Membership filter: " + (", ".join(queue["selected_memberships"]) or "all observed relationship types") + ".", ""]
    lines += ["Excluded memberships: " + (", ".join(queue["excluded_memberships"]) or "none") + ".", ""]
    if queue["contact_cooldown_hours"] is not None:
        lines += ["Contact cooldown: " + str(queue["contact_cooldown_hours"]) + " hours after a recorded interaction; explicit skip/next-review settings also apply.", ""]
    for item in queue["queue"]:
        lines.append("- [" + item["name"] + "](" + item["profile_url"] + ") · " + item["bucket"] + " · " + item["reason"])
    if not queue["queue"]:
        lines.append("No eligible relationships match this session's filters and cooldown. Review classifications or use rotation priority for inventory review.")
    lines += ["", "## Action checks", ""]
    for action in data["unresolved_actions"]:
        lines.append("- " + action["id"] + " · " + action["kind"] + " · " + action["state"] + "; inspect the recorded target/remote state.")
    if not data["unresolved_actions"]:
        lines.append("No unresolved local actions.")
    lines += ["", data["discovery_note"], ""]
    return artifact(s, "daily", selected.isoformat(), data, "\n".join(lines))


def performance(s, start=None, end=None):
    rows = []
    start_day = datetime.fromisoformat(start).astimezone(ZoneInfo(s.settings["timezone"])).date().isoformat() if start else None
    end_day = datetime.fromisoformat(end).astimezone(ZoneInfo(s.settings["timezone"])).date().isoformat() if end else None
    for item in s.all("SELECT * FROM metrics ORDER BY observed_at,rowid"):
        if item["window"].startswith("day:"):
            measured_day = item["window"][4:]
            include = (start_day is None or measured_day >= start_day) and (end_day is None or measured_day < end_day)
        else:
            # Non-daily snapshots are observations, not evidence of growth during this interval.
            include = (start is None or item["observed_at"] >= start) and (end is None or item["observed_at"] < end)
        if include:
            rows.append(item)
    latest = {}
    for item in rows:
        target = item["content_id"] or item["target_url"] or "account"
        latest[(target, item["scope"], item["metric"], item["window"])] = item
    groups = {}
    for (target, scope, metric, window), item in latest.items():
        group = groups.setdefault((target, scope, window), {"target": target, "scope": scope, "window": window, "metrics": {}})
        group["metrics"][metric] = {k: item[k] for k in ("value", "availability", "observed_at", "source")}
    for group in groups.values():
        metrics = group["metrics"]
        needed = [metrics.get(k) for k in ("impressions", "reactions", "comments", "reposts")]
        rate, reason = None, "Requires impressions, reactions, comments and reposts from one observation/window; absent is unavailable."
        if all(x and x["availability"] == "measured" for x in needed):
            if len({x["observed_at"] for x in needed}) != 1:
                reason = "Metric observations differ; no mixed-age engagement rate calculated."
            elif needed[0]["value"] == 0:
                reason = "Impressions are zero; engagement rate is undefined."
            else:
                rate = sum(x["value"] for x in needed[1:]) / needed[0]["value"]
                reason = "(reactions + comments + reposts) / impressions; includes own comments unless separately reported."
        group["engagement_rate"] = {"value": rate, "definition": reason}
    comparable = {}
    for group in groups.values():
        impression = group["metrics"].get("impressions")
        content = s.one("SELECT pillar,format FROM content WHERE id=?", (group["target"],))
        if group["scope"] == "post" and content and impression and impression["availability"] == "measured":
            k = (content["pillar"], content["format"], group["window"])
            comparable.setdefault(k, []).append(impression["value"])
    medians = [{"pillar": k[0], "format": k[1], "window": k[2], "sample_size": len(v), "median_impressions": statistics.median(v),
                "confidence": "descriptive only; export_range/unspecified windows may mix different post ages; small samples do not establish causality"} for k, v in comparable.items()]
    daily_values = {}
    for group in groups.values():
        if group["scope"] == "account" and group["window"].startswith("day:"):
            for metric, item in group["metrics"].items():
                daily_values.setdefault(metric, []).append(item)
    daily_totals = {metric: {"sum_measured": sum(x["value"] for x in values if x["availability"] == "measured"),
                             "measured_days": sum(x["availability"] == "measured" for x in values),
                             "unavailable_days": sum(x["availability"] == "unavailable" for x in values)} for metric, values in daily_values.items()}
    return {"observations": len(rows), "groups": list(groups.values()), "format_pillar_medians": medians, "daily_account_totals": daily_totals,
            "selection_basis": "Daily series use the measurement day even when imported later. Other snapshots use observation time and retain their original measurement windows; they are not interval growth.",
            "export_engagement_definition": "LinkedIn XLSX Engagements may include link interactions; do not equate this with UI social engagement totals or the defined reaction/comment/repost rate.",
            "unavailable_observations": sum(x["availability"] == "unavailable" for x in rows),
            "attribution": "Observed engagement is not proof that an individual comment or profile visit caused growth."}


def review(s, start=None, eight_week=False):
    today = local_day(s)
    if eight_week:
        configured = s.settings.get("pilot", {}).get("start_date")
        first = s.one("SELECT MIN(observed_at) AS first FROM receipts WHERE state='published'")
        start_date = date.fromisoformat(start or configured or first["first"][:10]) if (start or configured or first["first"]) else None
        end_date = start_date + timedelta(weeks=8) if start_date else None
    else:
        start_date = date.fromisoformat(start) if start else today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=7)
    a = timestamp(start_date.isoformat(), s.settings["timezone"]) if start_date else None
    b = timestamp(end_date.isoformat(), s.settings["timezone"]) if end_date else None
    observations = performance(s, a, b)
    interactions = s.all("SELECT * FROM interactions WHERE occurred_at>=? AND occurred_at<?", (a, b)) if a else []
    people = {}
    for item in interactions:
        if item["relationship_id"]:
            people[item["relationship_id"]] = people.get(item["relationship_id"], 0) + 1
    elapsed = max(0, (today - start_date).days) if start_date else 0
    data = {"kind": "eight_week_review" if eight_week else "weekly_review", "generated_at": now(),
            "start_date": start_date.isoformat() if start_date else None, "end_date_exclusive": end_date.isoformat() if end_date else None,
            "state": "awaiting_first_publication" if start_date is None else ("complete_window" if end_date <= today else "partial_window"),
            "elapsed_pilot_days": elapsed if eight_week else None, "performance": observations,
            "confirmed_interactions": len(interactions), "relationships_with_multiple_recorded_interactions": sum(v >= 2 for v in people.values()),
            "open_experiments": s.all("SELECT * FROM experiments WHERE status='open'"),
            "unresolved_actions": status(s)["unresolved_actions"],
            "expansion_decision": "Keep Instagram inactive until an evidence-backed review of reliability, sustainable effort and useful audience signals." if eight_week else None,
            "next_review_prompts": ["What specific personal perspective was strongest?", "Which measured results have comparable windows?", "What counterexamples challenge the apparent pattern?", "Select one variable for the next experiment; record a hypothesis and evidence."]}
    title = "Eight-week pilot review" if eight_week else "Weekly review"
    lines = ["# " + title, "", "Window: " + (data["start_date"] or "not started") + " to " + (data["end_date_exclusive"] or "not set") + " (end exclusive).", "State: " + data["state"], "",
             "- Metric observations: " + str(observations["observations"]), "- Unavailable observations: " + str(observations["unavailable_observations"]),
             "- Confirmed interactions: " + str(len(interactions)), "- Relationships with multiple recorded interactions: " + str(data["relationships_with_multiple_recorded_interactions"]), "",
             "## Measured comparisons", ""]
    for metric, totals in observations["daily_account_totals"].items():
        lines.append("- Daily " + metric + ": " + str(totals["sum_measured"]) + " across " + str(totals["measured_days"]) + " measured days; " + str(totals["unavailable_days"]) + " unavailable.")
    for item in observations["format_pillar_medians"]:
        lines.append("- " + item["pillar"] + " / " + item["format"] + " / " + item["window"] + ": median impressions " + str(item["median_impressions"]) + " (n=" + str(item["sample_size"]) + ").")
    if not observations["format_pillar_medians"]:
        lines.append("Insufficient linked measurements for format/pillar comparisons. Import metrics or record observations with a content ID.")
    lines += ["", observations["selection_basis"], "", observations["export_engagement_definition"], "", observations["attribution"], "", "## Editorial review", ""] + ["- " + q for q in data["next_review_prompts"]]
    if eight_week:
        lines += ["", data["expansion_decision"]]
    return artifact(s, "reviews", ("eight-week" if eight_week else "weekly") + "-" + (data["start_date"] or "not-started"), data, "\n".join(lines) + "\n")


def export_table(s, table, format="json"):
    allowed = ("content", "assets", "actions", "receipts", "relationships", "relationship_memberships", "membership_observations", "interactions", "metrics", "experiments", "history", "imports") + engagement.TABLES
    if table not in allowed:
        raise Error("Unsupported export table.")
    rows = s.all("SELECT * FROM " + table)
    if format == "json":
        output = json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    else:
        columns = [r[1] for r in s.db.execute("PRAGMA table_info(" + table + ")")]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            # Prevent formula interpretation when local notes are opened in Excel.
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v) for k, v in row.items()})
        output = stream.getvalue()
    path = "reports/exports/" + table + "-" + ident("export") + "." + format
    return {"path": s.write(path, output, True), "rows": len(rows), "source": "local user-owned records / user-provided exports; no LinkedIn API cache included"}
