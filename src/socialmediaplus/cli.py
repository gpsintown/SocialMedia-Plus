"""Codex-operated local CLI. JSON stdout is the stable integration contract."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import __version__, imports, network, reports, workflow, engagement
from .store import Error, Store, ident, now


def parser():
    p = argparse.ArgumentParser(prog="smp", description="Social Media Plus local records. No command posts, likes, scrapes or calls a remote platform.")
    p.add_argument("--root", default=str(Path.cwd()), help="Workspace root; may appear anywhere in the command")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    dashboard = sub.add_parser('dashboard', help='Durable local dashboard request records').add_subparsers(dest='operation', required=True)
    dashboard.add_parser('list')
    dashboard.add_parser('expire', help='Expire undispatched requests; never retries or changes running attempts')
    dashboard.add_parser('show').add_argument('id')
    dq = dashboard.add_parser('enqueue')
    dq.add_argument('--file', required=True, help='JSON command, params, idempotency_key and optional displayed snapshot')
    dt = dashboard.add_parser('transition')
    dt.add_argument('id')
    dt.add_argument('--state', required=True)
    dt.add_argument('--detail', required=True)
    dt.add_argument('--turn-id')
    for name, help in (("init", "Initialize a private local SQLite workspace"), ("status", "Summarize current records"), ("doctor", "Check database, hashes, phase and approval integrity")):
        sub.add_parser(name, help=help)
    content = sub.add_parser("content", help="Versioned draft and exact approval records").add_subparsers(dest="operation", required=True)
    add = content.add_parser("add")
    add.add_argument("file")
    add.add_argument("--title", required=True)
    add.add_argument("--pillar", default="unclassified")
    add.add_argument("--audience", default="unclassified")
    add.add_argument("--format", choices=workflow.FORMATS, default="text")
    add.add_argument("--evidence", action="append", default=[], help="Repeatable factual/experience source reference")
    revise = content.add_parser("revise")
    revise.add_argument("id")
    revise.add_argument("file")
    revise.add_argument("--evidence", action="append", help="Replace evidence references; omitted preserves them")
    slot = content.add_parser("slot")
    slot.add_argument("id")
    slot.add_argument("--at", required=True, help="ISO timestamp; include offset for an ambiguous DST instant")
    slot.add_argument("--timezone", required=True, help="IANA zone, e.g. Asia/Kolkata")
    route = content.add_parser("route", help="Select a per-content publishing authority before approval")
    route.add_argument("id")
    route.add_argument("--authority", required=True, choices=workflow.AUTHORITIES)
    format_command = content.add_parser("format", help="Change the content format before exact approval")
    format_command.add_argument("id")
    format_command.add_argument("--format", required=True, choices=workflow.FORMATS)
    approval = content.add_parser("approve")
    approval.add_argument("id")
    approval.add_argument("--by", required=True, help="Person who authorized the exact batch/item")
    approval.add_argument("--evidence", required=True, help="Reference to actual user authorization; do not fabricate")
    for name in ("show", "check"):
        content.add_parser(name).add_argument("id")
    listing = content.add_parser("list")
    listing.add_argument("--status")
    asset = sub.add_parser("asset", help="Register final asset snapshots and their provenance").add_subparsers(dest="operation", required=True)
    aa = asset.add_parser("add")
    aa.add_argument("content_id")
    aa.add_argument("file")
    aa.add_argument("--alt", required=True)
    aa.add_argument("--source", required=True)
    aa.add_argument("--metadata", default="{}", help="JSON object with dimensions, pages, prompt, editable source or preview")
    asset.add_parser("remove").add_argument("id")
    actions = sub.add_parser("action", help="Prepare a local action and record observed platform outcomes").add_subparsers(dest="operation", required=True)
    ap = actions.add_parser("prepare")
    ap.add_argument("--kind", required=True, choices=workflow.KINDS)
    ap.add_argument("--authority", required=True, choices=("native_linkedin", "official_api", "postiz", "user_manual"))
    ap.add_argument("--content")
    ap.add_argument("--target")
    ap.add_argument("--relationship", help="Known relationship ID for a post/comment target; exact profile visits link automatically")
    ap.add_argument("--session", help="Current plus-session authorization record")
    ap.add_argument("--opportunity", help="Observed qualifying job ID for recruiter DM/InMail")
    ap.add_argument("--attachment", help="Reviewed master PDF; stores an immutable private snapshot")
    ap.add_argument("--details-file", help="JSON containing reaction or outreach route/subject evidence")
    text_arguments(ap)
    for name in ("receipt", "reconcile"):
        ar = actions.add_parser(name)
        ar.add_argument("id")
        ar.add_argument("--state", choices=("confirmed", "uncertain", "failed", "cancelled"), required=True)
        ar.add_argument("--evidence", required=True)
        ar.add_argument("--remote-url")
        ar.add_argument("--remote-id", help="Observed queue reference or remote object ID")
        ar.add_argument("--observed-at", help="ISO timestamp with offset; defaults to current UTC")
        ar.add_argument("--observed-details-file", help="Confirmed DM/InMail: JSON with actually observed target_url, response, attachment_sha256 and subject")
    retry = actions.add_parser("retry")
    retry.add_argument("id")
    retry.add_argument("--evidence", required=True)
    pub = actions.add_parser("publication")
    pub.add_argument("id", help="Previously confirmed schedule action")
    pub.add_argument("--remote-url", required=True)
    pub.add_argument("--evidence", required=True)
    pub.add_argument("--observed-at")
    actions.add_parser("show").add_argument("id")
    actions.add_parser("check", help="Verify a prepared plus action immediately before browser submission").add_argument("id")
    actions.add_parser("list")
    sessions = sub.add_parser("session", help="Record a current plus-mode invocation; no remote execution").add_subparsers(dest="operation", required=True)
    ss = sessions.add_parser("start")
    ss.add_argument("--mode", required=True, choices=("engage_plus", "recruiter_plus"))
    ss.add_argument("--minutes", type=int, default=30)
    ss.add_argument("--authorization", required=True)
    ss.add_argument("--preview", action="store_true")
    for name in ("show", "end"):
        sessions.add_parser(name).add_argument("id")
    jobs = sub.add_parser("opportunity", help="Immutable visible job evidence and linked hiring contact").add_subparsers(dest="operation", required=True)
    jobs.add_parser("add").add_argument("file", help="JSON observation with explicit job, applicant, fit and contact evidence")
    jobs.add_parser("show").add_argument("id")
    jobs.add_parser("list")
    credits = sub.add_parser("inmail", help="Observed balance and conservative local credit holds").add_subparsers(dest="operation", required=True)
    cb = credits.add_parser("observe")
    cb.add_argument("--balance", type=int, required=True)
    cb.add_argument("--evidence", required=True)
    cb.add_argument("--observed-at")
    credits.add_parser("status").add_argument("--session")
    imp = sub.add_parser("import", help="Import user-provided LinkedIn exports; originals stay private")
    imp.add_argument("kind", choices=("connections", "followers", "archive", "metrics"))
    imp.add_argument("file")
    imp.add_argument("--observed-at", help="Metrics capture timestamp with offset")
    imp.add_argument("--window", help="Explicit measurement window; daily export rows retain their own dates")
    rel = sub.add_parser("relationship", help="Explicit-source professional classifications").add_subparsers(dest="operation", required=True)
    ra = rel.add_parser("add")
    ra.add_argument("--name", required=True)
    ra.add_argument("--url", required=True)
    ra.add_argument("--source", required=True)
    ra.add_argument("--company")
    ra.add_argument("--position")
    ra.add_argument("--type", default="connection", choices=("connection", "follower", "peer", "creator", "company_contact"))
    ru = rel.add_parser("update")
    ru.add_argument("id")
    for opt in ("bucket", "evidence", "geography", "geography-evidence", "topic", "reviewed-at", "next-review", "skip"):
        ru.add_argument("--" + opt)
    ru.add_argument("--clear-skip", action="store_true")
    rl = rel.add_parser("list")
    rl.add_argument("--bucket")
    rl.add_argument("--membership", action="append", choices=network.MEMBERSHIPS, help="Repeat memberships for an OR filter; a profile may be both connection and follower")
    rl.add_argument("--exclude-membership", action="append", choices=network.MEMBERSHIPS, help="Exclude profiles with any listed membership; combine follower include with connection exclude for follower-only people")
    rd = rel.add_parser("due")
    rd.add_argument("--as-of")
    rd.add_argument("--limit", type=int)
    rd.add_argument("--bucket", action="append", help="Repeat role buckets; recent recorded exchanges are included ahead of role candidates in conversations mode")
    rd.add_argument("--priority", choices=("conversations", "rotation"), default="conversations", help="Default: recorded exchanges first, then relevant professional roles; rotation reviews inventory")
    rd.add_argument("--cooldown-hours", type=int, default=24)
    rd.add_argument("--membership", action="append", choices=network.MEMBERSHIPS)
    rd.add_argument("--exclude-membership", action="append", choices=network.MEMBERSHIPS)
    rel.add_parser("coverage", help="Connection and incoming-follower coverage with overlap and latest snapshot evidence")
    ri = rel.add_parser("show")
    ri.add_argument("id")
    batch = rel.add_parser("apply", help="Apply apply:true rows in an explicitly reviewed classification proposal; preserve existing classifications")
    batch.add_argument("file")
    batch.add_argument("--evidence", required=True, help="Reference to the classification review decision")
    interaction = sub.add_parser("interaction", help="Confirmed observed participation history").add_subparsers(dest="operation", required=True)
    ia = interaction.add_parser("add")
    ia.add_argument("--target", required=True)
    ia.add_argument("--kind", required=True, choices=("comment", "reply", "like", "visit", "conversation", "repost", "reaction", "dm", "inmail"))
    ia.add_argument("--at", required=True, help="Actual occurrence ISO timestamp with offset")
    ia.add_argument("--source", required=True)
    ia.add_argument("--relationship")
    ia.add_argument("--outcome")
    text_arguments(ia)
    interaction.add_parser("list")
    history = sub.add_parser("history", help="Read private imported LinkedIn history; these are not live action receipts").add_subparsers(dest="operation", required=True)
    hl = history.add_parser("list")
    hl.add_argument("--kind", action="append", help="Repeat exported kinds, e.g. shares, comments, reactions, instant_reposts")
    hl.add_argument("--target", help="Exact LinkedIn target URL; URN colon encoding and tracking parameters are normalized")
    hl.add_argument("--query", help="Literal text substring, at most 200 characters")
    hl.add_argument("--limit", type=int, default=20, help="Maximum returned records, 1–100 (default 20)")
    metric = sub.add_parser("metric", help="Measured values or explicit unavailable observations").add_subparsers(dest="operation", required=True)
    ma = metric.add_parser("add")
    ma.add_argument("--metric", required=True)
    value = ma.add_mutually_exclusive_group(required=True)
    value.add_argument("--value")
    value.add_argument("--unavailable", action="store_true")
    ma.add_argument("--source", required=True)
    ma.add_argument("--observed-at", required=True)
    ma.add_argument("--window", required=True)
    ma.add_argument("--content")
    ma.add_argument("--target")
    ma.add_argument("--scope", choices=("post", "account"))
    metric.add_parser("list")
    exp = sub.add_parser("experiment", help="Explicit editorial hypotheses and evidence").add_subparsers(dest="operation", required=True)
    ea = exp.add_parser("add")
    ea.add_argument("--hypothesis", required=True)
    ea.add_argument("--variable", required=True)
    ea.add_argument("--start", required=True)
    er = exp.add_parser("resolve")
    er.add_argument("id")
    er.add_argument("--decision", required=True)
    er.add_argument("--evidence", required=True)
    er.add_argument("--end", required=True)
    exp.add_parser("list")
    week = sub.add_parser("plan-week", help="Generate proposed weekly slots and draft/evidence review artifacts")
    week.add_argument("--start")
    day = sub.add_parser("daily", help="Generate a bounded local relationship/action review")
    day.add_argument("--date")
    day.add_argument("--limit", type=int)
    day.add_argument("--bucket", action="append", help="Repeat selected role buckets; default BI/data/analytics/marketing analytics")
    day.add_argument("--priority", choices=("conversations", "rotation"), default="conversations")
    day.add_argument("--cooldown-hours", type=int, default=24)
    day.add_argument("--membership", action="append", choices=network.MEMBERSHIPS)
    day.add_argument("--exclude-membership", action="append", choices=network.MEMBERSHIPS)
    for name in ("weekly-review", "eight-week-review"):
        sub.add_parser(name).add_argument("--start")
    export = sub.add_parser("export", help="Export a local record table to a private report")
    export.add_argument("table", choices=("content", "assets", "actions", "receipts", "relationships", "relationship_memberships", "membership_observations", "interactions", "metrics", "experiments", "history", "imports") + engagement.TABLES)
    export.add_argument("--format", choices=("json", "csv"), default="json")
    return p


def text_arguments(p):
    for name in ("response", "context"):
        group = p.add_mutually_exclusive_group()
        group.add_argument("--" + name)
        group.add_argument("--" + name + "-file", help="UTF-8 text file; preserves exact multiline content")


def texts(args):
    return [Path(getattr(args, name + "_file")).read_text(encoding="utf-8") if getattr(args, name + "_file", None) else getattr(args, name, None) for name in ("response", "context")]


def dispatch(s, a):
    if a.command == 'dashboard':
        from .dashboard import records
        if a.operation == 'expire':
            return records.expire_pending(s)
        if a.operation == 'list':
            return s.all('SELECT id,command,state,created_at,updated_at FROM dashboard_requests ORDER BY created_at DESC')
        if a.operation == 'show':
            return records.get(s, a.id)
        if a.operation == 'transition':
            return records.transition(s, a.id, a.state, a.detail, a.turn_id)
        body = json.loads(Path(a.file).read_text())
        return records.enqueue(s, body['command'], body.get('params', {}), body['idempotency_key'], body.get('snapshot'))
    if a.command in ("init", "status"):
        return reports.status(s)
    if a.command == "doctor":
        return reports.doctor(s)
    if a.command == "content":
        if a.operation == "add":
            return workflow.content_add(s, a.file, a.title, a.pillar, a.audience, a.format, a.evidence)
        if a.operation == "revise":
            return workflow.content_revise(s, a.id, a.file, a.evidence)
        if a.operation == "slot":
            return workflow.set_slot(s, a.id, a.at, a.timezone)
        if a.operation == "route":
            return workflow.set_route(s, a.id, a.authority)
        if a.operation == "format":
            return workflow.set_format(s, a.id, a.format)
        if a.operation == "approve":
            return workflow.approve(s, a.id, a.by, a.evidence)
        if a.operation == "show":
            return workflow.content_show(s, a.id)
        if a.operation == "check":
            return workflow.content_check(s, a.id)
        return s.all("SELECT * FROM content" + (" WHERE status=?" if a.status else "") + " ORDER BY created_at", (a.status,) if a.status else ())
    if a.command == "asset":
        if a.operation == "add":
            metadata = json.loads(a.metadata)
            if not isinstance(metadata, dict):
                raise Error("--metadata must be a JSON object.")
            return workflow.asset_add(s, a.content_id, a.file, a.alt, a.source, metadata)
        return workflow.asset_remove(s, a.id)
    if a.command == "action":
        if a.operation == "prepare":
            response, context = texts(a)
            details = json.loads(Path(a.details_file).read_text(encoding="utf-8")) if a.details_file else None
            return workflow.prepare(s, a.kind, a.authority, a.content, a.target, response, context, a.relationship,
                                    a.session, a.opportunity, a.attachment, details)
        if a.operation in ("receipt", "reconcile"):
            observed = json.loads(Path(a.observed_details_file).read_text(encoding="utf-8")) if a.observed_details_file else None
            return workflow.receipt(s, a.id, a.state, a.evidence, a.remote_url, a.remote_id, a.observed_at, a.operation == "reconcile", observed)
        if a.operation == "retry":
            return workflow.retry(s, a.id, a.evidence)
        if a.operation == "publication":
            return workflow.publication(s, a.id, a.evidence, a.remote_url, a.observed_at)
        if a.operation == "show":
            return workflow.action_show(s, a.id)
        if a.operation == "check":
            return engagement.check_action(s, a.id)
        return s.all("SELECT * FROM actions ORDER BY created_at")
    if a.command == "session":
        if a.operation == "start":
            return engagement.session_start(s, a.mode, a.minutes, a.authorization, a.preview)
        return engagement.session_show(s, a.id) if a.operation == "show" else engagement.session_end(s, a.id)
    if a.command == "opportunity":
        if a.operation == "add":
            return engagement.opportunity_add(s, a.file)
        if a.operation == "show":
            return engagement.opportunity_show(s, a.id)
        return [engagement.opportunity_show(s, row["id"]) for row in s.all("SELECT id FROM opportunities ORDER BY observed_at DESC")]
    if a.command == "inmail":
        if a.operation == "observe":
            return engagement.observe_balance(s, a.balance, a.evidence, a.observed_at)
        return engagement.inmail_status(s, a.session)
    if a.command == "import":
        return imports.import_file(s, a.kind, a.file, a.observed_at, a.window)
    if a.command == "relationship":
        if a.operation == "add":
            return network.add(s, a.name, a.url, a.source, a.company, a.position, a.type)
        if a.operation == "update":
            return network.update(s, a.id, a.bucket, a.evidence, a.geography, a.geography_evidence, a.topic, a.reviewed_at, a.next_review, a.skip, a.clear_skip)
        if a.operation == "due":
            return network.due(s, a.as_of, a.limit, a.bucket, a.priority, a.cooldown_hours, a.membership, a.exclude_membership)
        if a.operation == "coverage":
            return reports.coverage(s)
        if a.operation == "apply":
            return network.apply_proposal(s, a.file, a.evidence)
        if a.operation == "show":
            row = s.require("relationships", a.id)
            row["memberships"] = network.memberships(s, a.id)
            row["membership_observations"] = s.all("SELECT * FROM membership_observations WHERE relationship_id=? ORDER BY observed_at DESC", (a.id,))
            row["interactions"] = s.all("SELECT * FROM interactions WHERE relationship_id=? ORDER BY occurred_at DESC", (a.id,))
            return row
        return network.list_people(s, a.bucket, a.membership, a.exclude_membership)
    if a.command == "interaction":
        if a.operation == "add":
            response, context = texts(a)
            return workflow.add_interaction(s, a.target, a.kind, a.at, a.source, response, context, a.relationship, a.outcome)
        return s.all("SELECT * FROM interactions ORDER BY occurred_at DESC")
    if a.command == "history":
        return reports.history_list(s, a.kind, a.target, a.query, a.limit)
    if a.command == "metric":
        if a.operation == "add":
            return imports.metric_add(s, a.metric, None if a.unavailable else a.value, a.source, a.observed_at, a.window, a.content, a.target, a.scope)
        return s.all("SELECT * FROM metrics ORDER BY observed_at DESC")
    if a.command == "experiment":
        from datetime import date
        if a.operation == "add":
            item = dict(id=ident("experiment"), hypothesis=a.hypothesis, variable=a.variable, start_date=date.fromisoformat(a.start).isoformat(), created_at=now())
            with s.transaction():
                s.insert("experiments", item)
            return item
        if a.operation == "resolve":
            row = s.require("experiments", a.id)
            end = date.fromisoformat(a.end).isoformat()
            if end < row["start_date"]:
                raise Error("Experiment end precedes start.")
            with s.transaction():
                s.db.execute("UPDATE experiments SET status='reviewed',end_date=?,evidence=?,decision=? WHERE id=?", (end, a.evidence, a.decision, a.id))
            return s.require("experiments", a.id)
        return s.all("SELECT * FROM experiments ORDER BY created_at")
    if a.command == "plan-week":
        return reports.plan_week(s, a.start)
    if a.command == "daily":
        return reports.daily(s, a.date, a.limit, a.bucket, a.priority, a.cooldown_hours, a.membership, a.exclude_membership)
    if a.command in ("weekly-review", "eight-week-review"):
        return reports.review(s, a.start, a.command == "eight-week-review")
    if a.command == "export":
        return reports.export_table(s, a.table, a.format)
    raise Error("Unsupported command.")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Support --root after any subcommand as well as conventional global placement.
    root_args = []
    for index in range(len(argv) - 1, -1, -1):
        if argv[index].startswith("--root="):
            root_args = ["--root", argv.pop(index).split("=", 1)[1]]
        elif argv[index] == "--root" and index + 1 < len(argv):
            root_args = argv[index:index + 2]
            del argv[index:index + 2]
    args = parser().parse_args(root_args + argv)
    store = None
    try:
        store = Store(args.root, create=args.command == "init")
        result = dispatch(store, args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if args.command == "doctor" and not result["ok"] else 0
    except (Error, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"error": str(exc), "command": args.command}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
