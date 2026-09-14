# BGBL Ledger

Live at https://kellertyj-sudo.github.io/bgbl-ledger/

Everything sits at the repo root — no folders. GitHub's web uploader flattens directories,
so the layout is flat by design.

| File | What it is |
|---|---|
| `index.html` | The site. Reads its data from `ledger.json` at load time. |
| `ledger.json` | **Current rosters, salaries and team names. Edit this to change the site.** |
| `registry.json` | Every player ever in the league. `pid` is the permanent key. |
| `transactions.json` | Append-only log, keyed by `pid`. |
| `ingest.py` | Parse, validate and apply an ESPN transaction paste. |

## Making a small change

Open `ledger.json` on GitHub, click the pencil, edit, commit. The site picks it up on the
next load — nothing to rebuild, nothing to regenerate. CSV downloads are generated in the
browser from the same file, so they can never drift out of step with what's on screen.

Team names live in the `teams` array; player rows live in `players`.

## Player identity

`pid` never changes and is never reused. A name change edits `name` and pushes the old form
into `aliases`; it never mints a second player. Two people can share a name — `p1039` Will
Smith (C) and `p1088` Will Smith (RP, retired) — which is why the key is a pid, not a name.

## Ingest

    python3 ingest.py paste.txt              # dry run, report only
    python3 ingest.py paste.txt --apply      # write, only if clean

Nothing is written unless the whole batch validates. Pastes come from ESPN's player pool, so
misspellings are not the risk — **name changes are** (Mike Stanton to Giancarlo Stanton). A
rename surfaces as a drop of a player who is not on any roster, so the validator checks the
dropping team for a near-identical name and a shared surname before reporting him missing.
When it asks, add the new spelling to that player's `aliases` and re-run. Never mint a second pid.
