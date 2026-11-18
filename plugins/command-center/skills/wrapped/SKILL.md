---
name: wrapped
description: A Wrapped-style look back at how someone used their notes and Claude Code over a season: active days, best streak, new notes, words written, peak hour, favourite day, a persona, and top skills. Count only, safe to share. Use for AI Wrapped, year in review, look back, or habit questions.
allowed-tools: Bash(python3:*), Bash(open:*), Read
---

# Wrapped

Answers one question, what did my habit look like over a season. Default window is 90 days, change it with `--days 365` for a year. It reads note dates and, if they exist, the Claude Code session logs for this folder, and keeps counts only. No prompt text is ever stored.

## How to run it

1. **Pick the folder.** Use the path in the arguments if one was given: `$ARGUMENTS`. If none was given, use the current working directory. If that folder holds no `.md` files, ask the person which folder holds their notes.
2. **Find the script.** It is `scripts/cc.py` at the root of this plugin. Use `${CLAUDE_PLUGIN_ROOT}/scripts/cc.py` when that variable is set. Otherwise it sits two folders above this skill's base directory, at `<base directory>/../../scripts/cc.py`.
3. **Run it** with python3 (standard library only, nothing to install):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cc.py" wrapped "<folder>"
```

The top card is counts only and safe to share. The top folders line is marked local only, remind the person to leave it out if they post a screenshot.

4. **Show the result.** Paste the report exactly as the script printed it, in a code block, down to the end of its first list (for the health score, through TOP FIXES). Do not reword, merge or round the lines. Then give a two-line read of it in plain words. End with the one next step the report names and the path of the report page. On a Mac, offer to open it with `open <path>`.

## Rules

- Read only. Never edit, move or delete anything in the notes folder. The script refuses to write inside it.
- Nothing leaves the machine. Do not paste note text or file names into any web tool or outside service.
- Report the numbers the script prints. Do not guess a score or add points the report does not show.
- If the script errors, show the error and the command you ran. Do not hand-compute a replacement score.
