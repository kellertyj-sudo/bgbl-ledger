# BGBL — Reference

Operational reference for the ledger. Kept separate from the data files so a fresh chat can
pick up the work without carrying a conversation with it.

| File | What it is |
|---|---|
| `transaction-logging-runbook.md` | The procedure: get the moves, dry run, apply, push. Read this first. |
| `league-constants.json` | Team codes, owners, ESPN team ids, escalator ladder, roster limit, the league-year calendar, ESPN API endpoints. |

## Starting a transaction-logging chat

Point Claude at this folder — or at
`https://github.com/kellertyj-sudo/bgbl-ledger/tree/main/reference`, since the repo is public
and readable without any device access — and say what you want logged. The runbook covers the
rest.

The Project docs in Claude carry the deeper background across chats on their own: the escalator
rules engine spec, the ESPN feed ingest notes, the Trello archive profile, and the known data
quality issues. This folder is the operational subset — what you need to *do the task*, not the
history of how it was worked out.

## What is deliberately not here

- **Salaries and rosters.** Those live in `ledger.json`, one directory up. One copy, no drift.
- **The Trello archive.** Narrative only. It is never used to compute a salary and never
  replayed against the ledger.
- **Anything Claude should infer.** Dates move every year; the runbook says to ask rather than
  assume, and `league-constants.json` records only what was actually observed.
