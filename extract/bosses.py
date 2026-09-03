"""Named boss and story battles, from the fight scripts.

SpecialFights, CitadelBosses, SpecFights3030 and the tower scripts each hold
one function per set-piece battle, built exactly like the gym teams:

    def generalBoltBattle()
      party = [createPokemon("LUXRAY", 120, [...]), ...]
      party[0].item = PBItems::AIRBALLOON
      trainer = createTrainer(222, "Bolt", party)
      result = customTrainerBattle(trainer, "... as expected.")
    end

The game never states a story order, so the list is ordered by the level of the
boss's team, which is what a player actually progresses through. Functions no
map ever calls are development leftovers and are dropped.
"""
import glob
import os
import re

import marshal48
import trainers

# Scripts that hold set-piece battles. Gym parties live in GymTeams and are
# already covered by the gyms page, so that one is deliberately absent.
FIGHT_SCRIPTS = ("SpecialFights", "CitadelBosses", "SpecFights3030",
                 "ZTower", "PrismTower", "TrainerTower", "League", "League v2")

SIMPLE_BATTLE = re.compile(
    r'simpleBattle\(\s*([^,]*),\s*(\w+)\s*,\s*(\d+)\s*,\s*"([^"]*)"'
    r'(?:\s*,\s*"([^"]*)")?')
CUSTOM_BATTLE = re.compile(r'customTrainerBattle\(\s*\w+\s*(?:,\s*"([^"]*)")?')
PARTNER = re.compile(r'pbRegisterPartner\(\s*PBTrainers::(\w+)\s*,\s*"([^"]+)"')
INTL = re.compile(r'_INTL\("([^"]+)"\)')

# The Z Tower ladder fields low-level teams but is endgame content, so sorting
# purely by level puts it at the wrong end. The data carries no story order, so
# this is an authored correction.
ENDGAME = ("wild:BEELUS", "betaArceusFight", "zineomBeachFight",
           "zineomBeastFight", "zineomFakeFinalFight", "zineomFinalFight")

# Damon is a gym leader, covered on the gyms page; his story fight is not a
# separate boss.
EXCLUDE = ("damonFakeFight",)

# Internal names that title-case into something awkward. RAYQYOMI_2 is the
# second phase of the same fight and is run as a trainer, so only one Rayqyomi
# reaches this list and the "1" is noise.
TITLE_OVERRIDES = {"wild:RAYQYOMI_1": "Rayqyomi"}

# Where the level sort puts something in the wrong narrative slot.
ORDER_AFTER = (("wild:RAYQYOMI_EGG", "wild:DREAM_MACHINE"),
               ("wild:RAYQYOMI_1", "wild:RAYQYOMI_EGG"))


def _functions(scripts):
    """Yield (script, function name, body) for every battle-shaped function."""
    for name in FIGHT_SCRIPTS:
        src = scripts.get(name, "")
        for m in re.finditer(r"^def (\w+)\(.*?\n(.*?)^end", src, re.S | re.M):
            body = m.group(2)
            if "createPokemon" in body:
                yield name, m.group(1), body


def _party_from(body):
    """-> (party, display name, trainer type id, closing line, partner)"""
    got = trainers.extract_from_blob(body)
    mons, order = trainers.parse_party(body)
    trainers.apply_attrs(body, mons, order)

    party, label, tid = None, "", None
    if got:
        party, label, tid = got[0]["party"], got[0]["name"], got[0]["trainerTypeId"]
        quote = CUSTOM_BATTLE.search(body)
        quote = quote.group(1) if quote else None
    else:
        sb = SIMPLE_BATTLE.search(body)
        if not sb:
            return None, "", None, None, None
        party = order.get(sb.group(2))
        if party is None and sb.group(2) in mons:
            party = [mons[sb.group(2)]]
        label, tid, quote = sb.group(4), int(sb.group(3)), sb.group(5)

    p = PARTNER.search(body)
    return party, label, tid, quote, (p.group(2) if p else None)


CREATE_MON = re.compile(r'createPokemon\(\s*"([A-Z0-9_]+)"\s*,\s*(\d+)')


def scan_wild(root, map_names, special_species, titlecase):
    """Boss Pokemon fought directly, not through a trainer.

    Mutant Pikachu, the Rapidash pair, Kirlia and the fusion soldiers are wild
    battles set up in a map event:

        poke = createPokemon("MUTANT_PIKACHU", 5)
        result = twoAgainstOneBattle(poke, false)

    A page is read in order rather than as a whole, because one page can do
    both: the Rayqyomi fight runs phase one through simpleBattle and phase two
    through createTrainer, so testing the whole page for "createTrainer" would
    throw away a real boss encounter.
    """
    found = {}
    for f in sorted(glob.glob(os.path.join(root, "Data", "Map[0-9]*.rxdata"))):
        mid = int(re.search(r"Map(\d+)", os.path.basename(f)).group(1))
        name = map_names.get(mid) or ""
        if "test" in name.lower():
            continue  # developer room
        try:
            m = marshal48.load(f)
        except Exception:
            continue
        for _, e in m.ivars["events"].items():
            for page in e.ivars["pages"]:
                text = "\n".join(v for kind, v in trainers.event_script_text(page)
                                 if kind == "script")
                if "createPokemon" not in text:
                    continue
                # Pokemon built since the last battle call belong to whichever
                # call comes next: a solo battle makes them a boss encounter, a
                # trainer call means they are somebody's party and are covered
                # as a trainer battle instead.
                pending = []
                for line in text.split("\n"):
                    for sps, lvl in CREATE_MON.findall(line):
                        if sps in special_species:
                            pending.append((sps, int(lvl)))
                    solo = re.search(r"\b(simpleBattle|twoAgainstOneBattle|"
                                     r"simpleDoubleBattle)\s*\(", line)
                    if solo:
                        for sps, lvl in pending:
                            rec = found.setdefault(sps, {
                                "species": sps, "encounters": [],
                                "helper": solo.group(1),
                            })
                            spot = {"mapId": mid, "mapName": name, "level": lvl}
                            if spot not in rec["encounters"]:
                                rec["encounters"].append(spot)
                        pending = []
                    elif re.search(r"\b(createTrainer|customTrainerBattle)\s*\(", line):
                        pending = []

    out = []
    for sps, rec in found.items():
        spots = sorted(rec["encounters"], key=lambda s: (s["level"], s["mapId"]))
        levels = [s["level"] for s in spots]
        out.append({
            "battleKind": "wild",
            "id": "wild:%s" % sps,
            "species": sps,
            "title": titlecase(sps),
            "encounters": spots,
            # More than a couple of places means a recurring enemy rather than
            # a one-off boss: the fusion soldiers turn up on every Citadel floor.
            "recurring": len(spots) > 2,
            "minLevel": min(levels), "maxLevel": max(levels),
            "partySize": 1,
            "helper": rec["helper"],
        })
    return out


def scan(root, scripts, map_names, map_regions, region_names, slugify,
         trainer_types, locations, wild=None):
    """-> [{...}] one entry per boss battle, in ascending team level."""
    found = {}
    for script, fn, body in _functions(scripts):
        party, label, tid, quote, partner = _party_from(body)
        if not party:
            continue
        found[fn] = {
            "id": fn, "script": script, "name": label.strip(),
            "trainerTypeId": tid, "party": party, "partner": partner,
            "quote": quote,
            "partySize": len(party),
            "maxLevel": max((p["level"] for p in party), default=0),
        }

    # Which map calls each one. A battle nothing calls is dev leftovers.
    called = {}
    for f in sorted(glob.glob(os.path.join(root, "Data", "Map[0-9]*.rxdata"))):
        mid = int(re.search(r"Map(\d+)", os.path.basename(f)).group(1))
        try:
            m = marshal48.load(f)
        except Exception:
            continue
        for _, e in m.ivars["events"].items():
            for page in e.ivars["pages"]:
                text = "\n".join(v for kind, v in trainers.event_script_text(page)
                                 if kind == "script")
                if not text:
                    continue
                for fn in found:
                    if re.search(r"\b%s\b" % re.escape(fn), text):
                        called.setdefault(fn, []).append(mid)

    slug_by_map = {}
    for l in locations:
        slug_by_map.setdefault(l["mapId"], l["slug"])

    out = []
    for fn, d in found.items():
        maps = called.get(fn)
        if not maps:
            continue  # never reachable in game
        # Prefer a real location over the developer Test Room.
        maps = sorted(set(maps),
                      key=lambda m: ("test" in (map_names.get(m) or "").lower(), m))
        mid = maps[0]
        reg = map_regions.get(mid, (None,))[0]
        d.update({
            "mapId": mid,
            "mapName": map_names.get(mid),
            "locationSlug": slug_by_map.get(mid),
            "regionName": region_names.get(reg) if reg is not None else None,
            "trainerType": trainer_types.get(d["trainerTypeId"]) if d["trainerTypeId"] else None,
        })
        # Several bosses are deliberately called "???" in game, and one takes
        # its name from a variable. Keep whatever the game shows as `name`, but
        # give the entry a readable title so a list of them is navigable.
        d["title"] = d["name"]
        if not d["name"] or not re.search(r"[A-Za-z]", d["name"]):
            derived = re.sub(r"(Fight|Battle)$", "", fn)
            derived = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)", " ", derived)
            d["title"] = derived[:1].upper() + derived[1:]
        out.append(d)

    for b in out:
        b["battleKind"] = "trainer"
        b["recurring"] = False
        b["minLevel"] = min((p["level"] for p in b["party"]), default=b["maxLevel"])
    out.extend(wild or [])

    # Team level is the progression signal the data carries, with the Z Tower
    # ladder forced last regardless of its levels.
    out = [b for b in out if b["id"] not in EXCLUDE]
    endgame_rank = {bid: i for i, bid in enumerate(ENDGAME)}
    out.sort(key=lambda b: (b["id"] in endgame_rank,
                            endgame_rank.get(b["id"], 0),
                            b["maxLevel"], b["title"]))

    # Move a battle to sit directly after another, where the level ordering
    # lands it somewhere the story does not.
    by_id = {b["id"]: b for b in out}
    for target, anchor in ORDER_AFTER:
        if target in by_id and anchor in by_id:
            b = by_id[target]
            out.remove(b)
            out.insert(out.index(by_id[anchor]) + 1, b)

    # Several characters are fought more than once (Moira three times, Blitz
    # four). Say where, so the list reads as a sequence of encounters rather
    # than a name repeated.
    counts = {}
    for b in out:
        counts[b["title"]] = counts.get(b["title"], 0) + 1
    for b in out:
        if counts[b["title"]] > 1 and b.get("mapName"):
            b["title"] = "%s (%s)" % (b["title"], b["mapName"])

    slug_by_map2 = slug_by_map
    for b in out:
        if b["battleKind"] != "wild":
            continue
        b["title"] = TITLE_OVERRIDES.get(b["id"], b["title"])
        first = b["encounters"][0]
        b["mapId"] = first["mapId"]
        b["mapName"] = first["mapName"]
        b["locationSlug"] = slug_by_map2.get(first["mapId"])
        reg = map_regions.get(first["mapId"], (None,))[0]
        b["regionName"] = region_names.get(reg) if reg is not None else None
        for spot in b["encounters"]:
            spot["slug"] = slug_by_map2.get(spot["mapId"])

    used = {}
    for i, b in enumerate(out, 1):
        b["order"] = i
        base = slugify(b["title"]) or "boss"
        slug, n = base, 2
        while slug in used:
            slug = "%s-%d" % (base, n)
            n += 1
        used[slug] = True
        b["slug"] = slug
    return out
