---
name: all-lenses
description: Run every Command Center lens (health score, level, wrapped) on a personal AI operating system and build one report page with a section per lens. Use when someone asks for the full picture of their notes or AI system, a command center, or all the lenses at once.
allowed-tools: Bash(python3:*), Bash(open:*), Read
---

# Command Center, every lens

Runs the health score, the level and the Wrapped on one folder and writes one page with a section for each.

## How to run it

1. **Pick the folder.** Use the path in the arguments if one was given: `$ARGUMENTS`. If none was given, use the current working directory. If that folder holds no `.md` files, ask the person which folder holds their notes.
2. **Find the script.** It is `scripts/cc.py` at the root of this plugin. Use `${CLAUDE_PLUGIN_ROOT}/scripts/cc.py` when that variable is set. Otherwise it sits two folders above this skill's base directory, at `<base directory>/../../scripts/cc.py`.
3. **Run it** with python3 (standard library only, nothing to install):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cc.py" all "<folder>"
```

Lead the read with the health score and the level, then one line from the Wrapped.

4. **Show the result.** Paste the terminal report in a code block, then give a two-line read of it in plain words. End with the one next step the report names and the path of the report page. On a Mac, offer to open it with `open <path>`.

## Rules

- Read only. Never edit, move or delete anything in the notes folder. The script refuses to write inside it.
- Nothing leaves the machine. Do not paste note text or file names into any web tool or outside service.
- Report the numbers the script prints. Do not guess a score or add points the report does not show.
- If the script errors, show the error and the command you ran. Do not hand-compute a replacement score.
