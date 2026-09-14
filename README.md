# BGBL Ledger

Keeper salary ledger for the BGBL fantasy baseball league.
Live at https://kellertyj-sudo.github.io/bgbl-ledger/

Everything lives at the repo root — no subfolders. GitHub's web uploader flattens
directories, so the layout is flat by design rather than by accident.

| File | What it is |
|---|---|
| `index.html` | The whole site, self-contained |
| `bgbl-roster-<TEAM>.csv` | One per team, in roster order |
| `bgbl-rosters-league-wide.csv` | All 344 players |
| `bgbl-transactions.csv` | Transaction log, flat export |
| `registry.json` | Every player ever in the league (1,088). `pid` is the permanent key |
| `transactions.json` | Append-only log, keyed by `pid`. The primary artifact |
| `ledger.json` | Current rosters and salaries — a derived view |
| `ingest.py` | Parse, validate and apply an ESPN transaction paste |

## Player identity

`pid` never changes and is never reused. A name change edits `name` and pushes the old
form into `aliases`; it never mints a second player. Two different people can share a
name — `p1039` Will Smith (C) and `p1088` Will Smith (RP, retired) — which is why the
key is a pid and not a name.

## Ingest

    python3 ingest.py paste.txt              # dry run, report only
    python3 ingest.py paste.txt --apply      # write, only if clean

Nothing is written unless the whole batch validates. Pastes come from ESPN's player pool,
so misspellings are not the risk — **name changes are** (Mike Stanton to Giancarlo Stanton).
A rename surfaces as a drop of a player who is not on any roster, so the validator checks the
dropping team for a near-identical name and a shared surname before reporting him missing.
When it asks, add the new spelling to that player's `aliases` and re-run. Never mint a second pid.
