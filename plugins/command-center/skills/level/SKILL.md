---
name: level
description: Place a personal AI operating system on a ladder from Level 1 (Ask well) to Level 5 (Runs without you), with one proof from the person's own files per level and the next step. Use when someone asks what level they are at with Claude or AI, how advanced their setup is, or what to do next.
allowed-tools: Bash(python3:*), Bash(open:*), Read
---

# Level

Answers one question, where am I on the ladder. Five levels, each passed only with proof from files: a guidance file, organised notes, a skill that gets used, a connector that gets used, and hooks plus a shared repo. The level is the highest one with every level below it passed.

## How to run it

1. **Pick the folder.** Use the path in the arguments if one was given: `$ARGUMENTS`. If none was given, use the current working directory. If that folder holds no `.md` files, ask the person which folder holds their notes.
2. **Find the script.** It is `scripts/cc.py` at the root of this plugin. Use `${CLAUDE_PLUGIN_ROOT}/scripts/cc.py` when that variable is set. Otherwise it sits two folders above this skill's base directory, at `<base directory>/../../scripts/cc.py`.
3. **Run it** with python3 (standard library only, nothing to install):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cc.py" level "<folder>"
```

Add `--include-user` to count skills, connectors and hooks in `~/.claude` as well as the folder's own `.claude`. Ask before adding it, because it reads the person's whole Claude Code setup.

4. **Show the result.** Paste the terminal report in a code block, then give a two-line read of it in plain words. End with the one next step the report names and the path of the report page. On a Mac, offer to open it with `open <path>`.

## Rules

- Read only. Never edit, move or delete anything in the notes folder. The script refuses to write inside it.
- Nothing leaves the machine. Do not paste note text or file names into any web tool or outside service.
- Report the numbers the script prints. Do not guess a score or add points the report does not show.
- If the script errors, show the error and the command you ran. Do not hand-compute a replacement score.
