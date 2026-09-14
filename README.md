# BGBL data

| File | What it is |
|---|---|
| `registry.json` | Every player who has ever been in the league (1,087). `pid` is the permanent key; `name` is an attribute that can change. `aliases` holds prior spellings so old pastes still match. |
| `transactions.json` | Append-only log, every record keyed by `pid`. This is the primary artifact. |
| `ledger.json` | Current rosters and salaries — a **derived view**, rebuilt from the baseline plus the log. |

## Player identity

`pid` never changes and is never reused. Correcting a spelling edits `name` and pushes the
old form into `aliases`; it does not create a new player. A player keeps his `pid` when he is
dropped, sits in the free-agent pool, and is signed again years later by someone else.

## Ingest

    python3 tools/ingest.py paste.txt              # dry run, report only
    python3 tools/ingest.py paste.txt --apply      # write, only if clean

Nothing is written unless the entire batch validates. See `tools/ingest.py` for the rules.

Pastes are copied from ESPN's player pool, never typed, so misspellings are not the risk the
validator guards against. **Name changes are** — Mike Stanton becoming Giancarlo Stanton. A rename
surfaces as a drop of a player who is not on any roster, so the validator checks the dropping
team's roster for both a near-identical name and a shared surname before reporting him missing.

When it asks, the fix is to add the new spelling to that player's `aliases` in `registry.json`
and re-run. Never mint a second `pid` for a renamed player.

A rename with no surname in common (Fausto Carmona to Roberto Hernandez) cannot be detected by
name. It still halts the batch as a drop of an unrostered player, so it can never silently
corrupt the ledger - it just needs a human to recognise it.
