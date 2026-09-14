#!/usr/bin/env python3
"""
BGBL transaction ingest.

Reads a raw ESPN transaction paste, validates every move against current
ledger state, and applies NOTHING unless the entire batch is clean.

    python3 ingest.py paste.txt              # dry run - report only
    python3 ingest.py paste.txt --apply      # write ledger + transactions

Exit 0 = clean. Exit 1 = held for review, nothing written.
"""
import json, re, sys, unicodedata, difflib, datetime, pathlib

HERE = pathlib.Path(__file__).resolve().parent
MON = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
ESC = {0: 0, 1: 0, 2: 1, 3: 3, 4: 5, 5: 7}
NEAR = 0.87          # similarity above which two names are probably the same person
# Pastes are copied from ESPN, never typed, so misspellings are not the threat.
# The threat is a player who CHANGED HIS NAME (Mike Stanton -> Giancarlo Stanton).
# Ratio alone misses that (0.62), so surname matching carries the real weight.
POSMAP = {"LF": "OF", "CF": "OF", "RF": "OF", "DH": "UT", "UTIL": "UT"}


def surname(k):
    return k.rsplit(" ", 1)[-1] if " " in k else k


def key(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    n = re.sub(r"\b(jr|sr|ii|iii)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


# ---------------------------------------------------------------- parsing
DATE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3}) (\d{1,2})$")
TAIL = re.compile(r"^([A-Z]{3,4}) (?:RosterOffers Report|Roster)$")
ADD = re.compile(r"^(?:.*?) added (.+?), ([A-Z]{2,3}) ([A-Z0-9]{1,2}) from Waivers for \$(\d+)$")
DROP = re.compile(r"^(?:.*?) dropped (.+?), ([A-Z]{2,3}) ([A-Z0-9]{1,2}) (?:to Waivers|from Roster)$")


def parse(text, year):
    lines = [l.rstrip() for l in text.split("\n")]
    out, i = [], 0
    while i < len(lines):
        m = DATE.match(lines[i])
        if not m:
            i += 1
            continue
        date = f"{year}-{MON[m.group(1)]:02d}-{int(m.group(2)):02d}"
        j = i + 2                                    # skip the time line
        if j < len(lines) and lines[j] == "Transaction":
            j += 1
        j += 1                                       # skip the type line
        ev = {"date": date, "add": None, "drop": None, "salary": None, "team": None}
        while j < len(lines) and not TAIL.match(lines[j]):
            a, d = ADD.match(lines[j]), DROP.match(lines[j])
            if a:
                ev["add"] = (a.group(1), a.group(2), a.group(3)); ev["salary"] = int(a.group(4))
            elif d:
                ev["drop"] = (d.group(1), d.group(2), d.group(3))
            elif lines[j].strip():
                raise SystemExit(f"UNPARSED LINE: {lines[j]!r}")
            j += 1
        if j >= len(lines):
            raise SystemExit(f"block starting {date} has no team footer")
        ev["team"] = TAIL.match(lines[j]).group(1)
        out.append(ev); i = j + 1
    return out


# ---------------------------------------------------------------- validation
def run(paste_path, apply=False, year=None):
    year = year or datetime.date.today().year
    led = json.loads((HERE / "ledger.json").read_text())
    reg = json.loads((HERE / "registry.json").read_text())
    txf = json.loads((HERE / "transactions.json").read_text())

    by_key = {r["key"]: r for r in reg["registry"]}
    for r in reg["registry"]:
        for a in r["aliases"]:
            by_key.setdefault(key(a), r)
    roster = {key(p["player"]): p for p in led["players"]}
    teams = {t["abbr"] for t in led["teams"]}

    events = parse(pathlib.Path(paste_path).read_text(), year)
    problems, newcomers, staged = [], [], []

    def flag(ev, msg):
        problems.append(f"{ev['date']}  {ev['team']:5} {msg}")

    for ev in sorted(events, key=lambda e: e["date"]):
        if ev["team"] not in teams:
            flag(ev, f"unknown team code {ev['team']!r}")
            continue
        # ---- the drop leg
        if ev["drop"]:
            nm = ev["drop"][0]; kk = key(nm)
            held = roster.get(kk)
            if held is None:
                # a rename shows up here first: ESPN uses the new name, the ledger the old one
                same_team = {key(p["player"]): p for p in roster.values()
                             if p["team"] == ev["team"]}
                cand = difflib.get_close_matches(kk, list(same_team), n=1, cutoff=NEAR)
                if not cand:
                    cand = [c for c in same_team if surname(c) == surname(kk)]
                if cand:
                    was = same_team[cand[0]]["player"]
                    flag(ev, f"DROP of {nm} - not on any roster, but {ev['team']} holds "
                             f"{was!r}. Same player under a new name? If so add {nm!r} to "
                             f"that player's aliases in registry.json and re-run.")
                else:
                    flag(ev, f"DROP of {nm} - not on any roster")
            elif held["team"] != ev["team"]:
                flag(ev, f"DROP of {nm} - actually on {held['team']}")
            else:
                del roster[kk]
                staged.append({"type": "release", "date": ev["date"], "name": held["player"],
                               "from": ev["team"], "salary": 0})
        # ---- the add leg
        if ev["add"]:
            nm, mlb, pos = ev["add"]; kk = key(nm)
            held = roster.get(kk)
            if held is not None:
                flag(ev, f"ADD of {nm} - already rostered by {held['team']}")
                continue
            known = by_key.get(kk)
            if known is None:
                close = difflib.get_close_matches(kk, list(by_key), n=1, cutoff=NEAR)
                if close:
                    flag(ev, f"ADD of {nm!r} is unknown but nearly matches "
                             f"{by_key[close[0]]['name']!r} ({by_key[close[0]]['pid']}) - "
                             f"same player renamed, or genuinely new?")
                    continue
                kin = [by_key[c] for c in by_key if surname(c) == surname(kk)][:3]
                newcomers.append((nm, mlb, pos, kin))
            p = POSMAP.get(pos, pos)
            roster[kk] = {"player": known["name"] if known else nm, "team": ev["team"],
                          "positions": p, "salary": ev["salary"], "year": 1}
            staged.append({"type": "fa_add", "date": ev["date"],
                           "name": known["name"] if known else nm, "to": ev["team"],
                           "salary": ev["salary"], "mlb": mlb, "pos": p,
                           "pid": known["pid"] if known else None})

    # ---- structural checks
    counts = {}
    for p in roster.values():
        counts[p["team"]] = counts.get(p["team"], 0) + 1
    for t, n in sorted(counts.items()):
        if n > 29:
            problems.append(f"ROSTER LIMIT   {t} would hold {n} players (max 29 = 26 + 3 IL)")

    # ---- report
    print(f"parsed {len(events)} transactions from {paste_path}")
    if newcomers:
        print(f"\nNEW TO THE LEAGUE ({len(newcomers)}) - will be minted a pid:")
        for nm, mlb, pos, kin in newcomers:
            print(f"   {nm:26} {mlb:4} {pos}")
            for x in kin:
                print(f"      note: registry already has {x['name']!r} ({x['pid']}, "
                      f"{x['positions'] or '?'}) - same surname, presumed a different player")
    if problems:
        print(f"\nHELD FOR REVIEW - {len(problems)} problem(s), nothing applied:\n")
        for p in problems:
            print("   " + p)
        return 1
    print(f"\nclean: {len(staged)} moves reconcile against every roster")
    if not apply:
        print("dry run - rerun with --apply to write")
        return 0
    # ---- apply (only ever reached on a clean batch)
    nxt = max(int(r["pid"][1:]) for r in reg["registry"]) + 1
    kmap = {r["key"]: r for r in reg["registry"]}
    for nm, mlb, pos, _kin in newcomers:
        reg["registry"].append({"pid": f"p{nxt:04d}", "name": nm, "key": key(nm), "aliases": [],
                                "mlb": mlb, "positions": POSMAP.get(pos, pos),
                                "status": "free", "team": "", "trello": "", "review": ""})
        kmap[key(nm)] = reg["registry"][-1]; nxt += 1
    tn = max([int(t["txid"][1:]) for t in txf["transactions"]] or [0]) + 1
    for s in staged:
        r = kmap[key(s["name"])]
        txf["transactions"].append({"txid": f"t{tn:05d}", "date": s["date"], "type": s["type"],
                                    "pid": r["pid"], "player": r["name"],
                                    "to": s.get("to"), "from": s.get("from"),
                                    "salary": s["salary"], "source": "espn-paste"})
        tn += 1
    (HERE / "registry.json").write_text(json.dumps(reg, indent=1))
    (HERE / "transactions.json").write_text(json.dumps(txf, indent=1))
    print(f"applied: +{len(newcomers)} players, +{len(staged)} transactions")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(run(args[0], apply="--apply" in sys.argv,
                 year=int(args[1]) if len(args) > 1 else None))
