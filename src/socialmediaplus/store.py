"""SQLite persistence, canonical identifiers, files, and time handling."""
import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Error(ValueError):
    """A reviewable user/data error, printed without a traceback by the CLI."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ident(prefix):
    return prefix + "_" + uuid.uuid4().hex[:12]


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def canonical_url(value, profile=False):
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise Error("Use an absolute HTTPS URL without credentials.")
    host = parsed.hostname.lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        host = "www.linkedin.com"
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    # LinkedIn's observed English-language profile links add /en/. Collapse
    # that explicit locale only, never activity/details or arbitrary subpages.
    if profile and host == "www.linkedin.com" and re.fullmatch(r"/in/[^/]+/en", path):
        path = path[:-3]
    if profile and (host != "www.linkedin.com" or not re.fullmatch(r"/in/[^/]+", path)):
        raise Error("A relationship needs a LinkedIn /in/ profile URL.")
    # commentUrn/replyUrn in LinkedIn links identify a precise comment target.
    # Strip only tracking parameters; dropping every query collapses different replies.
    query = [] if profile else [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                                if not k.lower().startswith("utm_") and k.lower() not in ("lipi", "trackingid", "mid", "trk")]
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def timestamp(value, tz_name=None, validate_offset=True):
    """Return an explicit UTC instant; reject ambiguous/nonexistent local times."""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise Error("Time must be ISO 8601, e.g. 2026-09-14T09:00:00+05:30.") from exc
    if dt.tzinfo is None:
        if not tz_name:
            raise Error("Naive timestamps require --timezone with an IANA zone.")
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise Error("Unknown IANA time zone: " + tz_name) from exc
        candidates = []
        for fold in (0, 1):
            aware = dt.replace(tzinfo=tz, fold=fold)
            if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == dt:
                candidates.append(aware)
        if not candidates:
            raise Error("This local time does not exist due to daylight saving time.")
        if len({x.utcoffset() for x in candidates}) > 1:
            raise Error("This local time is ambiguous; include an explicit UTC offset.")
        dt = candidates[0]
    elif tz_name and validate_offset:
        try:
            local = dt.astimezone(ZoneInfo(tz_name))
        except ZoneInfoNotFoundError as exc:
            raise Error("Unknown IANA time zone: " + tz_name) from exc
        if dt.utcoffset() != local.utcoffset():
            raise Error("Timestamp offset does not match the supplied IANA time zone.")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


MEMBERSHIP_SCHEMA = """
CREATE TABLE IF NOT EXISTS relationship_memberships(
 relationship_id TEXT NOT NULL REFERENCES relationships(id), membership TEXT NOT NULL,
 first_observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL, source TEXT NOT NULL,
 PRIMARY KEY(relationship_id,membership)
);
CREATE TABLE IF NOT EXISTS membership_observations(
 id TEXT PRIMARY KEY, relationship_id TEXT NOT NULL REFERENCES relationships(id), membership TEXT NOT NULL,
 observed_at TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT, name TEXT, headline TEXT,
 dedup_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS membership_observations_relationship ON membership_observations(relationship_id,membership,observed_at);
"""

PLUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS engagement_sessions(
 id TEXT PRIMARY KEY, mode TEXT NOT NULL, authorization TEXT NOT NULL,
 preview INTEGER NOT NULL, started_at TEXT NOT NULL, ends_at TEXT NOT NULL, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS opportunities(
 id TEXT PRIMARY KEY, job_url TEXT NOT NULL, company TEXT NOT NULL, title TEXT NOT NULL,
 country TEXT NOT NULL, observed_at TEXT NOT NULL, contact_id TEXT REFERENCES relationships(id),
 evidence_json TEXT NOT NULL, source_path TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS opportunities_url ON opportunities(job_url,observed_at);
CREATE TABLE IF NOT EXISTS action_details(
 action_id TEXT PRIMARY KEY REFERENCES actions(id), session_id TEXT NOT NULL REFERENCES engagement_sessions(id),
 opportunity_id TEXT REFERENCES opportunities(id), details_json TEXT NOT NULL,
 attachment_path TEXT, attachment_sha256 TEXT, attachment_name TEXT, fingerprint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipt_details(
 receipt_id TEXT PRIMARY KEY REFERENCES receipts(id), evidence_json TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inmail_balances(
 id TEXT PRIMARY KEY, balance INTEGER NOT NULL CHECK(balance>=0),
 observed_at TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inmail_reservations(
 action_id TEXT PRIMARY KEY REFERENCES actions(id), session_id TEXT NOT NULL REFERENCES engagement_sessions(id),
 balance_id TEXT NOT NULL REFERENCES inmail_balances(id), state TEXT NOT NULL,
 reserved_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
INSERT INTO schema_version SELECT 5 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
CREATE TABLE IF NOT EXISTS content(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, pillar TEXT NOT NULL,
 audience TEXT NOT NULL, format TEXT NOT NULL, platform TEXT NOT NULL DEFAULT 'linkedin',
 publishing_authority TEXT NOT NULL DEFAULT 'native_linkedin',
 current_version INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'draft',
 evidence_json TEXT NOT NULL, scheduled_at TEXT, schedule_timezone TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions(
 content_id TEXT NOT NULL REFERENCES content(id), version INTEGER NOT NULL,
 path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(content_id,version)
);
CREATE TABLE IF NOT EXISTS assets(
 id TEXT PRIMARY KEY, content_id TEXT NOT NULL REFERENCES content(id),
 path TEXT NOT NULL UNIQUE, original_path TEXT NOT NULL, sha256 TEXT NOT NULL,
 alt_text TEXT NOT NULL, source TEXT NOT NULL, metadata_json TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals(
 id TEXT PRIMARY KEY, content_id TEXT NOT NULL REFERENCES content(id),
 fingerprint TEXT NOT NULL, approved_by TEXT NOT NULL, evidence TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, content_id TEXT REFERENCES content(id),
 fingerprint TEXT, target_url TEXT, response TEXT, parent_context TEXT,
 relationship_id TEXT REFERENCES relationships(id),
 authority TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'prepared',
 idempotency_key TEXT NOT NULL UNIQUE, attempt INTEGER NOT NULL DEFAULT 1,
 remote_url TEXT, remote_id TEXT, scheduled_at TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts(
 id TEXT PRIMARY KEY, action_id TEXT NOT NULL REFERENCES actions(id),
 state TEXT NOT NULL, evidence TEXT NOT NULL, remote_url TEXT, remote_id TEXT,
 observed_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relationships(
 id TEXT PRIMARY KEY, profile_url TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 company TEXT, position TEXT, connected_at TEXT, relationship_type TEXT NOT NULL DEFAULT 'connection',
 bucket TEXT NOT NULL DEFAULT 'unclassified', bucket_evidence TEXT,
 topic TEXT, geography TEXT, geography_evidence TEXT, source TEXT NOT NULL, last_reviewed_at TEXT, next_review_at TEXT,
 skip_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interactions(
 id TEXT PRIMARY KEY, relationship_id TEXT REFERENCES relationships(id),
 action_id TEXT UNIQUE REFERENCES actions(id), target_url TEXT NOT NULL,
 kind TEXT NOT NULL, response TEXT, parent_context TEXT, state TEXT NOT NULL,
 occurred_at TEXT NOT NULL, source TEXT NOT NULL, outcome TEXT,
 dedup_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
 source_path TEXT NOT NULL, stored_path TEXT NOT NULL, imported_at TEXT NOT NULL,
 summary_json TEXT NOT NULL, UNIQUE(kind,sha256)
);
CREATE TABLE IF NOT EXISTS history(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_url TEXT, text TEXT,
 occurred_at TEXT, source TEXT NOT NULL, raw_json TEXT NOT NULL,
 dedup_key TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS metrics(
 id TEXT PRIMARY KEY, content_id TEXT REFERENCES content(id), target_url TEXT,
 scope TEXT NOT NULL, metric TEXT NOT NULL, value REAL, availability TEXT NOT NULL,
 observed_at TEXT NOT NULL, window TEXT NOT NULL, source TEXT NOT NULL,
 dedup_key TEXT NOT NULL UNIQUE,
 CHECK(availability IN ('measured','unavailable')),
 CHECK((availability='measured' AND value IS NOT NULL) OR (availability='unavailable' AND value IS NULL))
);
CREATE TABLE IF NOT EXISTS experiments(
 id TEXT PRIMARY KEY, hypothesis TEXT NOT NULL, variable TEXT NOT NULL,
 start_date TEXT NOT NULL, end_date TEXT, status TEXT NOT NULL DEFAULT 'open',
 evidence TEXT, decision TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS metrics_content ON metrics(content_id,metric,observed_at);
CREATE INDEX IF NOT EXISTS interactions_relationship ON interactions(relationship_id,occurred_at);
""" + MEMBERSHIP_SCHEMA + PLUS_SCHEMA


class Store:
    def __init__(self, root, create=False):
        self.root = Path(root).expanduser().resolve()
        self.db_path = self.root / "data/socialmediaplus.sqlite3"
        self.settings = {
            "timezone": "UTC", "display_timezones": [],
            "active_platforms": ["linkedin"], "profile_url": "",
            "weekly_post_count": 3, "daily_queue_limit": 8,
        }
        settings_path = self.root / "config/settings.json"
        if settings_path.exists():
            try:
                self.settings.update(json.loads(settings_path.read_text(encoding="utf-8")))
            except (ValueError, TypeError) as exc:
                raise Error("config/settings.json must be a JSON object.") from exc
        for name in [self.settings["timezone"]] + self.settings.get("display_timezones", []):
            try:
                ZoneInfo(name)
            except (ZoneInfoNotFoundError, TypeError) as exc:
                raise Error("Invalid configured time zone: " + str(name)) from exc
        if not create and not self.db_path.exists():
            raise Error("Workspace is not initialized. Run: scripts/smp --root PATH init")
        if create:
            for path in ("data/imports", "content/versions", "assets/registered", "reports", "network"):
                (self.root / path).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=15000")
        if create:
            self.db.executescript(SCHEMA)
            self.db.commit()
            os.chmod(self.db_path, 0o600)
        version = self.one("SELECT version FROM schema_version")["version"]
        if version == 1:
            # Additive migration for the initial local pilot database.
            with self.db:
                self.db.execute("ALTER TABLE actions ADD COLUMN relationship_id TEXT REFERENCES relationships(id)")
                self.db.execute("UPDATE schema_version SET version=2")
            version = 2
        if version == 2:
            with self.db:
                self.db.execute("ALTER TABLE content ADD COLUMN publishing_authority TEXT NOT NULL DEFAULT 'native_linkedin'")
                self.db.execute("UPDATE schema_version SET version=3")
            version = 3
        if version == 3:
            # Memberships overlap: observing a follower must not erase their connection,
            # role classification, review notes, or established interaction identity.
            with self.db:
                for statement in MEMBERSHIP_SCHEMA.split(";"):
                    if statement.strip():
                        self.db.execute(statement)
                self.db.execute("""INSERT OR IGNORE INTO relationship_memberships
                    (relationship_id,membership,first_observed_at,last_observed_at,source)
                    SELECT id,relationship_type,created_at,created_at,source FROM relationships""")
                self.db.execute("UPDATE schema_version SET version=4")
            version = 4
        if version == 4:
            with self.db:
                for statement in PLUS_SCHEMA.split(";"):
                    if statement.strip():
                        self.db.execute(statement)
                self.db.execute("UPDATE schema_version SET version=5")
            version = 5
        if version == 5:
            from .dashboard.records import SCHEMA as DASHBOARD_SCHEMA
            with self.db:
                for statement in DASHBOARD_SCHEMA.split(';'):
                    if statement.strip():
                        self.db.execute(statement)
                self.db.execute('UPDATE schema_version SET version=6')
            version = 6
        if version == 6:
            # Legacy requests did not persist the desktop product. Leave their
            # host unknown rather than inferring authorization from today's
            # mutable configuration; only fresh invocations may dispatch.
            # Acquire the writer lock before checking columns, so concurrent
            # dashboard reads cannot race the additive ALTER TABLE.
            self.db.execute('BEGIN IMMEDIATE')
            with self.db:
                columns = {row['name'] for row in self.all('PRAGMA table_info(dashboard_requests)')}
                if 'desktop_host' not in columns:
                    self.db.execute('ALTER TABLE dashboard_requests ADD COLUMN desktop_host TEXT')
                self.db.execute('UPDATE schema_version SET version=7')
            version = 7
        if version != 7:
            raise Error("Unsupported database schema version: " + str(version))

    def close(self):
        self.db.close()

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def require(self, table, id_value):
        if table not in ("content", "assets", "actions", "relationships", "experiments", "engagement_sessions", "opportunities"):
            raise Error("Invalid record type.")
        row = self.one("SELECT * FROM " + table + " WHERE id=?", (id_value,))
        if not row:
            raise Error("Unknown " + table + " ID: " + id_value)
        return row

    def insert(self, table, values):
        keys = list(values)
        self.db.execute("INSERT INTO " + table + " (" + ",".join(keys) + ") VALUES (" + ",".join("?" for _ in keys) + ")", [values[k] for k in keys])

    def managed(self, relative):
        result = (self.root / relative).resolve()
        try:
            result.relative_to(self.root)
        except ValueError as exc:
            raise Error("Managed file escapes the project root.") from exc
        return result

    def write(self, relative, data, exclusive=False):
        result = self.managed(relative)
        result.parent.mkdir(parents=True, exist_ok=True)
        with result.open("xb" if exclusive else "wb") as stream:
            stream.write(data.encode("utf-8") if isinstance(data, str) else data)
        os.chmod(result, 0o600)
        return str(result)

    def read_checked(self, relative, checksum):
        path = self.managed(relative)
        if not path.is_file() or digest(path.read_bytes()) != checksum:
            raise Error("Missing or changed registered file: " + relative)
        return path

    def transaction(self):
        # Writers acquire the lock before validation, so concurrent approval/edits serialize.
        self.db.execute("BEGIN IMMEDIATE")
        return self.db


def number(value, allow_negative=False):
    if value is None or str(value).strip().lower() in ("", "n/a", "na", "null", "none", "-", "—", "unavailable"):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise Error("Invalid numeric metric: " + str(value)) from exc
    if not math.isfinite(result) or (result < 0 and not allow_negative):
        raise Error("Metrics must be finite non-negative counts; signed daily engagement/follower deltas are supported.")
    return result
