# Command Center

**The problem this solves.** You built a personal AI operating system out of notes, a CLAUDE.md and a few skills, and you cannot tell if it is working. Command Center reads your notes folder on your own machine and tells you how healthy it is, what level you are at, and what your habit looked like this season.

License: MIT · Free · Nothing leaves your machine

## Start here, one paste

Open Claude Code in the folder that holds your notes, then paste this.

```text
Install the Command Center plugin from the remix-systems marketplace at
https://github.com/remixrevco/remix-command-center (if that link does not work,
I will give you a local path instead). Walk me through any Terminal step in plain
words. When it is installed, run /command-center:health-score on this folder,
show me the report, and tell me the one thing to fix first.
```

## Install it yourself

Two lines inside Claude Code.

```text
/plugin marketplace add remixrevco/remix-command-center
/plugin install command-center@remix-systems
```

From a local copy instead (after `git clone`), point the first line at the folder.

```text
/plugin marketplace add /path/to/remix-command-center
/plugin install command-center@remix-systems
```

Restart Claude Code if the new commands do not show up. Type `/command-center` and the four lenses appear.

From a terminal, the same two steps are `claude plugin marketplace add <repo or path>` and `claude plugin install command-center@remix-systems`.

## The lenses

| Command | The question it answers | What you get |
|---|---|---|
| `/command-center:health-score` | Is it healthy | A score out of 100, a label (Filing Cabinet, Notebook, Network, Operating System), four bars and the five fixes worth the most points, each with evidence |
| `/command-center:level` | Where am I on the ladder | Level 1 (Ask well) to 5 (Runs without you), one proof from your files per level, and your next step |
| `/command-center:wrapped` | What did my habit look like | Active days, best streak, new notes, words, peak hour, favourite day and a persona, over 90 days by default |
| `/command-center:all-lenses` | All of the above | One page with a section per lens |

Each command takes an optional folder path. With none, it reads the folder Claude Code is open in.

## Try it on the sample

The repo ships a small sample notes folder for a made-up design studio.

```text
/command-center:health-score examples/sample-notes
```

Or with no Claude at all, straight from a terminal.

```bash
python3 plugins/command-center/scripts/cc.py all examples/sample-notes
```

## What it reads, what it writes

| It reads | It writes |
|---|---|
| Every `.md` file in the folder, for links, tags, dates and word counts | `~/.cache/command-center/<folder name>/`, a `scan.json`, a JSON result and an HTML page per run |
| `CLAUDE.md`, `AGENTS.md` or `GEMINI.md` at the top of the folder | Nothing inside your notes folder. The script refuses to |
| The folder's `.claude/` settings, skills and commands | |
| Claude Code's session logs for this folder, as counts only. Prompt text is never stored | |

Change the output folder with `--out`. Skip session logs with `--no-sessions`. The level lens counts only the folder's own `.claude/` unless you add `--include-user`.

Needs python3 (any Mac has it) and Claude Code. No accounts, no API keys, no network calls.

## How the health score works

Four dimensions, 100 points. Every check prints its evidence line, a count and the files behind it, so you can fix it without us.

| Dimension | Points | Asks |
|---|---|---|
| Structure | 25 | Is it built right. Note openers and tags, naming, loose notes, index notes, templates |
| Connection | 30 | Is it a graph or a folder tree. Broken links, orphans, hubs, links from new notes, links up, dead ends |
| Currency | 25 | Is it still true. Index drift, stale indexes, inbox backlog, notes marked done that hold nothing, freshness |
| Leverage | 20 | Is AI operating it. A guidance file that points to things, AI sessions in the last 30 days, no keys in notes, a guidance file that matches the folders |

A check with no data, such as no inbox folder, is left out and the score is scaled. It never costs you points for not using our layout. No check needs a file anyone sells.

## Check the plugin

```bash
python3 tests/run_checks.py          # every detector must catch a known-bad seed
claude plugin validate .             # manifest and skill checks
```

## Built by

Remix Systems builds personal AI operating systems. Want the system these lenses measure? [Remix Yourself Starter](https://github.com/remixrevco/remix-yourself-starter) is free.

Free and open source under the MIT License. Questions? Email andy@remixsystems.co · [remixsystems.co](https://remixsystems.co)
