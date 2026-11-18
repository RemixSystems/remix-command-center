---
name: health-score
description: Score a personal AI operating system (a folder of Markdown notes, an Obsidian vault, a second brain) out of 100 across structure, connection, currency and leverage, with a maturity label and the five fixes worth the most points, each with its evidence. Use when someone asks how healthy their notes or AI system is, for a health check, an audit, or a score.
allowed-tools: Bash(python3:*), Bash(open:*), Read
---

# Health score

Answers one question, is this system healthy. It reads the notes folder and gives one number out of 100, a label (Filing Cabinet, Notebook, Network, Operating System), four dimension bars, and the five fixes worth the most points. Every check prints its evidence, so nothing is an assertion.

## How to run it

1. **Pick the folder.** Use the path in the arguments if one was given: `$ARGUMENTS`. If none was given, use the current working directory. If that folder holds no `.md` files, ask the person which folder holds their notes.
2. **Find the script.** It is `scripts/cc.py` at the root of this plugin. Use `${CLAUDE_PLUGIN_ROOT}/scripts/cc.py` when that variable is set. Otherwise it sits two folders above this skill's base directory, at `<base directory>/../../scripts/cc.py`.
3. **Run it** with python3 (standard library only, nothing to install):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cc.py" health "<folder>"
```

Checks with no data (no inbox, no index notes, no session logs) are left out and the score is scaled, never zeroed. Say so if the report shows points not scored.

4. **Show the result.** Paste the terminal report in a code block, then give a two-line read of it in plain words. End with the one next step the report names and the path of the report page. On a Mac, offer to open it with `open <path>`.

## Rules

- Read only. Never edit, move or delete anything in the notes folder. The script refuses to write inside it.
- Nothing leaves the machine. Do not paste note text or file names into any web tool or outside service.
- Report the numbers the script prints. Do not guess a score or add points the report does not show.
- If the script errors, show the error and the command you ran. Do not hand-compute a replacement score.
