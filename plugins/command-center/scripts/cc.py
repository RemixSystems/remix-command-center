#!/usr/bin/env python3
"""Command Center, a set of lenses on a personal AI operating system.

Reads a folder of Markdown notes (an Obsidian vault or any notes folder), plus the
Claude Code session logs for that folder if they exist, and answers one question
per lens. Files only. Nothing is uploaded. Nothing is written inside the notes folder.

Usage
    cc.py scan    <folder>              write scan.json and print where it went
    cc.py health  <folder>              health score out of 100, four dimensions, five fixes
    cc.py level   <folder>              level 1 to 5 with one proof per level
    cc.py wrapped <folder> [--days 90]  your habit over a season, count only
    cc.py all     <folder>              every lens on one page

Options
    --out DIR        where reports go (default ~/.cache/command-center/<folder-name>)
    --days N         window for wrapped and recent-activity checks (default 90)
    --sessions DIR   Claude Code session folder to read (default: the one for <folder>)
    --no-sessions    ignore Claude Code session logs
    --include-user   let the level lens count skills and settings in ~/.claude too
    --json           print the lens result as JSON instead of the text report

python3 standard library only.
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

VERSION = "0.1.0"

SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", ".venv", "__pycache__", ".claude"}
# Folders where an unlinked note is normal. Reported in every evidence line that uses it.
MACHINE_ZONE_RE = re.compile(r"(^|/)(?:\d+[-_ ]*)?(templates?|_?templates|archive|_archive|attachments?|assets|media|bins?|trash|_trash)(/|$)", re.I)
INDEX_NAMES = {"index", "readme", "moc", "_moc", "_index", "home", "start here", "overview"}
GUIDANCE_FILES = ["CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules"]
INBOX_RE = re.compile(r"(^|/)(0+[-_ ]?)?inbox(/|$)", re.I)
PROFILE_RE = re.compile(r"(about[-_ ]?me|profile|^me$|^user$|who[-_ ]?i[-_ ]?am)", re.I)

WIKILINK_RE = re.compile(r"!?\[\[([^\]\n]+?)\]\]")
MDLINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\s]+?)\)")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
TAG_RE = re.compile(r"(?:^|\s)#[A-Za-z][\w/-]*")
FIELD_RE = re.compile(r"^\s*[-*]?\s*\[?[A-Za-z][\w -]{0,40}::", re.M)
DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
CREATED_RE = re.compile(r"^\s*created\s*:{1,2}\s*\"?(\d{4}-\d{2}-\d{2})", re.M | re.I)
PROCESSED_RE = re.compile(r"(^\s*(status|processed)\s*:{1,2}\s*(processed|done|true|yes)\b|#processed\b)", re.M | re.I)
SECRET_RES = [
    ("Anthropic or OpenAI key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]
NAMING_STYLES = [
    ("dated", re.compile(r"^\d{4}-\d{2}-\d{2}")),
    ("kebab", re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")),
    ("single-word", re.compile(r"^[A-Za-z0-9_]+$")),
    ("title", re.compile(r"^[A-Z0-9].* .*$")),
    ("lower-spaced", re.compile(r"^[a-z0-9]+(?: [a-z0-9]+)+$")),
]

NOW = dt.datetime.now()
TODAY = NOW.date()


# ---------------------------------------------------------------- helpers

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "notes"


def lerp_score(value, full_at, zero_at, pts):
    """Linear points. full_at may be above or below zero_at."""
    if full_at == zero_at:
        return pts if value == full_at else 0
    t = (value - zero_at) / (full_at - zero_at)
    return round(max(0.0, min(1.0, t)) * pts, 1)


def pct(n, d):
    return 0.0 if d == 0 else round(100.0 * n / d, 1)


def naming_style(stem):
    for name, rx in NAMING_STYLES:
        if rx.match(stem):
            return name
    return "other"


def strip_frontmatter(text):
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[4:end], text[end + 4:]
    return "", text


def first_prose_line(body):
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", "|", ">", "-", "*", "!", "```", "<", "up::")) or re.match(r"^\d+\.", line):
            if line.startswith("#") and not line.startswith("# ") and not line.startswith("##"):
                return None  # a tag line before any prose
            continue
        if FIELD_RE.match(line):
            continue
        return line
    return None


def session_dir_for(folder):
    enc = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(folder))
    return os.path.join(os.path.expanduser("~/.claude/projects"), enc)


# ---------------------------------------------------------------- scan

def scan(folder, days=90, sessions=None, no_sessions=False, include_user=False):
    root = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(root):
        raise SystemExit(f"command-center: no folder at {root}")
    notes = []
    other_files = set()
    env_files = []
    folders_with_notes = Counter()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir
        for fn in filenames:
            rel = os.path.join(rel_dir, fn) if rel_dir else fn
            if fn == ".env" or fn.startswith(".env."):
                env_files.append(rel)
            if not fn.lower().endswith(".md"):
                other_files.add(fn.lower())
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                st = os.stat(full)
            except OSError:
                continue
            notes.append(read_note(rel, text, st))
            folders_with_notes[rel_dir] += 1
    # also catch .env files inside skipped dot folders at the root
    for fn in os.listdir(root):
        if (fn == ".env" or fn.startswith(".env.")) and fn not in env_files:
            env_files.append(fn)

    resolve_links(notes, other_files)
    data = {
        "tool": "command-center",
        "version": VERSION,
        "scanned_at": NOW.isoformat(timespec="seconds"),
        "folder_name": os.path.basename(root),
        "root": root,
        "days": days,
        "notes": notes,
        "folders": dict(folders_with_notes),
        "env_files": sorted(env_files),
        "guidance": read_guidance(root, folders_with_notes),
        "git": read_git(root),
        "claude": read_claude_dir(os.path.join(root, ".claude")),
        "user_claude": read_claude_dir(os.path.expanduser("~/.claude")) if include_user else None,
        "sessions": None,
    }
    if not no_sessions:
        sdir = os.path.abspath(os.path.expanduser(sessions)) if sessions else session_dir_for(root)
        data["sessions"] = read_sessions(sdir, days)
    return data


def read_note(rel, text, st):
    fm, body = strip_frontmatter(text)
    clean = INLINE_CODE_RE.sub("", FENCE_RE.sub("", body))
    stem = os.path.splitext(os.path.basename(rel))[0]
    created = None
    m = DATE_PREFIX_RE.match(stem)
    if m:
        created = m.group(0)
    else:
        m = CREATED_RE.search(fm) or CREATED_RE.search(body)
        if m:
            created = m.group(1)
    links = []
    for raw in WIKILINK_RE.findall(clean):
        target = raw.split("|", 1)[0].split("#", 1)[0].split("^", 1)[0].strip().rstrip("\\").strip()
        if target:
            links.append(target)
    for raw in MDLINK_RE.findall(clean):
        if "://" in raw or raw.startswith(("mailto:", "#")):
            continue
        target = raw.split("#", 1)[0]
        target = re.sub(r"%20", " ", target)
        if target:
            links.append(target)
    words = len(re.findall(r"\w+", clean))
    has_meta = bool(fm.strip()) or bool(TAG_RE.search(clean)) or bool(FIELD_RE.search(clean))
    opener = first_prose_line(body)
    return {
        "path": rel,
        "stem": stem,
        "folder": os.path.dirname(rel),
        "words": words,
        "mtime": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "created": created,
        "has_meta": has_meta,
        "has_opener": bool(opener and len(opener.split()) >= 6),
        "processed_marker": bool(PROCESSED_RE.search(fm) or PROCESSED_RE.search(clean)),
        "links_raw": links,
        "secrets": [name for name, rx in SECRET_RES if rx.search(text)],
        "machine_zone": bool(MACHINE_ZONE_RE.search(os.path.dirname(rel) + "/")),
        "is_index": is_index(rel, stem),
    }


def is_index(rel, stem):
    s = stem.lower().strip("_ ")
    folder = re.sub(r"^[\d]+[-_. ]*", "", os.path.basename(os.path.dirname(rel)).lower()).strip()
    return s in INDEX_NAMES or "moc" in s.split() or s.startswith("moc ") or s.endswith(" moc") or (folder and s == folder) or s.startswith("_moc")


def resolve_links(notes, other_files):
    by_stem = defaultdict(list)
    by_path = {}
    for n in notes:
        by_stem[n["stem"].lower()].append(n["path"])
        by_path[os.path.splitext(n["path"])[0].lower()] = n["path"]
    inbound = Counter()
    for n in notes:
        out, unresolved = [], []
        for t in n["links_raw"]:
            tl = t.lower().lstrip("./")
            base, ext = os.path.splitext(tl)
            if ext and ext != ".md":
                if os.path.basename(tl) in other_files:
                    continue  # attachment that exists, not a note link
                unresolved.append(t)
                continue
            key = base if ext == ".md" else tl
            hit = None
            if "/" in key:
                if key in by_path:
                    hit = by_path[key]
                else:
                    cands = [p for k, p in by_path.items() if k.endswith("/" + key) or k == key]
                    hit = cands[0] if cands else None
                    if not hit:
                        rel_try = os.path.normpath(os.path.join(n["folder"], key)).lower()
                        hit = by_path.get(rel_try)
            else:
                c = by_stem.get(key)
                hit = c[0] if c else None
            if hit:
                if hit != n["path"]:
                    out.append(hit)
            else:
                unresolved.append(t)
        n["links_out"] = sorted(set(out))
        n["unresolved"] = unresolved
        for h in n["links_out"]:
            inbound[h] += 1
        del n["links_raw"]
    for n in notes:
        n["inbound"] = inbound.get(n["path"], 0)


def read_guidance(root, folders):
    for name in GUIDANCE_FILES:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            lines = text.count("\n") + 1
            refs = set(re.findall(r"\[\[([^\]|#]+)", text)) | set(re.findall(r"`([^`\n]+/)`", text)) | set(re.findall(r"`([^`\n]+\.md)`", text))
            # A folder claim is a backticked token that ends in "/" (`Projects/`), or one that
            # starts like a numbered folder (`10-Projects`). Only top-level names are checked.
            named = set()
            for tok in re.findall(r"`([^`\n]{1,60})`", text):
                tok = tok.strip()
                if tok.startswith(("~", "$", "/", ".", "-")):
                    continue
                # one folder name only (`Projects/`), not a path inside some other folder
                dname = tok.rstrip("/")
                if (tok.endswith("/") or re.match(r"^\d{2}[-_ ]\w", tok)) and dname and "/" not in dname and "." not in dname:
                    named.add(dname)
            named = sorted(named)
            all_dirs = set()
            for dp, dns, _ in os.walk(root):
                dns[:] = [d for d in dns if d not in SKIP_DIRS]
                all_dirs.update(d.lower() for d in dns)
            missing = [d for d in named if d.lower() not in all_dirs]
            return {"file": name, "lines": lines, "refs": len(refs), "named_folders": named, "missing_folders": missing}
    return None


def read_git(root):
    cfg = os.path.join(root, ".git", "config")
    if not os.path.isfile(cfg):
        return {"repo": False, "remote": False, "gitignore": os.path.isfile(os.path.join(root, ".gitignore"))}
    with open(cfg, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return {"repo": True, "remote": "[remote " in text, "gitignore": os.path.isfile(os.path.join(root, ".gitignore"))}


def read_claude_dir(cdir):
    if not os.path.isdir(cdir):
        return None
    out = {"skills": 0, "commands": 0, "agents": 0, "hooks": 0, "mcp_servers": 0, "plugins": 0}
    for kind in ("skills", "commands", "agents"):
        d = os.path.join(cdir, kind)
        if os.path.isdir(d):
            if kind == "skills":
                out[kind] = sum(1 for e in os.listdir(d) if os.path.isfile(os.path.join(d, e, "SKILL.md")))
            else:
                out[kind] = sum(1 for _, _, fs in os.walk(d) for f in fs if f.endswith(".md"))
    for sf in ("settings.json", "settings.local.json"):
        p = os.path.join(cdir, sf)
        if os.path.isfile(p):
            try:
                with open(p) as fh:
                    s = json.load(fh)
            except (OSError, ValueError):
                continue
            for ev, groups in (s.get("hooks") or {}).items():
                for g in groups or []:
                    out["hooks"] += len(g.get("hooks", [])) if isinstance(g, dict) else 0
            out["mcp_servers"] += len(s.get("mcpServers") or {})
            out["plugins"] += sum(1 for v in (s.get("enabledPlugins") or {}).values() if v)
    mcp = os.path.join(os.path.dirname(cdir), ".mcp.json")
    if os.path.isfile(mcp):
        try:
            with open(mcp) as fh:
                out["mcp_servers"] += len(json.load(fh).get("mcpServers") or {})
        except (OSError, ValueError):
            pass
    return out


def read_sessions(sdir, days):
    """Count-only read of Claude Code session logs. Never keeps message text."""
    res = {"dir": sdir, "found": False, "sessions": 0, "prompts": 0, "days_active": 0,
           "sessions_30d": 0, "by_hour": [0] * 24, "by_weekday": [0] * 7, "skills": {}, "mcp_calls": 0,
           "tool_calls": 0, "first": None, "last": None}
    if not os.path.isdir(sdir):
        return res
    res["found"] = True
    cutoff = NOW - dt.timedelta(days=days)
    cut30 = NOW - dt.timedelta(days=30)
    day_set = set()
    skills = Counter()
    for fn in os.listdir(sdir):
        if not fn.endswith(".jsonl"):
            continue
        p = os.path.join(sdir, fn)
        try:
            if dt.datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
                continue
        except OSError:
            continue
        counted, in30 = False, False
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"timestamp"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = rec.get("timestamp")
                if not ts:
                    continue
                try:
                    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
                except ValueError:
                    continue
                if t < cutoff:
                    continue
                msg = rec.get("message") or {}
                if rec.get("type") == "user" and isinstance(msg.get("content"), str):
                    res["prompts"] += 1
                    res["by_hour"][t.hour] += 1
                    res["by_weekday"][t.weekday()] += 1
                    day_set.add(t.date().isoformat())
                    counted = True
                    in30 = in30 or t >= cut30
                    res["first"] = min(res["first"] or ts, ts)
                    res["last"] = max(res["last"] or ts, ts)
                elif rec.get("type") == "assistant" and isinstance(msg.get("content"), list):
                    for part in msg["content"]:
                        if isinstance(part, dict) and part.get("type") == "tool_use":
                            res["tool_calls"] += 1
                            name = part.get("name", "")
                            if name.startswith("mcp__"):
                                res["mcp_calls"] += 1
                            if name == "Skill":
                                sk = (part.get("input") or {}).get("skill")
                                if sk:
                                    skills[str(sk)[:60]] += 1
        if counted:
            res["sessions"] += 1
            res["sessions_30d"] += 1 if in30 else 0
    res["days_active"] = len(day_set)
    res["skills"] = dict(skills.most_common(10))
    return res


# ---------------------------------------------------------------- health lens

def note_dt(n):
    return dt.datetime.fromisoformat(n["mtime"])


def health(data):
    notes = data["notes"]
    organic = [n for n in notes if not n["machine_zone"]]
    by_path = {n["path"]: n for n in notes}
    checks = []

    def add(dim, key, title, pts, earned, evidence, fix, minutes, applicable=True):
        checks.append({"dimension": dim, "key": key, "title": title, "max": pts,
                       "earned": round(earned, 1) if applicable else None, "applicable": applicable,
                       "evidence": evidence, "fix": fix, "minutes": minutes})

    zone_note = "templates, archive and attachment folders left out"
    # ---- Structure (25)
    if organic:
        ok = sum(1 for n in organic if n["has_opener"] and n["has_meta"])
        p = pct(ok, len(organic))
        add("Structure", "anatomy", "Notes open with a sentence and carry tags or fields", 6, lerp_score(p, 80, 20, 6),
            f"{ok} of {len(organic)} notes ({p}%) open with a prose line and carry a tag, field or front matter. {zone_note}",
            "Give your busiest notes a one-sentence opener that says why the note exists, and one tag", 30)
    styles_by_folder = defaultdict(Counter)
    for n in organic:
        if not n["is_index"]:
            styles_by_folder[n["folder"]][naming_style(n["stem"])] += 1
    tot = sum(sum(c.values()) for c in styles_by_folder.values())
    # "other" is never a style, so a folder of unpatterned names does not count as consistent
    match = sum(max([v for k, v in c.items() if k != "other"] or [0]) for c in styles_by_folder.values())
    if tot >= 5:
        p = pct(match, tot)
        add("Structure", "naming", "File names follow one style per folder", 5, lerp_score(p, 90, 50, 5),
            f"{match} of {tot} notes ({p}%) match the most common naming style in their folder",
            "Pick one naming style per folder (dated, kebab-case or Title Case) and rename the outliers", 20)
    root_notes = [n for n in notes if n["folder"] == "" and not n["is_index"] and n["path"] not in GUIDANCE_FILES]
    if notes:
        p = pct(len(root_notes), len(notes))
        earned = 5 if len(root_notes) <= 5 else lerp_score(p, 2, 25, 5)
        add("Structure", "routing", "Few loose notes at the top level", 5, earned,
            f"{len(root_notes)} notes sit loose at the top level ({p}% of all notes)",
            "Move loose top-level notes into the folder they belong to, or into an inbox to sort later", 15)
    idx_folders = {}
    for n in notes:
        if n["is_index"]:
            idx_folders.setdefault(n["folder"], n)
    sib_total = sib_linked = 0
    drift = 0
    stale = 0
    idx_counted = 0
    for folder, idx in idx_folders.items():
        sibs = [n for n in notes if n["folder"] == folder and n["path"] != idx["path"]]
        if len(sibs) < 3:
            continue
        idx_counted += 1
        linked = set(idx["links_out"])
        sib_total += len(sibs)
        sib_linked += sum(1 for s in sibs if s["path"] in linked)
        idx_t = note_dt(idx)
        drift += sum(1 for s in sibs if note_dt(s) > idx_t and s["path"] not in linked)
        recent = any(note_dt(s) > NOW - dt.timedelta(days=30) for s in sibs)
        if recent and idx_t < NOW - dt.timedelta(days=30):
            stale += 1
    if idx_counted:
        p = pct(sib_linked, sib_total)
        add("Structure", "index_sync", "Index notes list the notes beside them", 5, lerp_score(p, 90, 40, 5),
            f"{idx_counted} index notes cover {sib_total} notes, {sib_linked} of them ({p}%) are linked from their index",
            "Open each index note and link the notes in its folder that it does not list", 30)
    else:
        add("Structure", "index_sync", "Index notes list the notes beside them", 5, 0,
            "No folder with three or more notes has an index note (index, README, MOC or the folder's own name)",
            "Give your two busiest folders an index note that links every note in them", 30, applicable=False)
    tmpl = [n for n in notes if re.search(r"(^|/)_?templates?(/|$)", n["folder"] + "/", re.I)]
    if tmpl:
        ok = sum(1 for n in tmpl if n["has_meta"])
        p = pct(ok, len(tmpl))
        add("Structure", "templates", "Templates produce tagged notes", 4, lerp_score(p, 100, 0, 4),
            f"{ok} of {len(tmpl)} templates carry a tag, field or front matter",
            "Add a type tag to each template so every new note starts tagged", 10)
    else:
        add("Structure", "templates", "Templates produce tagged notes", 4, 0, "No templates folder found",
            "Optional. A templates folder with tagged templates keeps new notes consistent", 10, applicable=False)

    # ---- Connection (30)
    total_links = sum(len(n["links_out"]) + len(n["unresolved"]) for n in notes)
    unresolved = sum(len(n["unresolved"]) for n in notes)
    if total_links:
        p = pct(unresolved, total_links)
        worst = sorted([n for n in notes if not n["machine_zone"]], key=lambda n: -len(n["unresolved"]))[:3]
        ex = ", ".join(f"{w['path']} ({len(w['unresolved'])})" for w in worst if w["unresolved"])
        add("Connection", "unresolved", "Links point at notes that exist", 6, lerp_score(p, 1, 10, 6),
            f"{unresolved} of {total_links} links ({p}%) point at a note that does not exist" + (f". Most in {ex}" if ex else ""),
            "Fix or remove broken links, starting with the files named in the evidence", 20)
    else:
        add("Connection", "unresolved", "Links point at notes that exist", 6, 0, "The notes hold no links at all",
            "Start linking notes to each other with [[double brackets]]", 20)
    orph_pool = [n for n in organic if not n["is_index"] and n["path"] not in GUIDANCE_FILES]
    orphans = [n for n in orph_pool if n["inbound"] == 0]
    if orph_pool:
        p = pct(len(orphans), len(orph_pool))
        add("Connection", "orphans", "Notes have at least one link pointing in", 7, lerp_score(p, 10, 50, 7),
            f"{len(orphans)} of {len(orph_pool)} notes ({p}%) have no link pointing at them. {zone_note}, index notes left out",
            "Link each orphan from the index or hub it belongs to", 30)
    top = max((n["inbound"] for n in notes), default=0)
    need = max(10, math.ceil(0.05 * len(notes)))
    hub = max(notes, key=lambda n: n["inbound"]) if notes else None
    add("Connection", "hubs", "At least one hub note pulls the graph together", 5, lerp_score(top, need, 2, 5),
        f"The most linked-to note is {hub['path'] if hub else 'none'} with {top} links in. Full points at {need}",
        "Pick a home note and link your main areas from it, and link back to it from each area", 15)
    newest = sorted(organic, key=note_dt, reverse=True)[:10]
    if newest:
        ok = sum(1 for n in newest if n["links_out"])
        p = pct(ok, len(newest))
        add("Connection", "hot_spots", "New notes link out when they are written", 6, lerp_score(p, 90, 30, 6),
            f"{ok} of the {len(newest)} newest notes link to at least one other note",
            "When you write a note, link the people, projects and ideas it mentions", 15)
    hubs = {n["path"] for n in notes if n["is_index"] or n["inbound"] >= 10}
    if organic and hubs:
        ok = sum(1 for n in organic if hubs.intersection(n["links_out"]) or n["path"] in hubs)
        p = pct(ok, len(organic))
        add("Connection", "parent_links", "Notes link up to a hub or index", 3, lerp_score(p, 80, 20, 3),
            f"{ok} of {len(organic)} notes ({p}%) link to an index note or a hub with 10+ links in",
            "End each note with a line that links its parent index or hub", 20)
    if organic:
        dead = [n for n in organic if not n["links_out"]]
        p = pct(len(dead), len(organic))
        add("Connection", "dead_ends", "Notes link out", 3, lerp_score(p, 15, 60, 3),
            f"{len(dead)} of {len(organic)} notes ({p}%) link to nothing",
            "Add at least one link out to each dead-end note", 20)

    # ---- Currency (25)
    if idx_counted:
        p = pct(drift, sib_total)
        add("Currency", "index_drift", "Index notes keep up with new notes", 6, lerp_score(p, 5, 40, 6),
            f"{drift} notes are newer than their folder's index and are not linked from it",
            "Add new notes to their folder's index the day you write them", 15)
        p2 = pct(stale, idx_counted)
        add("Currency", "stale_hubs", "Busy folders have a fresh index", 5, lerp_score(p2, 0, 50, 5),
            f"{stale} of {idx_counted} index notes are 30+ days old while their folder changed in the last 30 days",
            "Touch up the stale index notes so they say what is current", 15)
    else:
        add("Currency", "index_drift", "Index notes keep up with new notes", 6, 0, "No index notes to compare against",
            "Comes with index notes, see the index check", 0, applicable=False)
        add("Currency", "stale_hubs", "Busy folders have a fresh index", 5, 0, "No index notes to compare against",
            "Comes with index notes, see the index check", 0, applicable=False)
    inbox = [n for n in notes if INBOX_RE.search(n["folder"] + "/") and not n["is_index"]]
    if inbox or any(INBOX_RE.search(f + "/") for f in data["folders"]):
        old = [n for n in inbox if note_dt(n) < NOW - dt.timedelta(days=14)]
        add("Currency", "backlog", "The inbox gets emptied", 5, lerp_score(len(old), 2, 30, 5),
            f"{len(old)} of {len(inbox)} inbox notes are older than 14 days",
            "Sort the inbox notes older than two weeks, file them or archive them", 20)
    else:
        add("Currency", "backlog", "The inbox gets emptied", 5, 0, "No inbox folder found",
            "Optional. An inbox folder gives captures one place to land", 0, applicable=False)
    marked = [n for n in notes if n["processed_marker"]]
    if marked:
        lies = [n for n in marked if n["words"] < 30]
        p = pct(len(lies), len(marked))
        add("Currency", "stamp_honesty", "Notes marked done actually hold something", 5, lerp_score(p, 0, 30, 5),
            f"{len(lies)} of {len(marked)} notes marked processed or done hold under 30 words",
            "Open the notes marked done with no body and either write the summary or unmark them", 15)
    else:
        add("Currency", "stamp_honesty", "Notes marked done actually hold something", 5, 0,
            "No notes carry a processed or done marker", "", 0, applicable=False)
    if notes:
        newest_n = max(notes, key=note_dt)
        age = (NOW - note_dt(newest_n)).days
        recent = sum(1 for n in notes if note_dt(n) > NOW - dt.timedelta(days=30))
        earned = min(lerp_score(age, 3, 60, 4), lerp_score(recent, 5, 0, 4))
        add("Currency", "freshness", "Notes are still being written", 4, earned,
            f"Newest note changed {age} days ago. {recent} notes changed in the last 30 days",
            "Write or update one note a day for a week", 10)

    # ---- Leverage (20)
    g = data["guidance"]
    if g:
        routes = g["refs"] >= 3
        short = g["lines"] <= 400
        earned = 2 + (2 if routes else 0) + (1 if short else 0)
        add("Leverage", "guidance", "An AI guidance file exists and points to the right places", 5, earned,
            f"{g['file']} has {g['lines']} lines and {g['refs']} links or paths",
            "Keep the guidance file short and make it point to notes instead of holding everything", 20)
    else:
        add("Leverage", "guidance", "An AI guidance file exists and points to the right places", 5, 0,
            "No CLAUDE.md, AGENTS.md or GEMINI.md at the top level",
            "Add a CLAUDE.md that says who you are, how the folders work and where to look first", 20)
    s = data["sessions"]
    if s and s["found"]:
        add("Leverage", "ai_ran", "AI worked in this folder in the last 30 days", 5, lerp_score(s["sessions_30d"], 10, 0, 5),
            f"{s['sessions_30d']} Claude Code sessions in the last 30 days, read from the session log dates",
            "Open Claude Code in this folder for your next planning or writing task", 5)
    elif data["claude"]:
        add("Leverage", "ai_ran", "AI worked in this folder in the last 30 days", 5, 0,
            "A .claude folder exists but no Claude Code session log was found for this folder",
            "Open Claude Code in this folder for your next planning or writing task", 5)
    else:
        add("Leverage", "ai_ran", "AI worked in this folder in the last 30 days", 5, 0,
            "No Claude Code session log found for this folder", "", 0, applicable=False)
    secret_notes = [n for n in notes if n["secrets"]]
    findings = len(secret_notes) + len(data["env_files"])
    gi_ok = (not data["git"]["repo"]) or data["git"]["gitignore"]
    earned = 5 if findings == 0 and gi_ok else (2 if findings == 0 else 0)
    ev = f"{len(secret_notes)} notes look like they hold a key or token, {len(data['env_files'])} .env files in the folder"
    if data["git"]["repo"] and not data["git"]["gitignore"]:
        ev += ", git repo with no .gitignore"
    if secret_notes:
        ev += ". Files: " + ", ".join(n["path"] for n in secret_notes[:5])
    add("Leverage", "secrets", "No keys or tokens sit in notes", 5, earned, ev,
        "Move keys into a password manager, delete them from the notes, and rotate any that were synced or pushed", 20)
    if g and g["named_folders"]:
        ok = len(g["named_folders"]) - len(g["missing_folders"])
        p = pct(ok, len(g["named_folders"]))
        add("Leverage", "claims", "The guidance file describes folders that exist", 5, lerp_score(p, 100, 50, 5),
            f"{ok} of {len(g['named_folders'])} folders named in {g['file']} exist somewhere in the folder" + (f". Missing: {', '.join(g['missing_folders'][:5])}" if g["missing_folders"] else ""),
            "Update the guidance file so every folder it names is real", 10)
    else:
        add("Leverage", "claims", "The guidance file describes folders that exist", 5, 0,
            "The guidance file names no folders to check", "", 0, applicable=False)

    dims = {}
    for c in checks:
        d = dims.setdefault(c["dimension"], {"earned": 0.0, "max": 0, "na_max": 0})
        if c["applicable"]:
            d["earned"] += c["earned"]
            d["max"] += c["max"]
        else:
            d["na_max"] += c["max"]
    earned = sum(d["earned"] for d in dims.values())
    avail = sum(d["max"] for d in dims.values())
    score = round(100 * earned / avail) if avail else 0
    label = ("Filing Cabinet" if score < 40 else "Notebook" if score < 60 else "Network" if score < 80 else "Operating System")
    meaning = {"Filing Cabinet": "Notes go in. Nothing comes out.",
               "Notebook": "Real content, no connective tissue. Search works, recall does not.",
               "Network": "The graph carries weight. Gaps are maintenance, not architecture.",
               "Operating System": "It answers questions you did not think to ask."}[label]
    fixes = sorted([c for c in checks if c["applicable"] and c["max"] - c["earned"] > 0.5 and c["fix"]],
                   key=lambda c: -(c["max"] - c["earned"]))[:5]
    return {"lens": "health-score", "score": score, "label": label, "meaning": meaning,
            "dimensions": {k: {"earned": round(v["earned"], 1), "max": v["max"],
                               "pct": round(100 * v["earned"] / v["max"]) if v["max"] else None,
                               "not_scored": v["na_max"]} for k, v in dims.items()},
            "checks": checks, "fixes": fixes, "notes": len(notes),
            "scored_points": avail, "not_scored_points": 100 - avail}


# ---------------------------------------------------------------- level lens

LEVELS = [
    (1, "Ask well", "Claude knows who you are and how you work before you ask"),
    (2, "Set it up once", "Your notes are organised and a guidance file points Claude to them"),
    (3, "Repeat it", "A task you do every week is a skill or command, and you use it"),
    (4, "Connect it", "Claude reads a live system for you through a connector"),
    (5, "Runs without you", "Hooks or scheduled jobs do work when you are not typing, and the system lives in a shared repo"),
]


def level(data):
    g = data["guidance"]
    notes = data["notes"]
    cl = data["claude"] or {}
    ucl = data["user_claude"] or {}
    s = data["sessions"] or {}
    profile = [n["path"] for n in notes if PROFILE_RE.search(n["stem"])]
    top_folders = {f.split("/")[0] for f in data["folders"] if f}
    skills = cl.get("skills", 0) + cl.get("commands", 0) + ucl.get("skills", 0) + ucl.get("commands", 0)
    skill_uses = sum((s.get("skills") or {}).values())
    mcp = cl.get("mcp_servers", 0) + ucl.get("mcp_servers", 0)
    hooks = cl.get("hooks", 0) + ucl.get("hooks", 0)
    results = []
    # 1
    ok1 = bool(g) or bool(profile)
    results.append((ok1, f"Guidance file: {g['file'] if g else 'none'}. Profile notes: {len(profile)}",
                    "Add a CLAUDE.md that says who you are, what you work on and how you like answers"))
    # 2
    ok2 = bool(g) and g["refs"] >= 3 and len(top_folders) >= 3 and len(notes) >= 20
    results.append((ok2, f"{len(notes)} notes in {len(top_folders)} top-level folders. Guidance links or paths: {g['refs'] if g else 0}",
                    "Sort notes into at least three folders and make the guidance file link to each one"))
    # 3
    ok3 = skills >= 1 and skill_uses > 0
    proof3 = f"{skills} skills or commands found. {skill_uses} skill runs in the session logs" + ("" if s.get("found") else " (no session logs found, so use is unproven)")
    results.append((ok3, proof3, "Turn one task you do three times a week into a skill, then run it for a week"))
    # 4
    ok4 = s.get("mcp_calls", 0) > 0  # proof is use, connectors can also live in the Claude app
    results.append((ok4, f"{mcp} connectors (MCP servers) configured. {s.get('mcp_calls', 0)} connector calls in the session logs",
                    "Connect one live system (calendar, mail, CRM) read-only and use it in a weekly task"))
    # 5
    ok5 = hooks >= 1 and data["git"]["remote"]
    results.append((ok5, f"{hooks} hooks configured. Git remote: {'yes' if data['git']['remote'] else 'no'}",
                    "Add one hook or scheduled job that does work while you are away, and push the folder to a private repo"))
    lvl = 0
    for ok, _, _ in results:
        if ok:
            lvl += 1
        else:
            break
    rows = []
    for (n, name, means), (ok, proof, nxt) in zip(LEVELS, results):
        rows.append({"level": n, "name": name, "means": means, "passed": ok, "proof": proof, "next": nxt})
    nxt = rows[lvl]["next"] if lvl < 5 else "You are at the top. Teach someone else to get here"
    return {"lens": "level", "level": lvl, "name": LEVELS[lvl - 1][1] if lvl else "Not started",
            "rows": rows, "next_step": nxt, "counted_user_claude": data["user_claude"] is not None}


# ---------------------------------------------------------------- wrapped lens

def wrapped(data):
    days = data["days"]
    start = TODAY - dt.timedelta(days=days - 1)
    created = Counter()
    touched = Counter()
    hours = [0] * 24
    weekdays = [0] * 7
    words = 0
    new_notes = 0
    folders = Counter()
    for n in data["notes"]:
        m = dt.datetime.fromisoformat(n["mtime"])
        if m.date() >= start:
            touched[m.date()] += 1
            hours[m.hour] += 1
            folders[n["folder"].split("/")[0] or "(top level)"] += 1
        c = None
        if n["created"]:
            try:
                c = dt.date.fromisoformat(n["created"])
            except ValueError:
                c = None
        if c and c >= start:
            created[c] += 1
            weekdays[c.weekday()] += 1
            new_notes += 1
            words += n["words"]
    active = set(created) | set(touched)
    streak = best = 0
    d = start
    while d <= TODAY:
        streak = streak + 1 if d in active else 0
        best = max(best, streak)
        d += dt.timedelta(days=1)
    busiest = max(active, key=lambda x: created.get(x, 0) + touched.get(x, 0)) if active else None
    s = data["sessions"] or {}
    if s.get("found") and s.get("prompts"):
        hours_src, wd_src = s["by_hour"], s["by_weekday"]
    else:
        hours_src, wd_src = hours, weekdays
    peak_hour = max(range(24), key=lambda h: hours_src[h]) if any(hours_src) else None
    peak_day = max(range(7), key=lambda i: wd_src[i]) if any(wd_src) else None
    wknd = (wd_src[5] + wd_src[6]) / max(1, sum(wd_src))
    if peak_hour is None:
        persona = "Just getting started"
    elif wknd > 0.4:
        persona = "Weekend Builder"
    elif peak_hour < 9:
        persona = "Early Riser"
    elif peak_hour < 12:
        persona = "Morning Maker"
    elif peak_hour < 17:
        persona = "Afternoon Operator"
    elif peak_hour < 21:
        persona = "Evening Thinker"
    else:
        persona = "Night Owl"
    dayname = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {"lens": "wrapped", "days": days, "from": start.isoformat(), "to": TODAY.isoformat(),
            "active_days": len(active), "best_streak": best, "new_notes": new_notes, "words_in_new_notes": words,
            "notes_touched": sum(touched.values()),
            "busiest_day": busiest.isoformat() if busiest else None,
            "peak_hour": peak_hour, "peak_weekday": dayname[peak_day] if peak_day is not None else None,
            "persona": persona, "by_hour": hours_src, "by_weekday": wd_src,
            "top_folders": folders.most_common(3),
            "claude": {k: s.get(k) for k in ("found", "sessions", "prompts", "days_active", "skills", "tool_calls", "mcp_calls")} if s else None,
            "rhythm_source": "Claude Code session logs" if s.get("found") and s.get("prompts") else "note edit and creation times"}


# ---------------------------------------------------------------- output

def bar(v, mx, width=20):
    n = 0 if not mx else round(width * v / mx)
    return "#" * n + "." * (width - n)


def text_health(r):
    out = [f"HEALTH SCORE  {r['score']}/100  {r['label']}", f"  {r['meaning']}", ""]
    for k, d in r["dimensions"].items():
        p = d["pct"] if d["pct"] is not None else 0
        extra = f"  ({d['not_scored']} pts not scored, no data)" if d["not_scored"] else ""
        out.append(f"  {k:<11} {bar(p, 100)} {d['earned']:>5}/{d['max']:<3}{extra}")
    out += ["", "TOP FIXES"]
    for i, f in enumerate(r["fixes"], 1):
        out.append(f"  {i}. {f['fix']}  (+{round(f['max'] - f['earned'], 1)} pts, about {f['minutes']} min)")
        out.append(f"     evidence: {f['evidence']}")
    if not r["fixes"]:
        out.append("  None. Every scored check is at or near full points.")
    out += ["", "EVERY CHECK"]
    for c in r["checks"]:
        pts = f"{c['earned']}/{c['max']}" if c["applicable"] else f"n/a/{c['max']}"
        out.append(f"  [{c['dimension'][:4]}] {pts:>8}  {c['title']}")
        out.append(f"              {c['evidence']}")
    out.append(f"\nScored on {r['scored_points']} of 100 points. Checks with no data are left out and the score is scaled, never zeroed.")
    return "\n".join(out)


def text_level(r):
    out = [f"LEVEL {r['level']} of 5  {r['name']}", ""]
    for row in r["rows"]:
        mark = "PASS" if row["passed"] else "    "
        out.append(f"  {mark} {row['level']}. {row['name']}  {row['means']}")
        out.append(f"         proof: {row['proof']}")
    out += ["", f"NEXT STEP  {r['next_step']}"]
    if not r["counted_user_claude"]:
        out.append("  Only this folder's .claude settings were counted. Add --include-user to count ~/.claude too.")
    return "\n".join(out)


def text_wrapped(r):
    out = [f"WRAPPED  {r['from']} to {r['to']} ({r['days']} days)", "",
           f"  You are a {r['persona']}.",
           f"  Active days       {r['active_days']}",
           f"  Best streak       {r['best_streak']} days",
           f"  New notes         {r['new_notes']} ({r['words_in_new_notes']} words)",
           f"  Notes touched     {r['notes_touched']}",
           f"  Busiest day       {r['busiest_day']}",
           f"  Peak hour         {r['peak_hour']}:00" if r["peak_hour"] is not None else "  Peak hour         none yet",
           f"  Favourite day     {r['peak_weekday']}", ""]
    mx = max(r["by_hour"]) or 1
    out.append(f"  RHYTHM BY HOUR (from {r['rhythm_source']})")
    for h in range(6, 24, 1):
        if r["by_hour"][h]:
            out.append(f"    {h:02d}:00 {bar(r['by_hour'][h], mx, 30)} {r['by_hour'][h]}")
    c = r["claude"]
    out.append("")
    if c and c.get("found") and c.get("prompts"):
        out += ["  CLAUDE CODE IN THIS FOLDER",
                f"    Sessions {c['sessions']}, prompts {c['prompts']}, days with Claude {c['days_active']}, tool calls {c['tool_calls']}"]
        if c["skills"]:
            out.append("    Top skills " + ", ".join(f"{k} ({v})" for k, v in c["skills"].items()))
    else:
        out.append("  No Claude Code session logs for this folder in the window, so the rhythm comes from note times.")
    out += ["", "  Top folders (local only, leave these out if you share): " + ", ".join(f"{k} ({v})" for k, v in r["top_folders"])]
    return "\n".join(out)


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a66;--card:#fff;--line:#e6e3dc;--acc:#2f6f5e;--warn:#b5562b}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mut:#a3a29c;--card:#1d1d1b;--line:#33322f;--acc:#6fbfa6;--warn:#e08a5f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 12px;border-top:1px solid var(--line);padding-top:24px}
.mut{color:var(--mut)}.big{font-size:56px;font-weight:700;line-height:1}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
.row{display:flex;gap:12px;align-items:center;margin:6px 0}.lab{width:110px;flex:none}.track{flex:1;height:10px;background:var(--line);border-radius:5px;overflow:hidden}
.fill{height:100%;background:var(--acc)}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line);vertical-align:top}
.pass{color:var(--acc);font-weight:600}.fail{color:var(--mut)}.ev{color:var(--mut);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat b{display:block;font-size:28px}.hours{display:flex;align-items:flex-end;gap:2px;height:80px}.hours div{flex:1;background:var(--acc);border-radius:2px 2px 0 0;min-height:1px}
footer{margin-top:48px;font-size:13px;color:var(--mut)}footer a{color:var(--acc)}
"""


def e(s):
    return html.escape(str(s))


def html_health(r):
    h = [f"<h2>Health score</h2><div class='card'><div class='big'>{r['score']}<span class='mut' style='font-size:20px'> / 100</span></div>",
         f"<p><b>{e(r['label'])}</b>. {e(r['meaning'])}</p>"]
    for k, d in r["dimensions"].items():
        p = d["pct"] or 0
        h.append(f"<div class='row'><span class='lab'>{e(k)}</span><span class='track'><span class='fill' style='display:block;width:{p}%'></span></span><span>{d['earned']}/{d['max']}</span></div>")
    h.append(f"<p class='ev'>Scored on {r['scored_points']} of 100 points. Checks with no data are left out and the score is scaled.</p></div>")
    h.append("<h3>Top fixes</h3><ol>")
    for f in r["fixes"]:
        h.append(f"<li><b>{e(f['fix'])}</b> <span class='mut'>+{round(f['max'] - f['earned'], 1)} pts, about {f['minutes']} min</span><div class='ev'>{e(f['evidence'])}</div></li>")
    h.append("</ol><h3>Every check</h3><table><tr><th>Dimension</th><th>Check</th><th>Points</th></tr>")
    for c in r["checks"]:
        pts = f"{c['earned']} / {c['max']}" if c["applicable"] else f"not scored / {c['max']}"
        h.append(f"<tr><td>{e(c['dimension'])}</td><td>{e(c['title'])}<div class='ev'>{e(c['evidence'])}</div></td><td>{pts}</td></tr>")
    h.append("</table>")
    return "".join(h)


def html_level(r):
    h = [f"<h2>Level</h2><div class='card'><div class='big'>{r['level']}<span class='mut' style='font-size:20px'> of 5</span></div><p><b>{e(r['name'])}</b></p>",
         f"<p>Next step. {e(r['next_step'])}</p></div><table><tr><th></th><th>Level</th><th>Proof from your files</th></tr>"]
    for row in r["rows"]:
        cls, mark = ("pass", "Pass") if row["passed"] else ("fail", "Not yet")
        h.append(f"<tr><td class='{cls}'>{mark}</td><td><b>{row['level']}. {e(row['name'])}</b><div class='ev'>{e(row['means'])}</div></td><td class='ev'>{e(row['proof'])}</td></tr>")
    h.append("</table>")
    return "".join(h)


def html_wrapped(r):
    mx = max(r["by_hour"]) or 1
    bars = "".join(f"<div title='{h}:00, {v}' style='height:{max(1, round(80 * v / mx))}px'></div>" for h, v in enumerate(r["by_hour"]))
    stats = [("Active days", r["active_days"]), ("Best streak", f"{r['best_streak']} days"), ("New notes", r["new_notes"]),
             ("Words written", r["words_in_new_notes"]), ("Peak hour", f"{r['peak_hour']}:00" if r["peak_hour"] is not None else "none"),
             ("Favourite day", r["peak_weekday"] or "none")]
    h = [f"<h2>Wrapped</h2><div class='card'><p class='mut'>{r['from']} to {r['to']}</p><div class='big' style='font-size:36px'>You are a {e(r['persona'])}.</div>",
         "<div class='grid' style='margin-top:16px'>" + "".join(f"<div class='stat'><b>{e(v)}</b><span class='mut'>{e(k)}</span></div>" for k, v in stats) + "</div>",
         f"<p class='mut' style='margin-top:16px'>Rhythm by hour, from {e(r['rhythm_source'])}</p><div class='hours'>{bars}</div>",
         "<p class='ev'>Everything above this line is counts only and safe to share.</p></div>"]
    c = r["claude"]
    if c and c.get("found") and c.get("prompts"):
        h.append(f"<p>Claude Code in this folder. {c['sessions']} sessions, {c['prompts']} prompts, {c['days_active']} days, {c['tool_calls']} tool calls.</p>")
        if c["skills"]:
            h.append("<p>Top skills. " + e(", ".join(f"{k} ({v})" for k, v in c["skills"].items())) + "</p>")
    h.append("<p class='ev'>Top folders, local only. " + e(", ".join(f"{k} ({v})" for k, v in r["top_folders"])) + "</p>")
    return "".join(h)


def page(title, folder, sections):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{e(title)}</title><style>{CSS}</style></head><body><main><h1>{e(title)}</h1>"
            f"<p class='mut'>{e(folder)} · {NOW.strftime('%Y-%m-%d %H:%M')} · read on this machine, nothing uploaded</p>"
            + "".join(sections) +
            "<footer>Want the system these lenses measure? <a href='https://github.com/remixrevco/remix-yourself-starter'>Remix Yourself Starter</a> is free.<br>"
            "Free and open source under the MIT License. Questions? Email andy@remixsystems.co · <a href='https://remixsystems.co'>remixsystems.co</a></footer></main></body></html>")


def out_dir(args, data):
    d = os.path.expanduser(args.out) if args.out else os.path.join(os.path.expanduser("~/.cache/command-center"), slug(data["folder_name"]))
    root = data["root"]
    if os.path.abspath(d).startswith(root + os.sep) or os.path.abspath(d) == root:
        raise SystemExit("command-center: refusing to write reports inside the notes folder. Pick another --out")
    os.makedirs(d, exist_ok=True)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cc.py", description="Command Center lenses on a personal AI operating system")
    ap.add_argument("lens", choices=["scan", "health", "health-score", "level", "wrapped", "all"])
    ap.add_argument("folder")
    ap.add_argument("--out")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--sessions")
    ap.add_argument("--no-sessions", action="store_true")
    ap.add_argument("--include-user", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    lens = "health" if args.lens == "health-score" else args.lens
    data = scan(args.folder, args.days, args.sessions, args.no_sessions, args.include_user)
    od = out_dir(args, data)
    with open(os.path.join(od, "scan.json"), "w") as fh:
        json.dump(data, fh, indent=1)
    if lens == "scan":
        print(f"scan.json written to {os.path.join(od, 'scan.json')} ({len(data['notes'])} notes)")
        return 0
    runs = {"health": (health, text_health, html_health, "Health score"),
            "level": (level, text_level, html_level, "Level"),
            "wrapped": (wrapped, text_wrapped, html_wrapped, "Wrapped")}
    picked = list(runs) if lens == "all" else [lens]
    results, sections, texts = {}, [], []
    for k in picked:
        fn, tx, hx, _ = runs[k]
        r = fn(data)
        results[k] = r
        texts.append(tx(r))
        sections.append(hx(r))
    name = "command-center" if lens == "all" else lens
    title = "Command Center" if lens == "all" else f"Command Center, {runs[lens][3].lower()}"
    html_path = os.path.join(od, f"{name}.html")
    with open(html_path, "w") as fh:
        fh.write(page(title, data["folder_name"], sections))
    with open(os.path.join(od, f"{name}.json"), "w") as fh:
        json.dump(results, fh, indent=1)
    if args.json:
        print(json.dumps(results, indent=1))
    else:
        print(f"COMMAND CENTER  {data['folder_name']}  ({len(data['notes'])} notes)\n")
        print("\n\n".join(texts))
        print(f"\nReport page: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
