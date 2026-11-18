#!/usr/bin/env python3
"""The plugin's own checks.

1. Builds a known-bad notes folder in a temp dir and confirms every health detector
   loses points on it. A detector's clean result only counts after it has caught a
   known-bad seed once.
2. Runs every lens on the sample vault and confirms it beats the bad seed.
3. Confirms no lens writes inside the folder it reads.
4. Confirms session logs are read as counts (a fixture log, no real logs).

Run:  python3 tests/run_checks.py
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CC = os.path.join(REPO, "plugins", "command-center", "scripts", "cc.py")
SAMPLE = os.path.join(REPO, "examples", "sample-notes")
FAILS = []


def check(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def run(args):
    p = subprocess.run([sys.executable, CC] + args + ["--json"], capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr)
        raise SystemExit("cc.py exited non-zero for " + " ".join(args))
    return json.loads(p.stdout)


def write(root, rel, text, age_days=0):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(text)
    if age_days:
        t = (dt.datetime.now() - dt.timedelta(days=age_days)).timestamp()
        os.utime(p, (t, t))


def listing(root):
    out = []
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out.append((os.path.relpath(p, root), os.path.getsize(p)))
    return sorted(out)


def build_bad(root):
    fake_key = "sk-" + "ant-" + "x" * 32  # built at run time, never stored as a literal
    # Guidance file: long, routes nowhere, names a folder that does not exist
    write(root, "CLAUDE.md", "Notes.\n\nKeep things in `Archive/` and `Projects/`.\n" + "Rule line.\n" * 450, age_days=70)
    # Loose top-level notes, mixed naming, no openers, no tags, dead ends
    for i in range(12):
        name = [f"note-number-{i}", f"Note Title {i}", f"x_{i}", f"N~{i}"][i % 4]
        write(root, f"{name}.md", "- bullet only\n", age_days=90)
    # A folder with an index that lists none of its notes, old index, newer siblings
    write(root, "Projects/Projects.md", "# Projects\n\n- [[missing one]]\n- [[missing two]]\n- [[missing three]]\n", age_days=80)
    for i in range(6):
        write(root, f"Projects/p{i}.md", "- todo\n", age_days=20)
    # Inbox backlog
    for i in range(35):
        write(root, f"Inbox/capture {i}.md", "thing\n", age_days=40)
    # Notes marked processed with nothing in them
    for i in range(4):
        write(root, f"Meetings/m{i}.md", "status:: processed\n", age_days=70)
    # Untagged templates
    write(root, "templates/blank.md", "# {{title}}\n", age_days=70)
    # A key in a note and an env file
    write(root, "Projects/keys.md", f"api key {fake_key}\n", age_days=70)
    write(root, ".env", "TOKEN=abc\n")
    # Make every note old except the few set above, so freshness fails
    return root


def build_sessions(d, recent):
    os.makedirs(d, exist_ok=True)
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1 if recent else 60)
    ts = when.isoformat().replace("+00:00", "Z")
    lines = [
        {"type": "user", "timestamp": ts, "message": {"role": "user", "content": "this text must never be kept"}},
        {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "weekly-review"}},
            {"type": "tool_use", "name": "mcp__calendar__list", "input": {}}]}},
    ]
    p = os.path.join(d, "fixture.jsonl")
    with open(p, "w") as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + "\n")
    t = when.timestamp()
    os.utime(p, (t, t))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out")
        bad = build_bad(os.path.join(tmp, "bad-vault"))
        old_sessions = os.path.join(tmp, "sessions-old")
        build_sessions(old_sessions, recent=False)
        os.makedirs(os.path.join(bad, ".claude"), exist_ok=True)

        print("Known-bad seed, every detector must lose points")
        before = listing(bad)
        r = run(["health", bad, "--out", out, "--sessions", old_sessions])["health"]
        for c in r["checks"]:
            if c["key"] in ("hubs",):
                continue  # checked below with its own threshold
            check(c["applicable"] and c["earned"] < c["max"], f"{c['key']:<14} flagged ({c['earned']}/{c['max']})")
        check(r["score"] < 40, f"bad seed scores Filing Cabinet ({r['score']})")
        hub = next(c for c in r["checks"] if c["key"] == "hubs")
        check(hub["earned"] < hub["max"], f"hubs           flagged ({hub['earned']}/{hub['max']})")
        check(listing(bad) == before, "nothing written inside the bad seed")

        print("\nSample vault")
        before = listing(SAMPLE)
        s = run(["all", SAMPLE, "--out", out, "--no-sessions"])
        check(s["health"]["score"] > r["score"] + 30, f"sample ({s['health']['score']}) beats bad seed ({r['score']}) by 30+")
        check(s["level"]["level"] >= 2, f"sample reaches level 2 or more ({s['level']['level']})")
        check(s["wrapped"]["new_notes"] > 0, f"wrapped counts new notes ({s['wrapped']['new_notes']})")
        check(listing(SAMPLE) == before, "nothing written inside the sample vault")
        check(os.path.isfile(os.path.join(out, "command-center.html")), "report page written outside the folder")

        print("\nSession logs read as counts")
        new_sessions = os.path.join(tmp, "sessions-new")
        build_sessions(new_sessions, recent=True)
        w = run(["all", SAMPLE, "--out", out, "--sessions", new_sessions])
        c = w["wrapped"]["claude"]
        check(c["prompts"] == 1 and c["skills"].get("weekly-review") == 1, "prompt and skill counted")
        check(w["level"]["rows"][2]["passed"], "level 3 passes once a skill run is in the logs")
        scan_text = open(os.path.join(out, "scan.json")).read()
        check("must never be kept" not in scan_text, "prompt text is not stored in scan.json")

        print("\nRefuses to write inside the notes folder")
        p = subprocess.run([sys.executable, CC, "health", SAMPLE, "--out", os.path.join(SAMPLE, "x")], capture_output=True, text=True)
        check(p.returncode != 0 and not os.path.exists(os.path.join(SAMPLE, "x")), "--out inside the folder is refused")

    print(f"\n{'ALL CHECKS PASSED' if not FAILS else str(len(FAILS)) + ' CHECK(S) FAILED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
