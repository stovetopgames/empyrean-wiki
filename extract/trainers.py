"""Trainer battles, mined out of map events and the GymTeams script.

Almost every battle in the game is built the same way in an event script:

    party = [createPokemon("WEAVILE", 55, [:ICEPUNCH]), ...]
    party[0].item = PBItems::LEFTOVERS
    trainer = createTrainer(160, "Lena", party)

or with named locals (p1, p2, ...) collected into `party` at the end. Both
shapes are handled here by a small interpreter over the event's script text,
rather than trying to run Ruby.

Signatures (from the Tournament script):
    createPokemon(species, level, moveset=nil, gender=nil)
    createTrainer(trainerid, trainername, party, items=[])
"""
import glob
import os
import re

import marshal48
import pbs

SCRIPT_CODES = (355, 655)
TEXT_CODES = (101, 401)

CREATE_POKEMON = re.compile(
    r'createPokemon\(\s*"([^"]+)"\s*,\s*(\d+)\s*'
    r'(?:,\s*(\[[^\]]*\]|nil)\s*)?'
    r'(?:,\s*"([^"]*)"\s*)?\)',
    re.S)
CREATE_TRAINER = re.compile(
    r'createTrainer\(\s*(\d+)\s*,\s*(?:"([^"]+)"|([^,]+?))\s*,\s*(\w+|\[[^\]]*\])', re.S)
# `party = party_gym3()` — the team lives in the GymTeams script instead.
GYM_PARTY = re.compile(r'(\w+)\s*=\s*(?:party|hard)_gym(\d+)\(\)')
ASSIGN_LOCAL = re.compile(r'^\s*(\w+)\s*=\s*createPokemon\(', re.M)
LIST_START = re.compile(r'(\w+)\s*=\s*\[')
ATTR = re.compile(
    r'(\w+)(?:\[(\d+)\])?\.(item|card|shinyflag|genderflag)\s*=\s*'
    r'(?:PBItems::)?(\w+)')
ABILITY = re.compile(r'(\w+)(?:\[(\d+)\])?\.setAbility\((\d+)\)')


def event_script_text(page):
    """All script + message text on one event page, in order."""
    parts = []
    for c in page.ivars["list"]:
        code = c.ivars["code"]
        params = c.ivars["parameters"]
        if not params:
            continue
        v = params[0]
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        if not isinstance(v, str):
            continue
        if code in SCRIPT_CODES:
            parts.append(("script", v))
        elif code in TEXT_CODES:
            parts.append(("text", v))
    return parts


def parse_moves(raw):
    if not raw or raw == "nil":
        return []
    return [m.upper() for m in re.findall(r":(\w+)", raw)]


def mon_from_match(cp):
    return {
        "species": cp.group(1), "level": int(cp.group(2)),
        "moves": parse_moves(cp.group(3)), "gender": cp.group(4) or None,
        "item": None, "card": None, "shiny": False, "abilityIndex": None,
    }


def parse_party(blob):
    """-> ({local name -> pokemon}, [pokemon in list order] per list variable)"""
    # `return [...]` is just an anonymous party; name it so the same code path
    # handles both styles.
    blob = re.sub(r"\breturn\s*\[", "__ret = [", blob)
    mons = {}
    order = {}

    # p1 = createPokemon(...)
    for m in re.finditer(r'(\w+)\s*=\s*createPokemon\(', blob):
        cp = CREATE_POKEMON.match(blob, m.end() - len("createPokemon("))
        if cp:
            mons[m.group(1)] = mon_from_match(cp)

    # party = [createPokemon(...), createPokemon(...)]  /  party = [p1, p2]
    # Movesets are themselves bracketed, so match brackets rather than
    # stopping at the first "]".
    for m in LIST_START.finditer(blob):
        varname = m.group(1)
        start = m.end()
        depth, i = 1, start
        while i < len(blob) and depth:
            if blob[i] == "[":
                depth += 1
            elif blob[i] == "]":
                depth -= 1
            i += 1
        if depth:
            continue
        body = blob[start:i - 1]
        if "createPokemon" not in body and not re.search(r"\b\w+\b", body):
            continue
        entries = []
        if "createPokemon" in body:
            for cp in CREATE_POKEMON.finditer(body):
                entries.append(mon_from_match(cp))
        else:
            for token in re.findall(r"\b([A-Za-z_]\w*)\b", body):
                if token in mons:
                    entries.append(mons[token])
        if entries:
            order[varname] = entries
    return mons, order


def apply_attrs(blob, mons, order):
    """Attach .item / .card / .shinyflag / setAbility to the right Pokémon."""
    for m in ATTR.finditer(blob):
        var, idx, attr, value = m.group(1), m.group(2), m.group(3), m.group(4)
        target = None
        if idx is not None and var in order:
            i = int(idx)
            if i < len(order[var]):
                target = order[var][i]
        elif var in mons:
            target = mons[var]
        if target is None:
            continue
        if attr == "item":
            # Several gym entries assign a *_CARD to .item; keep it as a card so
            # the page does not claim the Pokémon is holding a card as an item.
            if value.endswith("_CARD"):
                target["card"] = value
            else:
                target["item"] = value
        elif attr == "card":
            target["card"] = value
        elif attr == "shinyflag":
            target["shiny"] = value == "true"
        elif attr == "genderflag":
            target["gender"] = "male" if value == "0" else "female"

    for m in ABILITY.finditer(blob):
        var, idx, n = m.group(1), m.group(2), int(m.group(3))
        if idx is not None and var in order:
            i = int(idx)
            if i < len(order[var]):
                order[var][i]["abilityIndex"] = n
        elif var in mons:
            mons[var]["abilityIndex"] = n


def extract_from_blob(blob):
    """-> [{trainerTypeId, name, party, gym, dynamic}] per createTrainer call."""
    mons, order = parse_party(blob)
    apply_attrs(blob, mons, order)
    gym_vars = {m.group(1): int(m.group(2)) for m in GYM_PARTY.finditer(blob)}

    out = []
    for m in CREATE_TRAINER.finditer(blob):
        tid = int(m.group(1))
        name, dyn_name, partyvar = m.group(2), m.group(3), m.group(4)
        party = order.get(partyvar)
        if party is None and partyvar in mons:
            party = [mons[partyvar]]
        if party is None and partyvar.startswith("["):
            # createTrainer(121, "Vincent", [p1]) — party built inline
            party = [mons[t] for t in re.findall(r"\b([A-Za-z_]\w*)\b", partyvar)
                     if t in mons]
        gym = gym_vars.get(partyvar)
        if not party and gym is None:
            continue
        # A few battles pick the species or the trainer name from a game
        # variable (the rival mirrors your starter choice); record that rather
        # than pretending a fixed team.
        dynamic = bool(dyn_name) or any(
            not re.match(r"^[A-Z0-9_]+$", p["species"]) for p in (party or []))
        # A dynamic name is a Ruby expression (pbGet(100), $game_variables[...]),
        # not something to print; fall back to the trainer class alone.
        label = name
        if label is None:
            expr = (dyn_name or "").strip()
            label = "" if re.search(r"[(\[$.]|^pb", expr) else expr

        out.append({
            "trainerTypeId": tid,
            "name": label.strip(),
            "party": [dict(p) for p in (party or [])],
            "gym": gym,
            "dynamic": dynamic,
        })
    return out


def trainer_types(pbs_dir):
    """id -> display name, from trainertypes.txt."""
    out = {}
    for r in pbs.read_csv_rows(os.path.join(pbs_dir, "trainertypes.txt")):
        if len(r) < 3:
            continue
        try:
            out[int(r[0])] = r[2]
        except ValueError:
            continue
    return out


def gym_teams(scripts):
    """The eight authored gym parties, Normal and Extreme, from GymTeams."""
    src = scripts.get("GymTeams", "")
    gyms = {}
    for m in re.finditer(r"^def (hard|party)_gym(\d+)\(\)(.*?)^end", src, re.S | re.M):
        kind, num, body = m.group(1), int(m.group(2)), m.group(3)
        mons, order = parse_party(body)
        apply_attrs(body, mons, order)
        party = order.get("party") or order.get("__ret")
        if not party:
            continue
        g = gyms.setdefault(num, {"gym": num, "normal": [], "extreme": []})
        g["extreme" if kind == "hard" else "normal"] = [dict(p) for p in party]
    return [gyms[k] for k in sorted(gyms)]


def gym_leaders(scripts):
    """gym number -> (leader name, trainer type id).

    Gyms 1-3 are fought straight from their map event, but 4-8 go through a
    helper in SpecialFights / Other Stuff (aerisGymBattle, iceGymBattle, ...)
    that calls party_gymN() and passes the leader's name to simpleBattle.
    """
    out = {}
    for src in scripts.values():
        for m in re.finditer(r"^def (\w+)\(.*?\n(.*?)^end", src, re.S | re.M):
            fn, body = m.group(1), m.group(2)
            if fn.startswith(("party_gym", "hard_gym")):
                continue
            g = re.search(r"(?:party|hard)_gym(\d+)\(\)", body)
            if not g:
                continue
            nm = re.search(
                r'simpleBattle\([^,]*,\s*\w+\s*,\s*(\d+)\s*,\s*"([^"]*)"', body)
            if not nm:
                nm = re.search(r'createTrainer\(\s*(\d+)\s*,\s*"([^"]+)"', body)
            if nm:
                out.setdefault(int(g.group(1)), (nm.group(2), int(nm.group(1))))
    return out


def scan_maps(root, map_names):
    """Every trainer battle defined in a map event."""
    results = []
    for f in sorted(glob.glob(os.path.join(root, "Data", "Map[0-9]*.rxdata"))):
        mid = int(re.search(r"Map(\d+)", os.path.basename(f)).group(1))
        try:
            m = marshal48.load(f)
        except Exception:
            continue
        for _, e in m.ivars["events"].items():
            ename = e.ivars["name"]
            ename = ename.decode("utf-8", "replace") if isinstance(ename, bytes) else str(ename)
            for pi, page in enumerate(e.ivars["pages"]):
                parts = event_script_text(page)
                blob = "\n".join(v for kind, v in parts if kind == "script")
                if "createTrainer" not in blob:
                    continue
                for t in extract_from_blob(blob):
                    t.update({"mapId": mid, "mapName": map_names.get(mid),
                              "event": ename, "page": pi})
                    results.append(t)
    return results


def badge_events(root, map_names):
    """Where each of the eight badges is awarded, with its reward."""
    out = {}
    for f in sorted(glob.glob(os.path.join(root, "Data", "Map[0-9]*.rxdata"))):
        mid = int(re.search(r"Map(\d+)", os.path.basename(f)).group(1))
        try:
            m = marshal48.load(f)
        except Exception:
            continue
        for _, e in m.ivars["events"].items():
            for page in e.ivars["pages"]:
                parts = event_script_text(page)
                blob = "\n".join(v for _, v in parts)
                bm = re.search(r"\$Trainer\.badges\[(\d+)\]\s*=\s*true", blob)
                if not bm:
                    continue
                idx = int(bm.group(1))
                if idx in out:
                    continue
                badge = re.search(r"received the ([A-Z][A-Za-z ]*) BADGE", blob)
                tm = re.search(r"pbReceiveItem\(PBItems::(\w+)\)", blob)
                cap = re.search(r"BADGELEVEL\[(\d+)\]", blob)
                leader = re.search(r'createTrainer\(\s*\d+\s*,\s*"([^"]+)"', blob)
                out[idx] = {
                    "index": idx, "badge": badge.group(1).title() if badge else None,
                    "mapId": mid, "mapName": map_names.get(mid),
                    "reward": tm.group(1) if tm else None,
                    "levelCapIndex": int(cap.group(1)) if cap else None,
                    "leader": leader.group(1) if leader else None,
                }
    return [out[k] for k in sorted(out)]
