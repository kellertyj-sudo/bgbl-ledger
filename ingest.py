#!/usr/bin/env python3
"""
BGBL transaction ingest.

Validates every move against current ledger state and applies NOTHING unless
the entire batch is clean.

    python3 ingest.py paste.txt               # dry run, report only
    python3 ingest.py paste.txt --apply       # write ledger + registry + transactions
    python3 ingest.py events.json --apply     # same, from an ESPN-API event list
    python3 ingest.py --keeper-roll 2027-03-20 --apply    # keeper deadline

Exit 0 = clean. Exit 1 = held for review, nothing written.

Input may be either:
  * an ESPN "Recent Activity" text paste, or
  * a JSON list of events pulled from the ESPN API, each
    {date, type, team, player, mlb, positions, salary, counterparty, wm}
    with type in {add, drop, trade_in, trade_out}.

WINTER MEETINGS. Pass --wm-date YYYY-MM-DD for the season being processed, or
set it in ledger.json as "wmDate". A trade inside that 24h window waives the
escalator: the player arrives at his existing salary and carries Year 0 until
the keeper deadline, where he enters Year 1. The date moves every year - it is
never inferred and never hardcoded.
"""
import json, re, sys, unicodedata, difflib, datetime, pathlib

HERE = pathlib.Path(__file__).resolve().parent
MON = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
ESC = {0: 0, 1: 0, 2: 1, 3: 3, 4: 5, 5: 7}     # escalator BY the year being entered
LIMIT = 29                                      # 26 active + 3 IL
NEAR = 0.87          # similarity above which two names are probably the same person
# Pastes are copied from ESPN, never typed, so misspellings are not the threat.
# The threat is a player who CHANGED HIS NAME (Mike Stanton -> Giancarlo Stanton).
# Ratio alone misses that (0.62), so surname matching carries the real weight.
POSMAP = {"LF": "OF", "CF": "OF", "RF": "OF", "DH": "UT", "UTIL": "UT"}
ARRIVAL = ("FA", "TRADE", "WM TRADE", "DRAFT")  # mutually exclusive; KEEP stacks on top


def escalator(entering_year):
    return ESC.get(entering_year, 5)


def surname(k):
    return k.rsplit(" ", 1)[-1] if " " in k else k


def key(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    n = re.sub(r"\b(jr|sr|ii|iii)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def reprice(p):
    """Recompute the forward-looking fields from salary + year. Year 0 takes no
    escalator into Year 1 - that is the Winter Meetings waiver."""
    p["nextYear"] = p["year"] + 1
    p["escalator"] = escalator(p["nextYear"]) if p["year"] > 0 else 0
    p["nextSalary"] = p["salary"] + p["escalator"]
    return p


def set_tags(p, arrival=None, keep=False):
    """Acquisition is a SET, not one value. An arrival replaces the arrival tag and
    clears KEEP; a keeper-deadline retention adds KEEP and leaves arrival alone.
    `acquired` stays populated as a single value for the current site."""
    tags = [t for t in p.get("tags", []) if t in ("KEEP",) or t in ARRIVAL]
    if arrival:
        tags = [t for t in tags if t not in ARRIVAL and t != "KEEP"] + [arrival]
    if keep and "KEEP" not in tags:
        tags.append("KEEP")
    order = {t: i for i, t in enumerate(ARRIVAL + ("KEEP",))}
    p["tags"] = sorted(set(tags), key=lambda t: order.get(t, 99))
    if "KEEP" in p["tags"]:
        p["acquired"] = "Keep"
    else:
        p["acquired"] = {"FA": "FA", "TRADE": "Trade", "WM TRADE": "Trade",
                         "DRAFT": "Draft"}.get(
                             next((t for t in p["tags"] if t in ARRIVAL), "FA"), "FA")
    return p


# ---------------------------------------------------------------- parsing
DATE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3}) (\d{1,2})$")
TAIL = re.compile(r"^([A-Z]{3,4}) (?:RosterOffers Report|Roster)$")
ADD = re.compile(r"^(?:.*?) added (.+?), ([A-Z]{2,3}) ([A-Z0-9]{1,2}) from Waivers for \$(\d+)$")
DROP = re.compile(r"^(?:.*?) dropped (.+?), ([A-Z]{2,3}) ([A-Z0-9]{1,2}) (?:to Waivers|from Roster)$")
TRADE = re.compile(r"^([A-Z]{3,4}) traded (.+?), ([A-Z]{2,3}) ([A-Z0-9]{1,2})(?: to ([A-Z]{3,4}))?$")


def parse_paste(text, year):
    """ESPN Recent Activity paste -> flat event list (same shape as the JSON path)."""
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
        block = []
        while j < len(lines) and not TAIL.match(lines[j]):
            a, d, t = ADD.match(lines[j]), DROP.match(lines[j]), TRADE.match(lines[j])
            if a:
                block.append({"type": "add", "player": a.group(1), "mlb": a.group(2),
                              "positions": a.group(3), "salary": int(a.group(4))})
            elif d:
                block.append({"type": "drop", "player": d.group(1), "mlb": d.group(2),
                              "positions": d.group(3), "salary": 0})
            elif t:
                block.append({"type": "trade_out", "player": t.group(2), "mlb": t.group(3),
                              "positions": t.group(4), "salary": 0,
                              "team": t.group(1), "counterparty": t.group(5) or ""})
            elif lines[j].strip():
                raise SystemExit(f"UNPARSED LINE: {lines[j]!r}")
            j += 1
        if j >= len(lines):
            raise SystemExit(f"block starting {date} has no team footer")
        team = TAIL.match(lines[j]).group(1)
        for e in block:
            e.setdefault("team", team)
            e["date"] = date
            e.setdefault("counterparty", "")
            e.setdefault("wm", False)
            out.append(e)
        i = j + 1
    return out


def load_events(path, year):
    raw = pathlib.Path(path).read_text()
    if path.endswith(".json") or raw.lstrip().startswith(("[", "{")):
        data = json.loads(raw)
        evs = data["events"] if isinstance(data, dict) else data
        for e in evs:
            e.setdefault("counterparty", "")
            e.setdefault("wm", False)
            e.setdefault("salary", 0)
        return evs
    return parse_paste(raw, year)


# ---------------------------------------------------------------- apply
def run(src=None, apply=False, year=None, wm_date=None, keeper_roll=None):
    year = year or datetime.date.today().year
    led = json.loads((HERE / "ledger.json").read_text())
    reg = json.loads((HERE / "registry.json").read_text())
    txf = json.loads((HERE / "transactions.json").read_text())
    wm_date = wm_date or led.get("wmDate")

    # The registry disambiguates same-name players with a position suffix
    # ("will smith c" / "will smith rp"), so a bare name key will not match them.
    index = {}
    for r in reg["registry"]:
        index.setdefault(r["key"], []).append(r)
        for a in r["aliases"]:
            index.setdefault(key(a), []).append(r)
    by_key = {k: v[0] for k, v in index.items()}

    def group(pos):
        return "P" if (pos or "").split("/")[0] in ("SP", "RP") else "B"

    def resolve(name, pos=""):
        k = key(name)
        if k in by_key:
            return by_key[k]
        cands = [r for kk, v in index.items() if kk.startswith(k + " ") for r in v]
        if not cands:
            return None
        if pos:
            same = [r for r in cands if group(r.get("positions")) == group(pos)]
            if len(same) == 1:
                return same[0]
        live = [r for r in cands if r.get("status") != "retired"]
        return live[0] if len(live) == 1 else None
    roster = {key(p["player"]): p for p in led["players"]}
    teams = {t["abbr"] for t in led["teams"]}
    problems, newcomers, staged, logged = [], [], [], []

    def flag(ev, msg):
        problems.append(f"{ev.get('date','?')}  {ev.get('team','?'):5} {msg}")

    # -------------------------------------------------- keeper deadline roll
    if keeper_roll:
        for p in roster.values():
            p["year"] = 1 if p["year"] == 0 else p["year"] + 1
            if p["year"] > 1:
                p["salary"] += escalator(p["year"])
            set_tags(p, keep=True)
            reprice(p)
            logged.append({"date": keeper_roll, "type": "keep", "team": p["team"],
                           "player": p["player"], "positions": p["positions"],
                           "salary": p["salary"], "counterparty": ""})
        print(f"keeper roll {keeper_roll}: {len(roster)} players advanced a service year")
    else:
        if not src:
            raise SystemExit("give a paste/JSON file, or --keeper-roll DATE")
        events = load_events(src, year)

        # trades arrive as paired legs; collapse to one move per (date, player)
        pairs, singles = {}, []
        for e in sorted(events, key=lambda e: (e["date"], e.get("player", ""))):
            if e["type"] in ("trade_in", "trade_out"):
                k = (e["date"], key(e["player"]))
                slot = pairs.setdefault(k, {})
                slot[e["type"]] = e
            else:
                singles.append(e)
        for k, slot in pairs.items():
            tin, tout = slot.get("trade_in"), slot.get("trade_out")
            e = dict(tin or tout)
            e["type"] = "trade"
            e["to"] = (tin or {}).get("team") or (tout or {}).get("counterparty") or ""
            e["from"] = (tout or {}).get("team") or (tin or {}).get("counterparty") or ""
            e["wm"] = bool((tin or tout).get("wm"))
            singles.append(e)

        for ev in sorted(singles, key=lambda e: (e["date"], e["type"])):
            t = ev["type"]
            if t != "trade" and ev.get("team") not in teams:
                flag(ev, f"unknown team code {ev.get('team')!r}")
                continue

            # ---------------------------------------------------- drop
            if t == "drop":
                nm = ev["player"]; kk = key(nm)
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
                    staged.append({"type": "release", "date": ev["date"],
                                   "name": held["player"], "from": ev["team"], "salary": 0})
                    logged.append({"date": ev["date"], "type": "drop", "team": ev["team"],
                                   "player": held["player"], "positions": held["positions"],
                                   "salary": held["salary"], "counterparty": ""})

            # ---------------------------------------------------- add
            elif t == "add":
                nm, mlb, pos = ev["player"], ev.get("mlb", ""), ev.get("positions", "")
                kk = key(nm)
                held = roster.get(kk)
                if held is not None:
                    flag(ev, f"ADD of {nm} - already rostered by {held['team']}")
                    continue
                known = resolve(nm, pos)
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
                new = {"player": known["name"] if known else nm, "team": ev["team"],
                       "positions": p, "primary": p.split("/")[0], "mlb": mlb,
                       "salary": ev["salary"], "year": 1,
                       "pid": known["pid"] if known else None, "rank": 0,
                       "group": "P" if p.split("/")[0] in ("SP", "RP") else "B"}
                reprice(set_tags(new, arrival="FA"))
                roster[kk] = new
                staged.append({"type": "fa_add", "date": ev["date"], "name": new["player"],
                               "to": ev["team"], "salary": ev["salary"], "mlb": mlb, "pos": p,
                               "pid": known["pid"] if known else None})
                logged.append({"date": ev["date"], "type": "add", "team": ev["team"],
                               "player": new["player"], "positions": p,
                               "salary": ev["salary"], "counterparty": ""})

            # ---------------------------------------------------- trade
            elif t == "trade":
                nm = ev["player"]; kk = key(nm)
                src_t, dst_t = ev.get("from", ""), ev.get("to", "")
                if dst_t not in teams:
                    flag(ev, f"TRADE of {nm} - unknown destination {dst_t!r}")
                    continue
                held = roster.get(kk)
                if held is None:
                    flag(ev, f"TRADE of {nm} - not on any roster")
                    continue
                if src_t and held["team"] != src_t:
                    flag(ev, f"TRADE of {nm} from {src_t} - actually on {held['team']}")
                    continue
                inside_wm = bool(ev.get("wm")) or (wm_date and ev["date"] == wm_date)
                held["team"] = dst_t
                held["year"] = 0 if inside_wm else 1     # salary itself never moves on a trade
                reprice(set_tags(held, arrival="WM TRADE" if inside_wm else "TRADE"))
                staged.append({"type": "trade_in", "date": ev["date"], "name": held["player"],
                               "to": dst_t, "from": src_t, "salary": 0, "wm": inside_wm})
                logged.append({"date": ev["date"], "type": "trade_out", "team": src_t,
                               "player": held["player"], "positions": held["positions"],
                               "salary": 0, "counterparty": dst_t, "wm": inside_wm})
                logged.append({"date": ev["date"], "type": "trade_in", "team": dst_t,
                               "player": held["player"], "positions": held["positions"],
                               "salary": 0, "counterparty": src_t, "wm": inside_wm})
            else:
                flag(ev, f"unknown event type {t!r}")

    # -------------------------------------------------- structural checks
    counts = {}
    for p in roster.values():
        counts[p["team"]] = counts.get(p["team"], 0) + 1
    for tm, n in sorted(counts.items()):
        if n > LIMIT:
            problems.append(f"ROSTER LIMIT   {tm} would hold {n} players (max {LIMIT} = 26 + 3 IL)")

    # -------------------------------------------------- report
    print(f"parsed {len(logged)} ledger movements from {src or 'keeper roll'}")
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
    print(f"\nclean: {len(logged)} movements reconcile against every roster")
    if not apply:
        print("dry run - rerun with --apply to write")
        return 0

    # -------------------------------------------------- apply (clean batches only)
    nxt = max(int(r["pid"][1:]) for r in reg["registry"]) + 1
    kmap = {r["key"]: r for r in reg["registry"]}
    for nm, mlb, pos, _kin in newcomers:
        reg["registry"].append({"pid": f"p{nxt:04d}", "name": nm, "key": key(nm), "aliases": [],
                                "mlb": mlb, "positions": POSMAP.get(pos, pos),
                                "status": "rostered", "team": "", "trello": "", "review": ""})
        kmap[key(nm)] = reg["registry"][-1]; nxt += 1
    for p in roster.values():                        # backfill pids minted just now
        if not p.get("pid"):
            r = kmap.get(key(p["player"])) or resolve(p["player"], p.get("positions", ""))
            p["pid"] = r["pid"] if r else None

    tn = max([int(t["txid"][1:]) for t in txf["transactions"]] or [0]) + 1
    for s in staged:
        r = kmap.get(key(s["name"])) or resolve(s["name"], s.get("pos", ""))
        row = {"txid": f"t{tn:05d}", "date": s["date"], "type": s["type"],
               "pid": r["pid"], "player": r["name"],
               "to": s.get("to"), "from": s.get("from"),
               "salary": s["salary"], "source": "espn"}
        if s.get("wm"):
            row["wm"] = True
        txf["transactions"].append(row); tn += 1

    led["players"] = sorted(roster.values(), key=lambda p: (p["team"], p["player"]))
    led["log"] = led.get("log", []) + logged
    led["asOf"] = max([e["date"] for e in logged] or [led.get("asOf", "")])
    if wm_date:
        led["wmDate"] = wm_date
    for t in led["teams"]:                            # payrolls are derived, never typed
        ps = [p for p in led["players"] if p["team"] == t["abbr"]]
        t["count"] = len(ps)
        t["payroll"] = sum(p["salary"] for p in ps)
        t["nextPayroll"] = sum(p["nextSalary"] for p in ps)

    (HERE / "registry.json").write_text(json.dumps(reg, indent=1))
    (HERE / "transactions.json").write_text(json.dumps(txf, indent=1))
    (HERE / "ledger.json").write_text(json.dumps(led, indent=1))
    print(f"applied: +{len(newcomers)} players, +{len(staged)} transactions, "
          f"+{len(logged)} log rows; ledger.json rewritten through {led['asOf']}")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    def opt(name):
        return argv[argv.index(name) + 1] if name in argv else None
    files = [a for a in argv if not a.startswith("--") and
             not (argv.index(a) and argv[argv.index(a) - 1] in ("--wm-date", "--keeper-roll", "--year"))]
    sys.exit(run(src=files[0] if files else None,
                 apply="--apply" in argv,
                 year=int(opt("--year")) if opt("--year") else None,
                 wm_date=opt("--wm-date"),
                 keeper_roll=opt("--keeper-roll")))
