# BGBL — Transaction Logging Runbook

Start a fresh chat with this file and `league-constants.json` and you have everything needed
to log transactions. You do not need the conversation that built any of this.

## What you're working with

The repo is public: `https://github.com/kellertyj-sudo/bgbl-ledger`
Live site: `https://kellertyj-sudo.github.io/bgbl-ledger/`
Local clone: `C:\Users\tyjke\OneDrive\Documents\GitHub\bgbl-ledger`

| File | Role |
|---|---|
| `ledger.json` | Current rosters, salaries, team payrolls, and the season `log`. What the site renders. |
| `registry.json` | Every player ever. `pid` is permanent and never reused. |
| `transactions.json` | Append-only per-player history keyed by `pid`. |
| `ingest.py` | Validates and applies. Writes all three. |
| `index.html` | The site. Reads `ledger.json` at load. |

## Standing rule: if something looks off, stop and ask Ty

**Ty's instruction, 2026-09-21. This outranks every other instinct in this file.**

`ingest.py` halts on things that are mechanically *invalid*. This rule covers the other category:
things that validate fine but look **strange**. Do not resolve them yourself, do not pick the
reading that seems most likely, and do not "correct" anything on your own judgment. Name the
oddity, say what you'd do about it, and wait for an answer.

**The line that matters: appending is routine, editing is not.**
Adding transactions to the log is the normal loop — do it. **Changing a value that is already in
`ledger.json`, `registry.json` or `transactions.json` is never routine.** An append is replayable
and reversible; an edit to existing state is neither, and it silently rewrites history. Every such
edit needs Ty's explicit yes first, even when you are confident.

Ask before acting on any of these:

- **A rostered player's ESPN salary disagrees with the ledger.** "ESPN transaction salaries are
  binding" applies to the **bid at the moment of acquisition** — a draft price or a winning FAAB
  bid. It is *not* a licence to sync a salary later. ESPN cannot represent cash assets or
  liabilities, and Ty's only workaround is to fake a player's salary there. Syncing that into the
  ledger puts a fabricated number into the real salary cap. See `cashAssetsAndLiabilities` in
  `league-constants.json`.
- **Any year, escalator or tag that doesn't match what the rules would produce.**
- **A transaction that contradicts one already logged** — a reversal, a duplicate, a move dated
  before something it depends on.
- **Anything that would change a number Ty entered by hand**, including the migration baseline.
- **Anything you are about to reconcile "for consistency."** That phrase is the warning sign.
- **Anything this runbook doesn't cover.** An unfamiliar situation is a question, not a judgment
  call.

This is not the same as second-guessing league strategy — see "Things that are NOT problems" below.
Odd *data* gets a question. Odd-looking *moves* get logged without comment.

## What actually matters (Ty, 2026-09-21)

**Rosters being correct, and staying correct, is the job.** Dates are of mild importance.
Historical transactions are settled — don't re-litigate them; correct an obvious error if one
surfaces and move on. 2026-09-21 set the baseline; everything after it is a delta.

## The loop

1. **Get the moves.** Either Ty pastes them, or pull them from the ESPN API (see
   `league-constants.json` → `espnApi`; the league is private, so the calls run from a
   signed-in browser).
2. **Save to a file** in the clone — `paste.txt` for an ESPN text paste, or `events.json`
   for an API event list.
3. **Dry run first, always.**
   ```
   python3 ingest.py paste.txt
   ```
   Exit 0 = clean. Exit 1 = held, nothing written.
4. **Read what it says.** If it held, fix the cause — do not force it through.
5. **Apply.**
   ```
   python3 ingest.py paste.txt --apply
   ```
6. **Ty commits and pushes.** You can write into the clone; you cannot push.
   ```
   git add -A && git commit -m "..." && git push
   ```
   Pages rebuilds in about 30 seconds.

## Event shape (the JSON path)

```json
{"date":"2026-09-13","type":"add","team":"BORG","player":"Jeffrey Springs",
 "mlb":"ATH","positions":"SP","salary":3,"counterparty":"","wm":false}
```

`type` is `add` | `drop` | `trade_in` | `trade_out`. Trades arrive as **paired legs** and
`ingest.py` collapses them to one move per player. Dates are **Pacific**.

## Rules the ingest applies

| Event | Salary | Year | Tags |
|---|---|---|---|
| FA add | winning FAAB bid | 1 | `FA` |
| Draft | winning auction bid | 1 | `DRAFT` |
| Trade | unchanged | resets to 1 | `TRADE` |
| Trade in the WM window | unchanged | **0** | `WM TRADE` |
| Kept at the deadline | prior + escalator | increments | arrival tag **+ `KEEP`** |

Escalator by year entered: 2 → +$1, 3 → +$3, 4 → +$5, 5 → +$7, 6+ → +$5. Year 0 → 1 takes
nothing; that is the Winter Meetings waiver.

Set the season's Winter Meetings date before processing offseason trades — `wmDate` in
`ledger.json`, or `--wm-date YYYY-MM-DD`. **It moves every year. Never infer it.**

The keeper deadline is its own operation, not a paste:
```
python3 ingest.py --keeper-roll 2027-03-20 --apply
```

## When it holds the batch

**"DROP of X — not on any roster, but TEAM holds 'Y'."** Almost always a name change
(Mike Stanton → Giancarlo Stanton). Add the new spelling to that player's `aliases` in
`registry.json` and re-run. **Never mint a second pid.**

**"ADD of X is unknown but nearly matches 'Y'."** Same question, other direction. Decide
whether it's a rename or a genuinely new player, then either alias it or let it mint.

**"ADD of X — already rostered by TEAM."** The batch is out of order, or a drop is missing.

**"ROSTER LIMIT — TEAM would hold N."** Limit is 29 (26 active + 3 IL). Something is missing
or ESPN and the ledger have diverged.

Nothing is written unless the whole batch is clean. That is the point — don't work around it.

## Things that are NOT problems — don't flag them

These are **league-strategy** judgments, not data anomalies. Log them and move on. The
stop-and-ask rule at the top of this file is about the *data* looking wrong, not about an owner
making a move you find surprising.


- **A team drops a player and signs him back off waivers.** Legal. The no-reacquisition rule
  covers trades only: you can't trade a player away and trade him back in the same league year
  to reset his escalator. Waiver moves are unrestricted.
- **A big FAAB bid late in the season.** FAAB doesn't carry over, so a contending team spending
  $9 in week 24 is playing correctly, not making a mistake.
- **A team picking up another team's expensive keeper cheap off waivers.** The escalator resets
  for the new owner by design. That's the system working.

## Things that have already gone wrong once

- **UTC vs Pacific.** The ESPN API returns UTC; the league runs on PT. Evening moves roll onto
  the next UTC day. This misdated 36 events before it was caught.
- **Trades vanish from `mTransactions2`.** Once a trade is accepted its player list moves to a
  proposal record the endpoint won't serve. Take trades from the activity feed (`messageTypeId`
  224) and salaries from `mTransactions2`. Neither source is complete alone.
- **Lineup slot ids masquerade as team ids** on `messageTypeId` 239 and 245. Slots 1–12 collide
  with teams 1–12, so mapping them through a team table produces confident wrong answers.
- **Same-name players.** `p1039` Will Smith (C) and `p1088` Will Smith (RP, retired). The
  registry disambiguates with a position suffix on `key`; resolve by position group.
- **ESPN censors GORD's team name.** The ledger value is right. Don't sync that one.
- **Reversals.** On 2026-07-30 a trade was partly reversed and redone within an hour. Pacific
  timestamps resolved the order; the log keeps the net result only.

## Verify before declaring victory

The site catches its own load failure and renders it into a banner rather than throwing, so a
page that *parses* can still be broken. If you touch `index.html`, check that the error banner
is empty and that the data actually rendered — 12 budget rows, 12 team tables, a populated log —
not just that there were no JS errors.
