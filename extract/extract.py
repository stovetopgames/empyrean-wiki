#!/usr/bin/env python
"""Extract Pokemon Empyrean game data into canonical JSON.

Reads the game's PBS text files plus Graphics/ and writes one JSON file per
entity type into wiki/data/. Everything downstream (static site, MediaWiki
export) renders from these files, so this is the single source of truth.
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbs
import locations as locations_mod
import trainers as trainers_mod
import townmap as townmap_mod
import pickups as pickups_mod
import forms as forms_mod
import bosses as bosses_mod

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PBS_DIR = os.path.join(ROOT, "PBS")
GFX = os.path.join(ROOT, "Graphics")
OUT = os.path.join(ROOT, "wiki", "data")

GENDER_RATES = {
    "AlwaysMale": (100.0, 0.0), "FemaleOneEighth": (87.5, 12.5),
    "Female25Percent": (75.0, 25.0), "Female50Percent": (50.0, 50.0),
    "Female75Percent": (25.0, 75.0), "FemaleSevenEighths": (12.5, 87.5),
    "AlwaysFemale": (0.0, 100.0), "Genderless": (None, None),
}
GROWTH_RATES = {
    "Medium": "Medium Fast", "Parabolic": "Medium Slow", "Erratic": "Erratic",
    "Fluctuating": "Fluctuating", "Fast": "Fast", "Slow": "Slow",
}
POCKETS = {
    1: "Items", 2: "Medicine", 3: "Poke Balls", 4: "TMs & HMs", 5: "Clothing",
    6: "Alterants", 7: "Cards & X-Items", 8: "Key Items",
}
# Essentials move target codes -> readable text
TARGETS = {
    "00": "Selected foe", "01": "No target", "02": "Random foe", "04": "All foes",
    "08": "All others", "10": "User", "20": "Both sides", "40": "Opposing side",
    "0C": "All foes and allies", "80": "Foe side", "100": "Ally",
    "200": "User or ally", "400": "Random ally",
}

ITEM_NAMES = {}
MOVE_NAMES = {}
SPECIES_NAMES = {}

# Empyrean reuses the vanilla Name= for its variants (OM_ZUBAT is still called
# "Zubat"), so 79 species share a display name. These prefixes disambiguate them.
# OM_/DR_/DATA_ are regional variants named after the game's own regions; the
# rest are one-off event or boss forms.
VARIANT_LABELS = {
    "OM": "Omuran", "DR": "Deshret", "DATA": "Data", "B": "Boss",
    "BOSS": "Boss", "MUTANT": "Mutant", "SAND": "Sand", "SUN": "Sun",
    "SWOL": "Swol", "MECH": "Mech", "GOLD": "Golden", "GOLDEN": "Golden",
    "ARMORED": "Armored", "CHIMERA": "Chimera", "DREAM": "Dream",
    "CYBORG": "Cyborg", "ALT": "Alt", "CLOCK": "Clock", "RAINBOW": "Rainbow",
    "FUNNY": "Funny", "GR": "GR", "BAKUHATSU": "Bakuhatsu", "NINA": "Nina",
    "BETA": "Beta", "Z": "Z", "ZINEOM": "Zineom", "ARCH": "Arch",
    "XATU": "Xatu", "TOTALLY": "Totally", "BANDIT": "Bandit", "DARK": "Dark",
    "RAYQYOMI": "Rayqyomi", "BRAIXEN": "Braixen", "ELECTIVIRE": "Electivire",
}


# Which abilities and items are Empyrean's own rather than stock Essentials.
#
# The author kept new content in reserved id ranges, which makes this readable
# straight off the data rather than guesswork:
#   abilities.txt runs 1-232 (the official Gen 7 set) then jumps to 300+
#   items.txt keeps the stock list in 1-525, the Gen 7 additions in 700-706 and
#   the Mega Stones in 726-766; everything else is new.
# A handful of stock items are merely renamed (STARDUST is "Red Stardust",
# COINCASE is "Token Pouch"); those keep their official id, so they stay out of
# the exclusive list, which is the right call - the item itself is not new.
OFFICIAL_ABILITY_MAX = 232
OFFICIAL_ITEM_RANGES = [(1, 525), (700, 706), (726, 766)]
# The one new item sitting inside an official range.
ITEM_EXCLUSIVE_OVERRIDES = {"MIZU_SHURIKEN"}


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "unnamed"


def is_exclusive_ability(a):
    return a["id"] > OFFICIAL_ABILITY_MAX


def is_exclusive_item(i):
    if i["internal"] in ITEM_EXCLUSIVE_OVERRIDES:
        return True
    return not any(lo <= i["id"] <= hi for lo, hi in OFFICIAL_ITEM_RANGES)


def assign_unique_names(records):
    """Add displayName + slug to records, disambiguating repeated names.

    Several moves and a lot of clothing items share a name across two internal
    entries; a wiki page title and a URL both have to be unique, so the later
    ones are qualified with their internal name.
    """
    squash = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    groups = defaultdict(list)
    for r in records:
        groups[r["name"]].append(r)

    # Decide per group of same-named entries. If the internal names differ from
    # the display name only by a numeric suffix ("TIDALWAVE" / "TIDAL_WAVE"),
    # they carry no information, so number the group instead. If they carry a
    # real distinction ("DEFAULTHAT_M" / "DEFAULTHAT_F"), keep it.
    numbered = set()
    for name, group in groups.items():
        if len(group) < 2:
            continue
        stem = squash(name)
        informative = False
        for r in group:
            rest = squash(r["internal"])
            rest = rest[len(stem):] if rest.startswith(stem) else rest
            if rest and not rest.isdigit():
                informative = True
                break
        if not informative:
            numbered.add(name)

    used = {}
    ordinal = defaultdict(int)
    for r in records:
        name = r["name"]
        if len(groups[name]) > 1:
            if name in numbered:
                ordinal[name] += 1
                qualifier = str(ordinal[name])
            else:
                qualifier = pbs.titlecase_name(r["internal"])
                # "Default Hat (Default Hat M)" -> "Default Hat (M)"
                if qualifier.lower().startswith(name.lower()):
                    qualifier = qualifier[len(name):].strip() or qualifier
            name = "%s (%s)" % (r["name"], qualifier)
        r["displayName"] = name
        base = slugify(name)
        s, n = base, 2
        while s in used:
            s = "%s-%d" % (base, n)
            n += 1
        used[s] = r["internal"]
        r["slug"] = s
    # A qualified name can still collide; make the final pass authoritative.
    seen = defaultdict(list)
    for r in records:
        seen[r["displayName"]].append(r)
    for name, group in seen.items():
        if len(group) > 1:
            for r in group:
                r["displayName"] = "%s [%s]" % (name, r["internal"])


def pretty(internal):
    if not internal:
        return ""
    return (ITEM_NAMES.get(internal) or MOVE_NAMES.get(internal)
            or SPECIES_NAMES.get(internal) or pbs.titlecase_name(internal))


def evolution_text(method, param, species_name):
    m, p = method, param
    simple = {
        "Level": "Level %s", "LevelNight": "Level %s at night",
        "LevelDay": "Level %s during the day", "LevelRain": "Level %s while raining",
        "LevelMale": "Level %s (male)", "LevelFemale": "Level %s (female)",
        "LevelDarkInParty": "Level %s with a Dark-type in the party",
        "AttackGreater": "Level %s with Attack greater than Defense",
        "DefenseGreater": "Level %s with Defense greater than Attack",
        "AtkDefEqual": "Level %s with Attack equal to Defense",
        "Ninjask": "Level %s",
        "Shedinja": "Level %s with a spare Poke Ball and party slot",
    }
    if m in simple:
        return simple[m] % p
    if m in ("Silcoon", "Cascoon"):
        return "Level %s (random, %s branch)" % (p, m)
    items = {
        "Item": "Use %s", "ItemMale": "Use %s (male)", "ItemFemale": "Use %s (female)",
        "DayHoldItem": "Level up holding %s during the day",
        "NightHoldItem": "Level up holding %s at night",
        "HoldItem": "Level up holding %s", "TradeItem": "Trade holding %s",
        "HasMove": "Level up knowing %s", "HasInParty": "Level up with %s in the party",
    }
    if m in items:
        return items[m] % pretty(p)
    happiness = {
        "Happiness": "Level up with high friendship",
        "HappinessDay": "Level up with high friendship during the day",
        "HappinessNight": "Level up with high friendship at night",
    }
    if m in happiness:
        return happiness[m]
    if m == "HappinessMoveType":
        return "Level up with high friendship while knowing a %s-type move" % str(p).title()
    if m == "Beauty":
        return "Level up with at least %s Beauty" % p
    if m == "Trade":
        return "Trade"
    if m and m.startswith("Custom"):
        return "Special method (%s) - see the notes on this page" % m
    return ("%s %s" % (m, p)).strip()


# ---------------------------------------------------------------- types
def extract_types():
    types = []
    for sec, f in pbs.read_sections(os.path.join(PBS_DIR, "types.txt")):
        types.append({
            "id": int(sec),
            "name": f.get("Name", ""),
            "internal": f.get("InternalName", ""),
            "isPseudoType": f.get("IsPseudoType", "").lower() == "true",
            "isSpecialType": f.get("IsSpecialType", "").lower() == "true",
            "weaknesses": [x for x in f.get("Weaknesses", "").split(",") if x],
            "resistances": [x for x in f.get("Resistances", "").split(",") if x],
            "immunities": [x for x in f.get("Immunities", "").split(",") if x],
        })
    # A defending type lists, in its own Weaknesses, the attacking types that hit it 2x.
    #
    # Precedence must match Compiler#pbCompileTypes, which assigns in this order,
    # each overwriting the last: default 1x -> weakness 2x -> resistance 0.5x ->
    # immunity 0x. So a type listed under BOTH Weaknesses and Resistances resolves
    # to 0.5x in-game, not 2x. types.txt does this in a handful of places.
    chart = {}
    conflicts = []
    for atk in types:
        chart[atk["internal"]] = {}
        for dfn in types:
            mult = 1.0
            if atk["internal"] in dfn["weaknesses"]:
                mult = 2.0
            if atk["internal"] in dfn["resistances"]:
                if mult == 2.0:
                    conflicts.append((atk["internal"], dfn["internal"]))
                mult = 0.5
            if atk["internal"] in dfn["immunities"]:
                mult = 0.0
            chart[atk["internal"]][dfn["internal"]] = mult
    if conflicts:
        print("  note: %d matchup(s) listed as both weakness and resistance; "
              "resolved to 0.5x as the game does:" % len(conflicts))
        for a, d in conflicts:
            print("        %s attacking %s" % (a, d))
    return {"types": types, "chart": chart}


# ---------------------------------------------------------------- abilities
def extract_abilities():
    out = []
    for r in pbs.read_csv_rows(os.path.join(PBS_DIR, "abilities.txt")):
        if len(r) < 4:
            continue
        out.append({"id": int(r[0]), "internal": r[1], "name": r[2], "description": r[3]})
    return out


# ---------------------------------------------------------------- moves
def extract_moves():
    out = []
    seen = set()
    for r in pbs.read_csv_rows(os.path.join(PBS_DIR, "moves.txt")):
        if len(r) < 14:
            r = r + [""] * (14 - len(r))
        try:
            mid = int(r[0])
        except ValueError:
            continue
        # moves.txt repeats the LEAFAGE row verbatim; the game keeps one, so do we.
        if (mid, r[1]) in seen:
            print("  note: skipping duplicate row for %s (id %d)" % (r[1], mid))
            continue
        seen.add((mid, r[1]))
        flags = r[12] or ""
        out.append({
            "id": mid, "internal": r[1], "name": r[2], "functionCode": r[3],
            "power": int(r[4] or 0), "type": r[5], "category": r[6],
            "accuracy": int(r[7] or 0), "pp": int(r[8] or 0),
            "effectChance": int(r[9] or 0), "target": r[10],
            "targetText": TARGETS.get(r[10], r[10]), "priority": int(r[11] or 0),
            "flags": flags,
            "makesContact": "a" in flags, "protectable": "b" in flags,
            "magicCoatable": "c" in flags, "snatchable": "d" in flags,
            "mirrorMoveable": "e" in flags, "kingsRockable": "f" in flags,
            "thawsUser": "g" in flags, "highCritRate": "h" in flags,
            "biteMove": "i" in flags, "punchingMove": "j" in flags,
            "soundMove": "k" in flags, "powderMove": "l" in flags,
            "pulseMove": "m" in flags, "bombMove": "n" in flags,
            "description": r[13],
        })
    return out


# ---------------------------------------------------------------- items
def extract_items():
    # Only ~900 of the items ship an icon; record which so the renderers can
    # skip the <img> entirely instead of emitting a broken reference.
    icon_dir = os.path.join(GFX, "Icons")
    have_icon = set(os.listdir(icon_dir)) if os.path.isdir(icon_dir) else set()
    items, cards = [], {}
    for r in pbs.read_csv_rows(os.path.join(PBS_DIR, "items.txt")):
        if len(r) < 11:
            r = r + [""] * (11 - len(r))
        try:
            iid = int(r[0])
        except ValueError:
            continue
        pocket = int(r[4] or 0)
        it = {
            "id": iid, "internal": r[1], "name": r[2], "plural": r[3],
            "pocket": pocket, "pocketName": POCKETS.get(pocket, "Unknown"),
            "price": int(r[5] or 0), "description": r[6],
            "fieldUse": int(r[7] or 0), "battleUse": int(r[8] or 0),
            "specialItem": int(r[9] or 0), "machine": r[10] or None,
        }
        it["isCard"] = it["internal"].endswith("_CARD")
        it["isMachine"] = bool(it["machine"])
        it["hasIcon"] = ("item%03d.png" % iid) in have_icon
        items.append(it)
        if it["isCard"]:
            cards[it["internal"][:-5]] = it["internal"]
    return items, cards


# ---------------------------------------------------------------- tm / tutor
def extract_machine_compat():
    """move internal -> {'species': [...], 'headings': [...]}"""
    out = {}
    for move, entries, heading in pbs.read_list_sections(os.path.join(PBS_DIR, "tm.txt")):
        rec = out.setdefault(move, {"species": [], "headings": []})
        rec["species"].extend(entries)
        if heading and heading not in rec["headings"]:
            rec["headings"].append(heading)
    for rec in out.values():
        rec["species"] = sorted(set(rec["species"]))
    return out


# ---------------------------------------------------------------- sprites
def sprite_index():
    return set(os.listdir(os.path.join(GFX, "Battlers"))), set(os.listdir(os.path.join(GFX, "Icons")))


def sprites_for(num, form, battlers, icons):
    base = "%03d" % num
    sfx = "_%d" % form if form else ""

    def b(n):
        return "Battlers/" + n if n in battlers else None

    def i(n):
        return "Icons/" + n if n in icons else None

    return {
        "front": b(base + sfx + ".png"),
        "back": b(base + "b" + sfx + ".png"),
        "shinyFront": b(base + "s" + sfx + ".png"),
        "shinyBack": b(base + "sb" + sfx + ".png"),
        "femaleFront": b(base + "f" + sfx + ".png"),
        "shinyFemaleFront": b(base + "fs" + sfx + ".png"),
        "icon": i("icon" + base + sfx + ".png"),
        "shinyIcon": i("icon" + base + "s" + sfx + ".png"),
    }


def parse_level_moves(raw):
    out = []
    mv = [x.strip() for x in raw.split(",") if x.strip()]
    for lvl, mov in zip(mv[0::2], mv[1::2]):
        try:
            out.append({"level": int(lvl), "move": mov})
        except ValueError:
            continue
    return out


def parse_evolutions(raw):
    out = []
    ev = [x.strip() for x in raw.split(",")]
    for k in range(0, len(ev) - 2, 3):
        if ev[k]:
            out.append({"to": ev[k], "method": ev[k + 1], "param": ev[k + 2]})
    return out


# ---------------------------------------------------------------- species
def extract_species(machine_compat, cards, battlers, icons, scripts):
    species, by_internal = [], {}

    for sec, f in pbs.read_sections(os.path.join(PBS_DIR, "pokemon.txt")):
        num = int(sec)
        internal = f.get("InternalName", "")
        stats = pbs.split_ints(f.get("BaseStats", "0,0,0,0,0,0"))
        evs = pbs.split_ints(f.get("EffortPoints", "0,0,0,0,0,0"))
        gr = f.get("GenderRate", "Female50Percent")
        male, female = GENDER_RATES.get(gr, (None, None))

        s = {
            "number": num, "internal": internal, "name": f.get("Name", internal),
            "formNumber": 0, "formName": None, "baseSpecies": internal,
            "types": [t for t in (f.get("Type1"), f.get("Type2")) if t],
            "baseStats": dict(zip(pbs.STAT_ORDER, stats + [0] * 6)),
            "baseStatTotal": sum(stats),
            "effortPoints": dict(zip(pbs.STAT_ORDER, evs + [0] * 6)),
            "genderRate": gr, "malePercent": male, "femalePercent": female,
            "growthRate": GROWTH_RATES.get(f.get("GrowthRate", ""), f.get("GrowthRate", "")),
            "baseEXP": int(f.get("BaseEXP", 0) or 0),
            "catchRate": int(f.get("Rareness", 0) or 0),
            "baseHappiness": int(f.get("Happiness", 0) or 0),
            "abilities": [a for a in f.get("Abilities", "").split(",") if a],
            "hiddenAbility": f.get("HiddenAbility") or None,
            "eggGroups": [g for g in f.get("Compatibility", "").split(",") if g],
            "stepsToHatch": int(f.get("StepsToHatch", 0) or 0),
            "height": float(f.get("Height", 0) or 0),
            "weight": float(f.get("Weight", 0) or 0),
            "color": f.get("Color"), "habitat": f.get("Habitat"),
            "kind": f.get("Kind"), "pokedex": f.get("Pokedex", ""),
            "regionalNumbers": pbs.split_ints(f.get("RegionalNumbers", "")),
            "wildItems": [x for x in (f.get("WildItemCommon"), f.get("WildItemUncommon"),
                                      f.get("WildItemRare")) if x],
            "levelMoves": parse_level_moves(f.get("Moves", "")),
            "eggMoves": [m for m in f.get("EggMoves", "").split(",") if m],
            "evolutions": parse_evolutions(f.get("Evolutions", "")),
            "preEvolutions": [],
            "card": cards.get(internal),
            "sprites": sprites_for(num, 0, battlers, icons),
        }
        species.append(s)
        by_internal[internal] = s
        SPECIES_NAMES[internal] = s["name"]

    # ---- forms inherit from, then override, their base species
    forms = []
    for sec, f in pbs.read_sections(os.path.join(PBS_DIR, "pokemonforms.txt")):
        m = re.match(r"^(.+)-(\d+)$", sec)
        if not m:
            continue
        base_internal, formno = m.group(1), int(m.group(2))
        base = by_internal.get(base_internal)
        if not base:
            continue
        s = json.loads(json.dumps(base))
        s.update({
            "formNumber": formno, "baseSpecies": base_internal,
            "internal": "%s_%d" % (base_internal, formno),
            "formName": f.get("FormName"),
        })
        if f.get("FormName"):
            fn = f["FormName"]
            # "Mega Mewtwo X" already names the species; don't say it twice.
            s["name"] = fn if base["name"].lower() in fn.lower() else "%s (%s)" % (base["name"], fn)
        if f.get("Type1"):
            s["types"] = [t for t in (f.get("Type1"), f.get("Type2")) if t]
        if f.get("BaseStats"):
            st = pbs.split_ints(f["BaseStats"])
            s["baseStats"] = dict(zip(pbs.STAT_ORDER, st))
            s["baseStatTotal"] = sum(st)
        if f.get("Abilities"):
            s["abilities"] = [x for x in f["Abilities"].split(",") if x]
        if f.get("Compatibility"):
            s["eggGroups"] = [x for x in f["Compatibility"].split(",") if x]
        if f.get("HiddenAbility"):
            s["hiddenAbility"] = f["HiddenAbility"]
        for key, fld, cast in (("Height", "height", float), ("Weight", "weight", float),
                               ("BaseEXP", "baseEXP", int), ("Rareness", "catchRate", int)):
            if f.get(key):
                s[fld] = cast(f[key])
        if f.get("Kind"):
            s["kind"] = f["Kind"]
        if f.get("Pokedex"):
            s["pokedex"] = f["Pokedex"]
        if f.get("Moves"):
            s["levelMoves"] = parse_level_moves(f["Moves"])
        if f.get("Evolutions"):
            s["evolutions"] = parse_evolutions(f["Evolutions"])
        s["sprites"] = sprites_for(base["number"], formno, battlers, icons)
        forms.append(s)

    all_species = species + forms

    # ---- TM / tutor learnsets, inverted out of tm.txt
    taught = defaultdict(list)
    for move, rec in machine_compat.items():
        for sp in rec["species"]:
            taught[sp].append(move)
    for s in all_species:
        got = list(taught.get(s["internal"], []))
        if s["formNumber"]:
            got.extend(taught.get(s["baseSpecies"], []))
        s["machineMoves"] = sorted(set(got))

    # ---- back-links: pre-evolutions and readable evolution text
    for s in all_species:
        for e in s["evolutions"]:
            e["text"] = evolution_text(e["method"], e["param"], s["name"])
            tgt = by_internal.get(e["to"])
            if tgt is not None:
                tgt["preEvolutions"].append({
                    "from": s["internal"], "method": e["method"],
                    "param": e["param"], "text": e["text"],
                })

    # ---- family root, for rendering full evolution lines
    for s in all_species:
        root, seen = s["internal"], set()
        while True:
            node = by_internal.get(root)
            if not node or not node["preEvolutions"] or root in seen:
                break
            seen.add(root)
            root = node["preEvolutions"][0]["from"]
        s["familyRoot"] = root

    apply_script_forms(all_species, by_internal, scripts, battlers, icons, cards)
    flag_special_species(all_species, scripts)
    assign_display_names(all_species)
    resolve_sprites(all_species, by_internal)
    return all_species


def apply_script_forms(all_species, by_internal, scripts, battlers, icons, cards):
    """Overlay the form data declared in Ruby onto the PBS forms.

    Most Megas set their stats, ability and typing in MultipleForms.register
    rather than in pokemonforms.txt, and 28 forms exist *only* there. Without
    this the wiki shows the base species' stats for a Mega and reports its
    ability as unused - which is exactly what players reported.
    """
    script_forms = forms_mod.parse(scripts)
    created = enriched = 0
    # by_internal only holds base species; index the PBS forms too, or every
    # form here looks new and gets duplicated.
    for s in all_species:
        by_internal.setdefault(s["internal"], s)

    for species, formdata in sorted(script_forms.items()):
        base = by_internal.get(species)
        if base is None:
            continue
        for formno, ov in sorted(formdata.items()):
            key = "%s_%d" % (species, formno)
            entry = by_internal.get(key)

            if entry is None:
                # A form the PBS files never mention: build it off the base.
                entry = json.loads(json.dumps(base))
                entry.update({
                    "internal": key, "formNumber": formno,
                    "baseSpecies": species, "formName": None,
                    "evolutions": [], "preEvolutions": [], "encounters": [],
                    "card": cards.get(key),
                })
                entry["sprites"] = sprites_for(base["number"], formno, battlers, icons)
                all_species.append(entry)
                by_internal[key] = entry
                created += 1
            else:
                enriched += 1

            if ov.get("baseStats"):
                entry["baseStats"] = dict(zip(pbs.STAT_ORDER, ov["baseStats"]))
                entry["baseStatTotal"] = sum(ov["baseStats"])
            if ov.get("effortPoints"):
                entry["effortPoints"] = dict(zip(pbs.STAT_ORDER, ov["effortPoints"]))
            if ov.get("abilities"):
                # A Mega has exactly the ability the script gives it, and no
                # hidden ability inherited from the base species.
                entry["abilities"] = list(ov["abilities"])
                entry["hiddenAbility"] = None
            if ov.get("type1") or ov.get("type2"):
                t = list(entry["types"]) or ["NORMAL"]
                if ov.get("type1"):
                    t = [ov["type1"]] + t[1:]
                if ov.get("type2"):
                    t = (t + [None])[:1] + [ov["type2"]]
                entry["types"] = [x for x in t if x]
            for k in ("height", "weight"):
                if ov.get(k):
                    entry[k] = ov[k]
            if ov.get("kind"):
                entry["kind"] = ov["kind"]

            # Fusions reuse the Mega machinery (getMegaForm + a stone), but
            # they are a separate mechanic and must not be labelled "Mega".
            entry["isFusion"] = bool(ov.get("isFusion"))
            entry["isMega"] = bool(ov.get("isMega")) and not entry["isFusion"]
            entry["megaStone"] = ov.get("megaStone")
            name = ov.get("megaName")
            if not name and entry["isFusion"] and not entry.get("formName"):
                stone = ITEM_NAMES.get(ov.get("megaStone") or "")
                name = ("%s (%s)" % (base["name"], stone) if stone
                        else "%s (Fusion %d)" % (base["name"], formno))
            if not name and not entry.get("formName"):
                # Script-only forms have no name anywhere in the data. Say
                # "Mega X" when a stone triggers it, otherwise number it, which
                # beats letting the display-name deduplicator invent
                # "Groudon (Groudon 1)".
                name = ("Mega %s" % base["name"] if ov.get("isMega")
                        else "%s (Form %d)" % (base["name"], formno))
            if name:
                entry["formName"] = name
                entry["name"] = name

    # Fusion-capable species and the exclusive move each fused form gains.
    capable, fusion_moves = forms_mod.fusion_data(scripts)
    for s in all_species:
        s.setdefault("isMega", False)
        s.setdefault("isFusion", False)
        s.setdefault("megaStone", None)
        s["canFuse"] = s["internal"] in capable or s["baseSpecies"] in capable
        s["fusionMove"] = fusion_moves.get(s["baseSpecies"]) if s["isFusion"] else None

    # pokemonforms.txt keeps a few leftovers the game can no longer reach:
    # CHARIZARD-3 is a second "Mega Charizard Y" but getMegaForm only ever
    # returns 1 or 2, and the entry has no sprite of its own. Drop a PBS form
    # when a script-defined mega of the same species already claims its name.
    claimed = {(s["baseSpecies"], s["formName"]) for s in all_species
               if s.get("isMega") and s.get("formName")}
    stale = [s for s in all_species
             if not s.get("isMega") and s["formNumber"]
             and not s["sprites"].get("front")  # hasOwnSprite is set later
             and (s["baseSpecies"], s.get("formName")) in claimed]
    for s in stale:
        all_species.remove(s)
        by_internal.pop(s["internal"], None)

    print("  script forms: %d enriched, %d created that PBS never defines, "
          "%d unreachable duplicate(s) dropped" % (enriched, created, len(stale)))


def flag_special_species(all_species, scripts):
    """Mark bosses, and work out the stats they actually fight with.

    Mutant, Alpha and Fusion species have their base stats multiplied before
    the normal stat formula runs, and a named boss's HP is replaced outright.
    Publishing the raw PBS numbers for these is misleading, so the real values
    are computed here and shown alongside.
    """
    bosses = forms_mod.boss_species(scripts)
    scaling = forms_mod.stat_scaling(scripts)
    factors = scaling["kindFactor"]
    diffs = scaling["difficulty"]
    fixed_hp = scaling["fixedHP"]

    for s in all_species:
        kind = s.get("kind") or ""
        s["isBoss"] = s["internal"] in bosses or s["baseSpecies"] in bosses
        s["isMutant"] = kind == "Mutant"
        s["statScaleKind"] = kind if kind in factors else None
        s["fixedHP"] = fixed_hp.get(s["internal"]) or fixed_hp.get(s["baseSpecies"])
        s["scaledStats"] = None
        s["statScale"] = None

        if s["statScaleKind"] or s["fixedHP"]:
            base_factor = factors.get(kind, 1)
            # (factor * mutmult).floor, per difficulty.
            s["statScale"] = {
                name: int(base_factor * mult) if s["statScaleKind"] else 1
                for name, mult in diffs.items()
            }
            scaled = {}
            for name in diffs:
                mult = s["statScale"][name]
                row = {k: v * mult for k, v in s["baseStats"].items()}
                if s["fixedHP"]:
                    row["hp"] = s["fixedHP"]
                scaled[name] = row
            s["scaledStats"] = scaled

    # What the pages actually show. For almost every Pokemon this is just the
    # PBS stats; for the scaled ones it is the Normal-difficulty result, which
    # is the number a player sees in a normal playthrough. baseStats keeps the
    # raw PBS values for anyone using the JSON directly.
    for s in all_species:
        normal = (s.get("scaledStats") or {}).get("normal")
        s["effectiveStats"] = dict(normal or s["baseStats"])
        s["effectiveStatTotal"] = sum(s["effectiveStats"].values())
        s["difficultyPercent"] = None
        scale = s.get("statScale")
        if scale and scale.get("normal"):
            ref = scale["normal"]
            pct = {d: round((scale[d] / ref - 1) * 100, 1)
                   for d in scale if d != "normal"}
            # Dream species use a flat x3 regardless of difficulty, and a boss
            # with fixed HP has no HP difference either way.
            if any(abs(v) > 0.05 for v in pct.values()):
                s["difficultyPercent"] = pct
    return bosses


def assign_display_names(all_species):
    """Give every entry a unique displayName and URL slug.

    Vanilla species keep their plain name; colliding variants get a qualifier
    drawn from their internal-name prefix, e.g. "Zubat (Omuran)".
    """
    counts = defaultdict(int)
    for s in all_species:
        counts[s["name"]] += 1

    for s in all_species:
        prefix = None
        m = re.match(r"^([A-Z0-9]+)_", s["internal"])
        if m and not s["formNumber"]:
            prefix = VARIANT_LABELS.get(m.group(1))
        s["variant"] = prefix

        name = s["name"]
        # Only variants get qualified. The prefix-less entry is the original
        # Charmander, so it keeps the bare name and DR_CHARMANDER becomes
        # "Charmander (Deshret)".
        if counts[name] > 1 and not s["formNumber"] and m:
            if prefix and prefix.lower() not in name.lower():
                name = "%s (%s)" % (s["name"], prefix)
            else:
                # Prefix is already in the name (Rayqyomi, Zineom...); qualify with
                # whatever distinguishes this entry from its siblings instead.
                tail = s["internal"]
                if m:
                    tail = s["internal"][len(m.group(1)) + 1:]
                tail = pbs.titlecase_name(tail) or pbs.titlecase_name(s["internal"])
                name = "%s (%s)" % (s["name"], tail)
        s["displayName"] = name

    # Last resort: anything still ambiguous gets its internal name appended.
    dupes = defaultdict(list)
    for s in all_species:
        dupes[s["displayName"]].append(s)
    for name, group in dupes.items():
        if len(group) > 1:
            for s in group:
                s["displayName"] = "%s [%s]" % (name, s["internal"])

    used = {}
    for s in all_species:
        base = slugify(s["displayName"])
        slug = base
        if slug in used:
            slug = slugify(s["internal"])
            n = 2
            while slug in used:
                slug = "%s-%d" % (base, n)
                n += 1
        used[slug] = s["internal"]
        s["slug"] = slug


def resolve_sprites(all_species, by_internal):
    """Fall back to the base species sprite, the way the game's loader does.

    Species with no sprite anywhere are flagged: the Randomizer script lists
    several of them as unfinished ("I don't have backsprites for ..."), so they
    exist in the data but are not obtainable in normal play.
    """
    for s in all_species:
        sp = s["sprites"]
        s["hasOwnSprite"] = bool(sp["front"])
        s["spriteFallback"] = None
        if s["formNumber"]:
            base = by_internal.get(s["baseSpecies"])
            if base:
                # Fill each missing slot individually: several Mega forms have a
                # battler but no party icon of their own.
                for k, v in base["sprites"].items():
                    if not sp.get(k) and v:
                        sp[k] = v
                        if k == "front":
                            s["spriteFallback"] = base["internal"]
        s["implemented"] = bool(sp["front"])


def read_scripts():
    """Section name -> Ruby source, out of Data/Scripts.rxdata."""
    import zlib
    import marshal48
    out = {}
    for entry in marshal48.load(os.path.join(ROOT, "Data", "Scripts.rxdata")):
        name = entry[1]
        name = name.decode("utf-8", "replace") if isinstance(name, bytes) else str(name)
        try:
            out[name] = zlib.decompress(entry[2]).decode("utf-8", "replace")
        except Exception:
            continue
    return out


# Soft level cap granted by each badge, from BADGELEVEL in the Other Stuff script.
def badge_levels(scripts):
    for src in scripts.values():
        m = re.search(r"BADGELEVEL\s*=\s*\[([^\]]*)\]", src)
        if m:
            return [int(x) for x in re.findall(r"\d+", m.group(1))]
    return []


def assemble_trainers(battles, gym_parties, badges, ttypes, scripts, map_names):
    """De-duplicate battles, name them, and merge the gym records."""
    caps = badge_levels(scripts)

    # The same battle is usually repeated across event pages (before/after
    # states); keep one copy per identical team in one place.
    seen = {}
    for b in battles:
        sig = (b["mapId"], b["name"], b["trainerTypeId"],
               tuple((p["species"], p["level"]) for p in b["party"]))
        if sig in seen:
            continue
        seen[sig] = b
    unique = list(seen.values())

    used = {}
    out = []
    for b in unique:
        if b["gym"] or not b["party"]:
            continue  # gym leaders get their own page; empty parties are noise
        ttype = ttypes.get(b["trainerTypeId"], "Trainer")
        display = "%s %s" % (ttype, b["name"]) if b["name"] else ttype
        base = slugify(display) or "trainer"
        slug, n = base, 2
        while slug in used:
            slug = "%s-%d" % (base, n)
            n += 1
        used[slug] = True
        out.append({
            "slug": slug, "name": b["name"], "displayName": display,
            "trainerType": ttype, "trainerTypeId": b["trainerTypeId"],
            "mapId": b["mapId"], "mapName": b["mapName"], "event": b["event"],
            "party": b["party"], "gym": b["gym"], "dynamic": b["dynamic"],
            "partySize": len(b["party"]),
            "maxLevel": max((p["level"] for p in b["party"]), default=0),
        })
    # "Hiker Keith" turns up in several places; a wiki page title has to be
    # unique, so qualify repeats with where the battle happens.
    by_name = defaultdict(list)
    for t in out:
        by_name[t["displayName"]].append(t)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for t in group:
            if t["mapName"]:
                t["displayName"] = "%s (%s)" % (name, t["mapName"])
    still = defaultdict(list)
    for t in out:
        still[t["displayName"]].append(t)
    for name, group in still.items():
        if len(group) < 2:
            continue
        for i, t in enumerate(group, 1):
            t["displayName"] = "%s (%d)" % (name, i)

    out.sort(key=lambda t: (t["mapId"], t["displayName"]))

    # Gym leaders: the team comes from GymTeams, the name and badge from events.
    # Gyms 1-3 name their leader in the map event; 4-8 go through a helper in
    # SpecialFights, so fall back to that.
    leaders = {}
    for b in unique:
        if b["gym"]:
            leaders[b["gym"]] = (b["name"], b["trainerTypeId"], b["mapId"])
    for n, (name, ttid) in trainers_mod.gym_leaders(scripts).items():
        if n not in leaders:
            leaders[n] = (name, ttid, None)
    gyms = []
    for g in gym_parties:
        n = g["gym"]
        badge = badges[n - 1] if n - 1 < len(badges) else {}
        leader, ttid, mapid = leaders.get(n, (None, None, badge.get("mapId")))
        gyms.append({
            "gym": n,
            "leader": leader or badge.get("leader"),
            "trainerType": ttypes.get(ttid) if ttid else None,
            "mapId": mapid, "mapName": map_names.get(mapid) if mapid else badge.get("mapName"),
            "badge": badge.get("badge"),
            "reward": badge.get("reward"),
            "levelCap": caps[n] if n < len(caps) else None,
            "normal": g["normal"], "extreme": g["extreme"],
        })
    return out, gyms


def main():
    os.makedirs(OUT, exist_ok=True)
    print("Reading PBS from %s\n" % PBS_DIR)

    types = extract_types()
    abilities = extract_abilities()
    moves = extract_moves()
    items, cards = extract_items()
    machine_compat = extract_machine_compat()
    battlers, icons = sprite_index()

    MOVE_NAMES.update({m["internal"]: m["name"] for m in moves})
    ITEM_NAMES.update({i["internal"]: i["name"] for i in items})

    for group in (moves, abilities, items):
        assign_unique_names(group)
    for a in abilities:
        a["exclusive"] = is_exclusive_ability(a)
    for i in items:
        i["exclusive"] = is_exclusive_item(i)

    scripts = read_scripts()
    species = extract_species(machine_compat, cards, battlers, icons, scripts)

    # ---- trainer battles first: which maps have them feeds the location set
    map_names = locations_mod.map_names(ROOT)
    ttypes = trainers_mod.trainer_types(PBS_DIR)
    battles = trainers_mod.scan_maps(ROOT, map_names)
    trainer_map_ids = {b["mapId"] for b in battles}

    # ---- item pickups and shop stock (early: the maps they sit on need pages)
    raw_pickups, raw_shops = pickups_mod.scan(ROOT, map_names)

    # ---- wild encounters, plus a page for anywhere a region map names, a
    # trainer stands, or an item can be found or bought
    extra = townmap_mod.resolve_maps(PBS_DIR, map_names, trainer_map_ids,
                                     locations_mod.map_regions(PBS_DIR))
    for mid in trainer_map_ids:
        extra.setdefault(mid, "trainers")
    for mid in {p["mapId"] for p in raw_pickups}:
        extra.setdefault(mid, "items")
    for mid in {s["mapId"] for s in raw_shops}:
        extra.setdefault(mid, "shop")
    locs, enc_index = locations_mod.build(ROOT, PBS_DIR, slugify, extra)
    for s in species:
        s["encounters"] = enc_index.get(s["internal"], [])

    # ---- gym teams and badges
    gym_parties = trainers_mod.gym_teams(scripts)
    badges = trainers_mod.badge_events(ROOT, map_names)
    battles, gyms = assemble_trainers(battles, gym_parties, badges, ttypes,
                                      scripts, map_names)
    trainer_index = defaultdict(list)
    for t in battles:
        for i, mon in enumerate(t["party"]):
            trainer_index[mon["species"]].append({
                "trainer": t["displayName"], "slug": t["slug"],
                "mapName": t["mapName"], "level": mon["level"], "slot": i,
            })
    for g in gyms:
        for key in ("normal", "extreme"):
            for i, mon in enumerate(g[key]):
                trainer_index[mon["species"]].append({
                    "trainer": "%s (Gym %d, %s)" % (g["leader"] or "Gym Leader",
                                                    g["gym"], key.title()),
                    "slug": "gym-%d" % g["gym"], "mapName": g["mapName"],
                    "level": mon["level"], "slot": i,
                })
    for s in species:
        s["trainers"] = trainer_index.get(s["internal"], [])

    # Tag moves that are backed by a real TM/HM item, plus who can learn them.
    machine_items = {i["machine"]: i for i in items if i["machine"]}
    for m in moves:
        mi = machine_items.get(m["internal"])
        m["machine"] = mi["name"] if mi else None
        rec = machine_compat.get(m["internal"])
        m["taughtTo"] = rec["species"] if rec else []
        m["tutorHeadings"] = rec["headings"] if rec else []
    learned_by = defaultdict(set)
    for s in species:
        for lm in s["levelMoves"]:
            learned_by[lm["move"]].add(s["internal"])
        for em in s["eggMoves"]:
            learned_by[em].add(s["internal"])
    for m in moves:
        m["levelUpLearners"] = sorted(learned_by.get(m["internal"], []))

    def dump(name, obj, count):
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
        print("  %-16s %6d entries  %8.1f KB" % (name, count, os.path.getsize(p) / 1024.0))

    # ---- resolve pickups against the item list and index them
    known = {i["internal"] for i in items}
    pickup_list, shop_list, missing = pickups_mod.drop_unknown(
        raw_pickups, raw_shops, known)
    if missing:
        print("  note: %d item constant(s) referenced by events no longer exist "
              "and are dropped, as the game does: %s"
              % (len(missing), ", ".join(missing)))
    found_idx, sold_idx = pickups_mod.index_by_item(pickup_list, shop_list, locs)
    for i in items:
        i["foundAt"] = found_idx.get(i["internal"], [])
        i["soldAt"] = sold_idx.get(i["internal"], [])

    dump("types.json", types, len(types["types"]))
    dump("abilities.json", abilities, len(abilities))
    dump("moves.json", moves, len(moves))
    dump("items.json", items, len(items))
    dump("pokemon.json", species, len(species))

    # ---- named boss and story battles
    special = {s["internal"] for s in species
               if s.get("isBoss")
               or (s.get("kind") or "") in ("Mutant", "Fusion", "Alpha", "Dream",
                                            "Mythical", "Cyborg")}
    wild_bosses = bosses_mod.scan_wild(ROOT, map_names, special, pbs.titlecase_name)
    boss_list = bosses_mod.scan(
        ROOT, scripts, map_names, locations_mod.map_regions(PBS_DIR),
        locations_mod.REGION_NAMES, slugify, ttypes, locs, wild_bosses)
    print("  boss battles: %d" % len(boss_list))

    # region maps, with each point resolved to a location page where possible
    regions = townmap_mod.build(PBS_DIR, locs, slugify)
    linked = sum(1 for r in regions for p in r["points"] if p["slug"])
    total_points = sum(len(r["points"]) for r in regions)
    print("  region maps: %d points, %d linked to a page (%.0f%%)"
          % (total_points, linked, 100.0 * linked / max(total_points, 1)))

    dump("locations.json", locs, len(locs))
    dump("regions.json", regions, len(regions))
    dump("pickups.json", pickup_list, len(pickup_list))
    dump("shops.json", shop_list, len(shop_list))
    dump("trainers.json", battles, len(battles))
    dump("gyms.json", gyms, len(gyms))
    dump("bosses.json", boss_list, len(boss_list))

    meta = {
        "game": "Pokemon Empyrean",
        "engine": "Pokemon Essentials v17 (RPG Maker XP)",
        "counts": {
            "species": len([s for s in species if not s["formNumber"]]),
            "forms": len([s for s in species if s["formNumber"]]),
            "moves": len(moves), "abilities": len(abilities),
            "items": len(items),
            "cards": len([i for i in items if i["isCard"]]),
            "exclusiveAbilities": len([a for a in abilities if a["exclusive"]]),
            "exclusiveItems": len([i for i in items if i["exclusive"]]),
            "exclusiveItemsNoCards": len([i for i in items if i["exclusive"] and not i["isCard"]]),
            "machines": len([i for i in items if i["isMachine"]]),
            "types": len(types["types"]),
            "locations": len(locs),
            "encounterTables": sum(len(l["tables"]) for l in locs),
            "speciesWithEncounters": len(enc_index),
            "regions": len({l["regionName"] for l in locs if l["regionName"]}),
            "trainers": len(battles),
            "trainerPokemon": sum(len(t["party"]) for t in battles),
            "gyms": len(gyms),
            "megas": len([s for s in species if s.get("isMega")]),
            "fusions": len([s for s in species if s.get("isFusion")]),
            "bosses": len([s for s in species if s.get("isBoss")]),
            "bossBattles": len(boss_list),
            "scaledSpecies": len([s for s in species if s.get("scaledStats")]),
            "regionMaps": len(regions),
            "mappedPlaces": sum(len(r["places"]) for r in regions),
            "pickups": len(pickup_list),
            "shops": len(shop_list),
            "itemsFindable": len(found_idx),
            "itemsSold": len(sold_idx),
        },
        "regionNames": locations_mod.REGION_NAMES,
        # Boss and mutant stats are multiplied at battle time by (1+gpBoost)^gp,
        # where a boss's gp is 10% of the player's party total, capped at maxGP.
        "gp": forms_mod.gp_constants(scripts),
        "statScaling": forms_mod.stat_scaling(scripts),
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print("\n" + json.dumps(meta["counts"], indent=1))


if __name__ == "__main__":
    main()
