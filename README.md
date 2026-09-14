# BGBL Ledger

Live at https://kellertyj-sudo.github.io/bgbl-ledger/

Everything sits at the repo root — no folders. GitHub's web uploader flattens directories,
so the layout is flat by design.

| File | What it is |
|---|---|
| `index.html` | The site. Reads its data from `ledger.json` at load time. |
| `ledger.json` | **Current rosters, salaries, team names and the season transaction log.** |
| `registry.json` | Every player ever in the league. `pid` is the permanent key. |
| `transactions.json` | Append-only per-player history, keyed by `pid`. |
| `ingest.py` | Parse, validate and apply transactions. Writes all three JSON files. |

## Making a small change

Open `ledger.json` on GitHub, click the pencil, edit, commit. The site picks it up on the
next load — nothing to rebuild, nothing to regenerate. CSV downloads are generated in the
browser from the same file, so they can never drift out of step with what's on screen.

Team names live in the `teams` array; player rows live in `players`; the season's moves live
in `log`. Team `payroll` and `nextPayroll` are **derived** — `ingest.py` recomputes them from
the player rows on every apply, so don't hand-edit them and expect them to stick.

## Player identity

`pid` never changes and is never reused. A name change edits `name` and pushes the old form
into `aliases`; it never mints a second player. Two people can share a name — `p1039` Will
Smith (C) and `p1088` Will Smith (RP, retired) — which is why the key is a pid, not a name.
Same-name players are disambiguated in the registry by a position suffix on `key`
(`will smith c` / `will smith rp`); `ingest.py` resolves them by position group.

## Acquisition is a set of tags, not one value

A player carries **how he arrived** and, separately, **whether he was retained**:

| Tag | Meaning |
|---|---|
| `FA` | Signed off waivers for a FAAB bid |
| `TRADE` | Acquired by trade |
| `WM TRADE` | Acquired in the Winter Meetings window — escalator waived, arrives at existing salary |
| `DRAFT` | Bought in the auction |
| `KEEP` | Retained at the keeper deadline |

Exactly one arrival tag, plus `KEEP` once he survives a deadline. `FA + KEEP` — signed in June,
kept in March — is the second most common combination on the board and cannot be expressed as
a single value. The `acquired` field is still populated as one string for backward compatibility,
but `tags` is the truth.

## The league year

Three moments, and **their dates move every year — never hardcode them**:

1. **Winter Meetings.** Ends the old league year, starts the new one. Next Year Salaries take
   effect at 12:00 AM PT at the close. A trade inside that 24-hour window waives the escalator:
   the player arrives at his existing salary and carries **Year 0**.
2. **Keeper deadline.** Rosters finalize — functionally the start of the season. Year 0 becomes
   Year 1; everyone else advances a year and takes their escalator. Year 0 never survives this.
3. **Draft.** Effectively a large FAAB session — auction buys enter at Year 1 for the winning bid.

Set the season's Winter Meetings date as `wmDate` in `ledger.json`, or pass `--wm-date`.
2026's was `2026-02-01` (Pacific).

**Dates are Pacific.** The ESPN API returns UTC; anything logged after ~4–5 PM PT rolls onto the
next UTC day, which put 36 events on the wrong date before this was caught.

## Ingest

    python3 ingest.py paste.txt              # dry run, report only
    python3 ingest.py paste.txt --apply      # write ledger + registry + transactions
    python3 ingest.py events.json --apply    # same, from an ESPN-API event list
    python3 ingest.py --keeper-roll 2027-03-20 --apply

Input is either an ESPN "Recent Activity" text paste or a JSON event list
(`{date, type, team, player, mlb, positions, salary, counterparty, wm}` with `type` in
`add` / `drop` / `trade_in` / `trade_out`). Trades arrive as paired legs and are collapsed to
one move per player.

Nothing is written unless the whole batch validates. Pastes come from ESPN's player pool, so
misspellings are not the risk — **name changes are** (Mike Stanton to Giancarlo Stanton). A
rename surfaces as a drop of a player who is not on any roster, so the validator checks the
dropping team for a near-identical name and a shared surname before reporting him missing.
When it asks, add the new spelling to that player's `aliases` in `registry.json` and re-run.
Never mint a second pid.

## Getting the ESPN data

The Recent Activity page is paginated with no export, but it sits on top of two API endpoints
that return the whole season in about twenty calls. The league is private, so the calls must run
from a signed-in browser session. Both are needed: `mTransactions2` has the FAAB and auction
amounts but loses trades once they're accepted, and the `communication` feed has every trade but
no salaries.
