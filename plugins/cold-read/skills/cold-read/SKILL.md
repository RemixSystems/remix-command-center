---
name: cold-read
description: Test a written document the way its reader will meet it, cold, before handing it over. Spawns a fresh agent with no session context, gives it only the file and the original ask, and grades it on eight points (people and terms defined, answers up top, decisions with options and a pick, likely questions answered, trust stated, plain tone, consistent numbers). Fixes and re-runs until it passes. Use on "cold read this", "would this make sense to someone without context", "check this before I send it". Not for code.
allowed-tools: Read, Edit, Agent
---

# Cold read

The person who reads a document has not read what you read. A plan, a brief or an email that makes sense to the session that wrote it can be unreadable to them. The fix is to hand the file to a fresh agent that has no context and ask whether it can understand, defend and decide from it.

## Why a fresh agent, not self-review

The writing session cannot see its own assumed context. It knows who "Josh" is and what "phase 3" means, so it never notices they are undefined. A fresh agent with only the file sees what the reader sees. The no-context part is what matters.

## Steps

1. **Pick the documents.** The file or files in the arguments: `$ARGUMENTS`. With none, ask which document to test. Skip code, logs and data files.
2. **Get the ask, word for word.** The request the document answers, copied exactly from the conversation. If there is none in the conversation, ask the person for it in one line, and who the reader is (default, the person who asked).
3. **Spawn one reader per document, in parallel, in one message.** Use the Agent tool. A smaller, faster model is fine for the reader. The prompt is the template below with only the path, the reader and the ask filled in. Never add session context, summaries or sources.
4. **Fix every FAIL.** Edit the document. Do not argue with the reader. If a finding is wrong only because the reader lacked context, the document is missing that context, so add it.
5. **Re-run with a new reader**, never the same one. Stop when every point passes. Run up to three rounds without asking.
6. **Ask before round four.** If round three still fails, ask one question, "Round 3 still fails on <the open findings>. Run another round, run three readers at once, or stop here?" Do not stop silently.
7. **Stamp it.** Add a last line, `cold-read: pass YYYY-MM-DD, round N`. If the person chose to stop with findings open, stamp `cold-read: stopped YYYY-MM-DD after N rounds, open: <what>`.
8. **Report.** Which documents passed, in how many rounds, and anything still open.

## Reader prompt template

```
You are a cold reader with NO other context. Read ONLY this file with the Read tool. Do not open any other file, search, or follow links.

FILE: <absolute path>

It was written for <the reader, one line on who they are> in answer to this request, quoted exactly:
"<the ask, verbatim>"

Judge it as that reader would, reading it cold, knowing they will be questioned by the people around them. Quote the exact lines that fail. For each point give PASS or FAIL and the fix.

1. People. Every person is introduced with their role the first time they appear.
2. Terms. Every acronym, product name, internal code, file name and piece of jargon is explained or removed. List the worst offenders.
3. Answers first. Each part of the request gets a plain answer near the top. A yes or no question gets a one-line verdict before the reasoning, not a hedge.
4. Decisions. Each decision states the background, the options, what happens under each, a deadline, and a recommendation with its reason. Tasks are not dressed up as decisions. You could make each decision from this text alone.
5. Questions. The document anticipates what the people it names will ask, and answers them.
6. Trust. It says near the top what was checked, how, and what was not.
7. Tone. No slogans, dramatic headings, hype, claims about people's motives without evidence, or notes about the writing process.
8. Consistency. Numbers, dates, counts and names agree everywhere in the document.

End with VERDICT, PASS or FIX, and the top three fixes in priority order.
```

## What not to do

- Do not grade it yourself and call that a cold read.
- Do not give the reader summaries or sources "to help". That defeats the test.
- Do not shorten the document to pass. Clarity is the bar, not length. A long document with a clear top section passes.
