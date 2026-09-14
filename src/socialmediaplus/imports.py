"""Private CSV/XLSX/LinkedIn archive imports without scraping or optional runtimes."""
import csv
import io
import json
import re
import zipfile
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from .store import Error, canonical_url, digest, dump, ident, now, number, timestamp
from .network import observe_membership


def key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def csv_rows(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-16")
    try:
        dialect = csv.Sniffer().sniff(text[:12000], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def safe_zip(raw):
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise Error("Invalid ZIP/XLSX archive.") from exc
    if len(archive.infolist()) > 10000 or sum(x.file_size for x in archive.infolist()) > 250_000_000:
        archive.close()
        raise Error("Archive is too large to import safely (250 MB uncompressed / 10,000 files limit).")
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
            archive.close()
            raise Error("Unsafe archive member path.")
        if info.flag_bits & 1:
            archive.close()
            raise Error("Encrypted archives are not supported.")
    return archive


def xlsx_tables(raw):
    """Read values/cached formulas from OOXML, including Excel date styles."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with safe_zip(raw) as archive:
        try:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root.findall("m:si", ns)]
            date_styles = set()
            if "xl/styles.xml" in archive.namelist():
                styles = ET.fromstring(archive.read("xl/styles.xml"))
                formats = {int(n.attrib["numFmtId"]): n.attrib.get("formatCode", "") for n in styles.findall("m:numFmts/m:numFmt", ns)}
                for index, xf in enumerate(styles.findall("m:cellXfs/m:xf", ns)):
                    code = int(xf.attrib.get("numFmtId", 0))
                    if code in set(range(14, 23)) | set(range(45, 48)) or re.search(r"[dy]", formats.get(code, ""), re.I):
                        date_styles.add(index)
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            props = workbook.find("m:workbookPr", ns)
            base = datetime(1904, 1, 1) if props is not None and props.attrib.get("date1904") in ("1", "true") else datetime(1899, 12, 30)
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            mapping = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
            tables = []
            for sheet in workbook.findall("m:sheets/m:sheet", ns):
                target = mapping[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
                path = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
                if ".." in PurePosixPath(path).parts:
                    raise Error("Unsafe XLSX worksheet relationship.")
                tree = ET.fromstring(archive.read(path))
                rows = []
                for row in tree.findall("m:sheetData/m:row", ns):
                    values = []
                    for cell in row.findall("m:c", ns):
                        letters = re.sub(r"\d", "", cell.attrib.get("r", "A1"))
                        column = 0
                        for ch in letters:
                            column = column * 26 + ord(ch.upper()) - 64
                        if column > 4096:
                            raise Error("XLSX has too many columns.")
                        while len(values) < column:
                            values.append("")
                        value = cell.find("m:v", ns)
                        data = value.text if value is not None and value.text is not None else ""
                        kind = cell.attrib.get("t")
                        if kind == "s" and data:
                            data = shared[int(data)]
                        elif kind == "inlineStr":
                            data = "".join(n.text or "" for n in cell.findall("m:is//m:t", ns))
                        elif kind == "e":
                            data = ""
                        elif data and int(cell.attrib.get("s", 0)) in date_styles and kind not in ("str", "b"):
                            data = (base + timedelta(days=float(data))).isoformat()
                        if column:
                            values[column - 1] = data
                    rows.append(values)
                tables.append((sheet.attrib["name"], rows))
            return tables
        except (ET.ParseError, KeyError, ValueError, IndexError) as exc:
            raise Error("Malformed or unsupported XLSX workbook: " + str(exc)) from exc


def tables(file, raw):
    suffix = Path(file).suffix.lower()
    if suffix == ".xlsx":
        return xlsx_tables(raw)
    if suffix in (".csv", ".tsv"):
        return [(Path(file).stem, csv_rows(raw))]
    raise Error("Use CSV, TSV or XLSX for tabular imports.")


def records(rows, kind):
    """Locate LinkedIn preamble/header without treating metadata as data."""
    for index, row in enumerate(rows[:60]):
        normalized = [key(x) for x in row]
        if kind == "connections":
            match = bool(set(normalized) & {"url", "profileurl", "linkedinurl", "publicprofileurl"}) and bool(set(normalized) & {"firstname", "lastname", "name", "fullname"})
        elif kind == "metrics":
            match = ("metric" in normalized and "value" in normalized) or len(set(normalized) & set(METRICS)) > 0
        else:
            match = bool(set(normalized) & {"date", "createdat", "time", "timestamp", "url", "link", "sharelink", "comment", "text", "title", "content", "firstname"})
        if match:
            return [{normalized[i]: v for i, v in enumerate(values[:len(normalized)]) if normalized[i]}
                    for values in rows[index + 1:] if any(str(v).strip() for v in values)]
    return []


def pick(row, *names):
    for name in names:
        value = row.get(key(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def parse_date(value, default=None, tz="UTC"):
    if not value:
        return default
    try:
        return timestamp(value, tz if not re.search(r"(Z|[+-]\d\d:\d\d)$", value) else None)
    except Error:
        for pattern in ("%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%m/%d/%Y %H:%M", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%b %d, %Y"):
            try:
                return timestamp(datetime.strptime(value, pattern).isoformat(), tz)
            except (ValueError, Error):
                pass
    raise Error("Unrecognized date: " + value)


METRICS = {
    "impressions": "impressions", "impression": "impressions", "membersreached": "members_reached", "reach": "members_reached",
    "reactions": "reactions", "likes": "reactions", "comments": "comments", "reposts": "reposts", "reshares": "reposts",
    "saves": "saves", "postsaves": "saves", "sends": "sends", "sendsonlinkedin": "sends",
    "engagements": "engagements", "engagement": "engagements", "followers": "followers", "totalfollowers": "followers",
    "newfollowers": "followers_gained", "followersgained": "followers_gained", "followersgainedfromthispost": "followers_gained",
    "profileviewersfromthispost": "profile_views", "profileviews": "profile_views", "profileviewers": "profile_views",
    "linkclicks": "link_clicks", "visitstolinksinthispost": "link_clicks", "videoviews": "video_views", "articleviews": "article_views",
    "owncomments": "own_comments", "substantivecomments": "substantive_comments", "opportunities": "opportunities",
}


PROFESSIONAL_FIELDS = {
    "profile": {"firstname", "lastname", "headline", "summary", "industry", "geolocation", "websites", "profileurl", "linkedinurl"},
    "positions": {"companyname", "title", "description", "location", "startedon", "finishedon"},
    "projects": {"title", "description", "url", "startedon", "finishedon"},
    "skills": {"name"},
    "certifications": {"name", "url", "authority", "startedon", "finishedon"},
    "education": {"schoolname", "startdate", "enddate", "degreename", "activities"},
    "publications": {"name", "publishedon", "description", "publisher", "url"},
}


SOCIAL_EXPORTS = {"shares": "shares", "comments": "comments", "reactions": "reactions",
                  "articles": "articles", "instantreposts": "instant_reposts"}


def archive_section(stem):
    """Account-number suffixes are allowed only for named social export files."""
    matched = re.fullmatch(r"(Shares|Comments|Reactions|Articles|InstantReposts)(?:_[0-9]+)?", stem, re.I)
    if matched:
        return SOCIAL_EXPORTS[matched.group(1).lower()]
    normalized = key(stem)
    return normalized if normalized in PROFESSIONAL_FIELDS or normalized == "connections" else None


def comment_export_records(raw, source, summary):
    """Preserve final-column text in LinkedIn's occasionally malformed comment CSV.

    This recovery is deliberately limited to the observed Date,Link,Message schema.
    It never interprets message text as instructions or guesses a person's identity.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None  # Other encodings retain the ordinary tabular import path.
    lines = text.splitlines(keepends=True)
    if not lines or [key(v) for v in next(csv.reader([lines[0]]), [])] != ["date", "link", "message"]:
        return None
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        next(reader)
        parsed, previous = [], 1
        for values in reader:
            line_end = reader.line_num
            if not values or not any(v.strip() for v in values):
                previous = line_end
                continue
            if len(values) != 3:
                raise csv.Error("Comment record does not have three fields.")
            row = dict(zip(("date", "link", "message"), values))
            row["_export"] = {"source": source, "record_number": len(parsed) + 1,
                              "line_start": previous + 1, "line_end": line_end,
                              "parsing": "strict_csv", "raw_block": "".join(lines[previous:line_end])}
            parsed.append(row)
            previous = line_end
        return parsed
    except csv.Error:
        pass

    # A field may contain literal commas, quotes and newlines. Only the first two
    # delimiters have a defensible meaning in this exact three-column schema.
    prefix = re.compile(r'^"?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"?,"?(https://www\.linkedin\.com/[^,\r\n"]+)"?,', re.M)
    matches = list(prefix.finditer(text))
    parsed, repaired = [], 0
    reason = None
    if not matches or text[len(lines[0]):matches[0].start()].strip():
        reason = "Unrecognized content before the first unambiguous comment record."
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_block = text[match.start():block_end]
        block = raw_block.rstrip("\r\n")
        try:
            datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            canonical_url(match.group(2))
        except (ValueError, Error):
            reason = "A candidate comment boundary has an invalid date or URL."
            break
        try:
            values = list(csv.reader(io.StringIO(block, newline=""), strict=True))
            if len(values) != 1 or len(values[0]) != 3:
                raise csv.Error("Unexpected comment field count.")
            row = dict(zip(("date", "link", "message"), values[0]))
            parsing = "strict_csv"
        except csv.Error:
            remainder = block[match.end() - match.start():]
            if len(remainder) < 2 or not (remainder.startswith('"') and remainder.endswith('"')):
                # A candidate might be a date/URL line inside someone else's text.
                # Quarantine this member instead of inventing a second comment.
                reason = "Ambiguous comment boundary or unmatched outer message quotes."
                break
            row = {"date": match.group(1), "link": match.group(2), "message": remainder[1:-1]}
            parsing = "final_column_boundary_recovery"
            repaired += 1
        row["_export"] = {"source": source, "record_number": index + 1,
                          "line_start": text.count("\n", 0, match.start()) + 1,
                          "line_end": text.count("\n", 0, block_end - 1) + 1,
                          "parsing": parsing, "raw_block": raw_block}
        if parsing != "strict_csv":
            row["_export"]["recovery_limits"] = "Exact final-column remainder with one observed outer quote pair removed; internal quotes, backslashes and newlines preserved literally; escape semantics unresolved."
        parsed.append(row)
    if reason:
        summary["quarantined_records"] += len(matches)
        summary["quarantine"].append({"source": source, "candidate_records": len(matches), "reason": reason,
                                      "scope": "entire_comment_member", "raw_source_retained": True})
        summary["warnings"].append("An ambiguous comment CSV member was quarantined with its unchanged raw source; no rows from that member were imported.")
        return []
    summary["recovered_comments"] += repaired
    if repaired:
        summary["warnings"].append("Malformed comment CSV quoting was recovered only at verified Date/LinkedIn URL boundaries; exact raw blocks and literal text are retained with recovery limits.")
    return parsed


def import_professional_section(s, rows, source, kind, summary):
    allowed = PROFESSIONAL_FIELDS[kind]
    for index, row in enumerate(rows[:60]):
        headers = [key(value) for value in row]
        if set(headers) & allowed:
            for values in rows[index + 1:]:
                sanitized = {headers[i]: str(value).strip() for i, value in enumerate(values[:len(headers)])
                             if headers[i] in allowed and str(value).strip()}
                if not sanitized:
                    continue
                dedup = digest(dump([kind, sanitized]))
                if s.one("SELECT id FROM history WHERE dedup_key=?", (dedup,)):
                    summary["updated"] += 1
                    continue
                s.insert("history", dict(id=ident("history"), kind=kind, text=dump(sanitized), source=source,
                                         raw_json=dump(sanitized), dedup_key=dedup))
                summary["inserted"] += 1
            return


class ArticleHTML(HTMLParser):
    """Extract plain text from a local export; no rendering, scripts or network."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    HIDDEN = {"script", "style", "template", "noscript", "iframe", "object", "svg"}
    BLOCK = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "li", "ul", "ol", "blockquote", "pre", "br", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.body, self.title, self.heading = [], [], [], []
        self.created, self.published, self.url = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.BLOCK:
            self.body.append("\n")
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.keep_url(attrs.get("href"))
        elif tag == "a" and any(t == "h1" for t, _ in self.stack):
            self.keep_url(attrs.get("href"))
        if tag not in self.VOID:
            self.stack.append((tag, attrs))

    def keep_url(self, value):
        try:
            self.url = canonical_url(value)
        except (Error, AttributeError):
            pass

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.body.append("\n")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        tags = {tag for tag, _ in self.stack}
        if tags & self.HIDDEN:
            return
        if "title" in tags:
            self.title.append(data)
            return
        if "h1" in tags:
            self.heading.append(data)
            return
        classes = {value for _, attrs in self.stack for value in attrs.get("class", "").split()}
        if "created" in classes:
            self.created.append(data)
        elif "published" in classes:
            self.published.append(data)
        elif "body" in tags:
            self.body.append(data)

    def article(self):
        clean = lambda values: re.sub(r"\s+", " ", "".join(values)).strip()
        published = re.sub(r"^Published on\s*", "", clean(self.published), flags=re.I)
        created = re.sub(r"^Created on\s*", "", clean(self.created), flags=re.I)
        published = None if published in ("", "---", "—") else published
        paragraphs = [re.sub(r"[\t \r\f\v]+", " ", line).strip() for line in "".join(self.body).splitlines()]
        return {"title": clean(self.heading) or clean(self.title), "body": "\n\n".join(line for line in paragraphs if line),
                "url": self.url, "created_at_export": created or None, "published_at_export": published,
                "export_state": "published" if published else "unpublished", "export_time_zone": None,
                "extraction": "Plain text from local HTML; scripts/styles/embedded frames excluded; no resources fetched."}


def import_article_html(s, raw, source, summary):
    try:
        html = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Error("Article HTML must be UTF-8.") from exc
    parser = ArticleHTML()
    parser.feed(html)
    parser.close()
    item = parser.article()
    if not (item["title"] or item["body"]):
        summary["skipped"] += 1
        summary["warnings"].append("An empty article HTML export had no usable title or body.")
        return
    dedup = digest(dump(["article_html", item]))
    if s.one("SELECT id FROM history WHERE dedup_key=?", (dedup,)):
        summary["updated"] += 1
        return
    # Export timestamps lack a zone. Keep them as evidence without inventing UTC.
    occurred = None
    if item["published_at_export"] and re.search(r"(Z|[+-]\d\d:\d\d)$", item["published_at_export"]):
        occurred = timestamp(item["published_at_export"])
    s.insert("history", dict(id=ident("history"), kind="articles", target_url=item["url"], text=item["title"] + "\n\n" + item["body"],
                             occurred_at=occurred, source=source, raw_json=dump(item), dedup_key=dedup))
    summary["inserted"] += 1
    summary["article_states"][item["export_state"]] += 1


def import_connections(s, table_rows, source, summary):
    for row in records(table_rows, "connections"):
        url = pick(row, "url", "profileurl", "linkedinurl", "publicprofileurl")
        name = pick(row, "name", "fullname") or " ".join(x for x in (pick(row, "firstname"), pick(row, "lastname")) if x)
        try:
            url = canonical_url(url, profile=True)
        except (Error, AttributeError):
            summary["skipped"] += 1
            summary["warnings"].append("Connections with missing/invalid profile URLs were retained as sanitized unresolved records; no URL was inferred.")
            sanitized = {"name": name, "company": pick(row, "company"), "position": pick(row, "position", "headline"),
                         "connected_at": pick(row, "connectedon", "connectedat", "connectiondate"), "reason": "missing_or_invalid_profile_url"}
            dedup = digest(dump(["unresolved_connections", sanitized]))
            if not s.one("SELECT id FROM history WHERE dedup_key=?", (dedup,)):
                s.insert("history", dict(id=ident("history"), kind="unresolved_connections", text=dump(sanitized), source=source, raw_json=dump(sanitized), dedup_key=dedup))
            summary["unresolved_connections"] += 1
            continue
        if not name:
            summary["skipped"] += 1
            continue
        existing = s.one("SELECT id FROM relationships WHERE profile_url=?", (url,))
        company, position = pick(row, "company"), pick(row, "position", "headline")
        connected = pick(row, "connectedon", "connectedat", "connectiondate")
        if existing:
            s.db.execute("UPDATE relationships SET name=?,company=COALESCE(?,company),position=COALESCE(?,position),connected_at=COALESCE(?,connected_at),updated_at=? WHERE id=?", (name, company, position, connected, now(), existing["id"]))
            summary["updated"] += 1
            person_id = existing["id"]
        else:
            person_id = ident("person")
            s.insert("relationships", dict(id=person_id, profile_url=url, name=name, company=company, position=position,
                                            connected_at=connected, source=source, created_at=now(), updated_at=now()))
            summary["inserted"] += 1
        observe_membership(s, person_id, "connection", now(), source, name=name, headline=position)


def metric_add(s, metric, value, source, observed_at, window, content_id=None, target_url=None, scope=None, transaction=True):
    if transaction:
        with s.transaction():
            return metric_add(s, metric, value, source, observed_at, window, content_id, target_url, scope, False)
    if content_id:
        s.require("content", content_id)
    target_url = canonical_url(target_url) if target_url else None
    if not content_id and target_url:
        linked = s.one("SELECT content_id FROM actions WHERE remote_url=? AND content_id IS NOT NULL", (target_url,))
        content_id = linked["content_id"] if linked else None
    metric = METRICS.get(key(metric), metric.strip().lower().replace(" ", "_"))
    if not re.fullmatch(r"[a-z][a-z0-9_]*", metric):
        raise Error("Invalid metric name.")
    val = number(value, allow_negative=window.startswith("day:") and metric in ("engagements", "followers_gained", "reactions", "comments", "reposts", "saves", "sends"))
    instant = timestamp(observed_at)
    scope = scope or ("post" if content_id or target_url else "account")
    if scope not in ("post", "account"):
        raise Error("Metric scope must be post or account.")
    if scope == "account" and (content_id or target_url):
        raise Error("Account metrics cannot carry a content ID or post URL.")
    if scope == "post" and not (content_id or target_url):
        raise Error("Post metrics require a content ID or post URL.")
    dedup = digest(dump([content_id, target_url, scope, metric, val, instant, window, source]))
    existing = s.one("SELECT id FROM metrics WHERE dedup_key=?", (dedup,))
    if existing:
        return {"existing": True, "id": existing["id"]}
    item = dict(id=ident("metric"), content_id=content_id, target_url=target_url, scope=scope, metric=metric, value=val,
                availability="unavailable" if val is None else "measured", observed_at=instant, window=window, source=source, dedup_key=dedup)
    s.insert("metrics", item)
    return item


def import_metrics(s, table_rows, source, summary, observed_at, window):
    for row in records(table_rows, "metrics"):
        content_id = pick(row, "content_id", "contentid")
        target = pick(row, "posturl", "postlink", "url", "targeturl", "link")
        instant = parse_date(pick(row, "observedat", "observationtime"), observed_at, s.settings["timezone"])
        row_date = pick(row, "date", "day")
        selected_window = pick(row, "window", "measurementwindow") or ("day:" + str(row_date).split("T")[0] if row_date else None) or window or "unspecified"
        if row_date and not pick(row, "window", "measurementwindow"):
            # Convert to local calendar date, not the preceding UTC date in India.
            from zoneinfo import ZoneInfo
            local_date = datetime.fromisoformat(parse_date(row_date, tz=s.settings["timezone"])).astimezone(ZoneInfo(s.settings["timezone"])).date()
            selected_window = "day:" + local_date.isoformat()
        scope = pick(row, "scope") or ("post" if content_id or target else "account")
        values = [(pick(row, "metric"), row.get("value"))] if pick(row, "metric") else [(METRICS[k], v) for k, v in row.items() if k in METRICS]
        for metric, value in values:
            try:
                item = metric_add(s, metric, value, source, instant, selected_window, content_id, target, scope, False)
                summary["updated" if item.get("existing") else "inserted"] += 1
            except Error as exc:
                raise Error("Metric import needs correction (" + metric + "): " + str(exc)) from exc


def import_native_sheet(s, name, rows, source, summary, observed_at, window):
    """LinkedIn's exported workbook contains summaries and independent ranking tables."""
    label = key(name)
    if label == "discovery":
        for row in rows:
            if len(row) >= 2 and key(row[0]) in METRICS:
                metric_add(s, METRICS[key(row[0])], row[1], source, observed_at, window or "unspecified", scope="account", transaction=False)
                summary["inserted"] += 1
        return True
    if label == "topposts":
        for index, row in enumerate(rows[:60]):
            starts = [i for i, value in enumerate(row) if key(value) == "posturl"]
            if starts:
                for group, start in enumerate(starts):
                    end = starts[group + 1] if group + 1 < len(starts) else len(row)
                    segment = [values[start:end] for values in rows[index:]]
                    # Trailing empty ranking slots are absent, not zero-valued posts.
                    segment = [segment[0]] + [r for r in segment[1:] if r and str(r[0]).strip()]
                    import_metrics(s, segment, source, summary, observed_at, window)
                return True
        return False
    if label == "followers":
        for row in rows[:10]:
            if len(row) >= 2 and key(row[0]).startswith("totalfollowerson"):
                metric_add(s, "followers", row[1], source, observed_at, "snapshot:" + row[0].replace("Total followers on ", ""), scope="account", transaction=False)
                summary["inserted"] += 1
        import_metrics(s, rows, source, summary, observed_at, window)
        return True
    if label in ("audiencedemographics", "contentdemographics"):
        for row in rows[1:]:
            if len(row) < 3 or not row[0]:
                continue
            record = {"dimension": row[0], "label": row[1], "percentage_reported": row[2], "window": window or "unspecified", "observed_at": observed_at}
            # Preserve '<1%' as a bound. Never turn it into a point estimate.
            dedup = digest(dump([label, record, source]))
            if s.one("SELECT id FROM history WHERE dedup_key=?", (dedup,)):
                summary["updated"] += 1
                continue
            s.insert("history", dict(id=ident("history"), kind=label, text=str(row[1]), occurred_at=observed_at, source=source, raw_json=dump(record), dedup_key=dedup))
            summary["inserted"] += 1
        return True
    return False


def import_history(s, table_rows, source, kind, summary, supplied_records=None):
    selected_records = records(table_rows, "history") if supplied_records is None else supplied_records
    for record_number, row in enumerate(selected_records, 1):
        target = pick(row, "url", "link", "sharelink", "articleurl", "posturl")
        if target:
            try:
                target = canonical_url(target)
            except Error:
                target = None
        text = pick(row, "text", "comment", "message", "sharecommentary", "commentary", "content", "title", "reactiontype", "type")
        raw_date = pick(row, "date", "createdat", "publisheddate", "time", "timestamp")
        export = row.setdefault("_export", {"source": source, "record_number": record_number})
        export.update(raw_date=raw_date, time_zone=None, date_status="missing")
        instant = None
        if raw_date and re.search(r"(Z|[+-]\d\d:?\d\d)$", raw_date):
            try:
                instant = timestamp(raw_date)
                export.update(time_zone="explicit_export_offset", date_status="explicit_offset")
            except Error:
                export["date_status"] = "unrecognized"
                summary["warnings"].append("History date could not be normalized; original date preserved.")
        elif raw_date:
            export["date_status"] = "zone_unspecified"
            summary["warnings"].append("Social export timestamps have no stated time zone; raw dates are retained and occurred_at is unavailable rather than assumed UTC/local time.")
        if kind == "profile":
            # Relevant professional fields only, excluding birth date, street address,
            # private contact/email fields and other unrelated account details.
            allowed = {"firstname", "lastname", "headline", "summary", "industry", "geolocation", "websites", "profileurl", "linkedinurl"}
            row = {k: v for k, v in row.items() if k in allowed}
            text = dump(row)
        dedup = digest(dump([kind, target, text, raw_date]))
        existing = s.one("SELECT id,raw_json FROM history WHERE dedup_key=?", (dedup,))
        if kind == "shares":
            # LinkedIn exports one row per media attachment for some posts. Keep
            # the established post identity while retaining every source row.
            source_row = {"source": source, "record": {k: v for k, v in row.items() if k != "_export"}}
            export["source_rows"] = [source_row]
            export["media_urls"] = [row["mediaurl"]] if row.get("mediaurl") else []
            if existing:
                kept = json.loads(existing["raw_json"])
                kept_export = kept.setdefault("_export", {})
                if "source_rows" not in kept_export:
                    kept_export["source_rows"] = [{"source": kept_export.get("source", "earlier_import"),
                                                   "record": {k: v for k, v in kept.items() if k != "_export"}}]
                if source_row not in kept_export["source_rows"]:
                    kept_export["source_rows"].append(source_row)
                    summary["merged_share_rows"] += 1
                kept_export["media_urls"] = sorted({entry["record"].get("mediaurl") for entry in kept_export["source_rows"] if entry["record"].get("mediaurl")})
                s.db.execute("UPDATE history SET raw_json=? WHERE id=?", (dump(kept), existing["id"]))
        if existing:
            summary["updated"] += 1
            continue
        s.insert("history", dict(id=ident("history"), kind=kind, target_url=target, text=text, occurred_at=instant, source=source, raw_json=dump(row), dedup_key=dedup))
        summary["inserted"] += 1


def import_file(s, kind, file, observed_at=None, window=None):
    if kind == "followers":
        from .followers import import_followers
        return import_followers(s, file, observed_at)
    path = Path(file).expanduser().resolve()
    raw = path.read_bytes()
    checksum = digest(raw)
    existing = s.one("SELECT * FROM imports WHERE kind=? AND sha256=?", (kind, checksum))
    if existing:
        existing["summary"] = json.loads(existing.pop("summary_json"))
        return {"existing": True, "import": existing}
    instant = timestamp(observed_at) if observed_at else now()
    summary = {"inserted": 0, "updated": 0, "skipped": 0, "warnings": [], "selected_files": [], "ignored_files": [],
               "unresolved_connections": 0, "article_states": {"published": 0, "unpublished": 0},
               "recovered_comments": 0, "quarantined_records": 0, "quarantine": [], "merged_share_rows": 0}
    stored = "data/imports/" + checksum[:16] + path.suffix.lower()
    source = "user_export:" + stored
    with s.transaction():
        # Recheck after acquiring the writer lock.
        if s.one("SELECT id FROM imports WHERE kind=? AND sha256=?", (kind, checksum)):
            raise Error("This import was already processed by another session.")
        if kind == "archive" and path.suffix.lower() == ".zip":
            with safe_zip(raw) as archive:
                for name in archive.namelist():
                    member = PurePosixPath(name)
                    if member.suffix.lower() in (".html", ".htm") and any(part.lower() == "articles" for part in member.parts[:-1]):
                        summary["selected_files"].append(name)
                        import_article_html(s, archive.read(name), source + "#" + name, summary)
                        continue
                    selected = archive_section(member.stem) if member.suffix.lower() == ".csv" else None
                    if not selected:
                        summary["ignored_files"].append(name)
                        continue
                    summary["selected_files"].append(name)
                    member_raw = archive.read(name)
                    comment_records = comment_export_records(member_raw, source + "#" + name, summary) if selected == "comments" else None
                    rows = csv_rows(member_raw) if comment_records is None else []
                    if selected == "connections":
                        import_connections(s, rows, source + "#" + name, summary)
                    elif selected in PROFESSIONAL_FIELDS:
                        import_professional_section(s, rows, source + "#" + name, selected, summary)
                    else:
                        import_history(s, rows, source + "#" + name, selected, summary, comment_records)
        else:
            comment_records = comment_export_records(raw, source + "#" + path.stem, summary) if kind == "archive" and archive_section(path.stem) == "comments" else None
            file_tables = tables(path, raw) if comment_records is None else [(path.stem, [])]
            if kind == "metrics" and not window:
                for name, rows in file_tables:
                    if key(name) == "discovery" and rows and len(rows[0]) >= 2:
                        window = "export_range:" + str(rows[0][1])
            for name, rows in file_tables:
                summary["selected_files"].append(name)
                if kind == "connections":
                    import_connections(s, rows, source + "#" + name, summary)
                elif kind == "metrics":
                    if not import_native_sheet(s, name, rows, source + "#" + name, summary, instant, window):
                        import_metrics(s, rows, source + "#" + name, summary, instant, window)
                else:
                    selected = archive_section(path.stem)
                    if selected in PROFESSIONAL_FIELDS:
                        import_professional_section(s, rows, source + "#" + name, selected, summary)
                    elif selected in SOCIAL_EXPORTS.values():
                        import_history(s, rows, source + "#" + name, selected, summary, comment_records)
                    else:
                        raise Error("Archive CSV must be a supported professional profile, Shares, Comments, Reactions, InstantReposts or Articles export.")
        if not summary["inserted"] and not summary["updated"] and not summary["unresolved_connections"] and not summary["quarantine"]:
            raise Error("No supported rows found. Inspect the export headers; no data was imported.")
        summary["warnings"] = sorted(set(summary["warnings"]))
        s.write(stored, raw)
        item = dict(id=ident("import"), kind=kind, sha256=checksum, source_path=str(path), stored_path=stored, imported_at=now(), summary_json=dump(summary))
        s.insert("imports", item)
    item["summary"] = summary
    item.pop("summary_json")
    return {"existing": False, "import": item}
