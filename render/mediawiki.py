#!/usr/bin/env python
"""Render wiki/data/*.json as MediaWiki XML ready for Special:Import.

Produces one XML file per content group (plus a combined dump) in wiki/out/.
Special:Import in a browser is usually capped around 2 MB, so the groups are
also chunked; a wiki admin with shell access can skip that and use
    php maintenance/importDump.php empyrean-all.xml
Templates are emitted as pages too, so importing bootstraps the whole wiki.

Images are NOT part of a MediaWiki XML dump. wiki/out/upload-manifest.csv lists
every file the pages reference alongside its path on disk, for Special:Upload,
Extension:SimpleBatchUpload or pywikibot's upload.py.
"""
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from xml.sax.saxutils import escape

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "wiki", "data")
OUT = os.path.join(ROOT, "wiki", "out")
GFX = os.path.join(ROOT, "Graphics")

SITENAME = "Pokemon Empyrean Wiki"
AUTHOR = "EmpyreanBot"
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MAX_BYTES = 1_800_000  # keep each chunk under the usual 2 MB upload cap

STAT_LABELS = [("hp", "HP"), ("attack", "Attack"), ("defense", "Defense"),
               ("spatk", "Sp. Atk"), ("spdef", "Sp. Def"), ("speed", "Speed")]


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


species = load("pokemon.json")
moves = load("moves.json")
abilities = load("abilities.json")
items = load("items.json")
locations = load("locations.json")
trainers = load("trainers.json")
gyms = load("gyms.json")
map_regions = load("regions.json")
pickups = load("pickups.json")
shops = load("shops.json")
types_data = load("types.json")
types = types_data["types"]
chart = types_data["chart"]
meta = load("meta.json")

by_species = {s["internal"]: s for s in species}
by_move = {m["internal"]: m for m in moves}
by_ability = {a["internal"]: a for a in abilities}
by_item = {i["internal"]: i for i in items}
by_type = {t["internal"]: t for t in types}
by_location = {l["slug"]: l for l in locations}


def location_title(l):
    """Areas can share a name across several maps; keep the titles unique."""
    same = [o for o in locations if o["name"] == l["name"]]
    return l["name"] if len(same) == 1 else "%s (map %d)" % (l["name"], l["mapId"])

move_name = lambda k: by_move[k]["displayName"] if k in by_move else k.title()
ability_name = lambda k: by_ability[k]["displayName"] if k in by_ability else k.title()
item_name = lambda k: by_item[k]["displayName"] if k in by_item else k.title()
type_name = lambda k: by_type[k]["name"] if k in by_type else k.title()


def page_title(s):
    """Page titles must be unique; displayName already guarantees that."""
    return s["displayName"].replace("[", "(").replace("]", ")")


def file_name(s, shiny=False):
    base = re.sub(r"[^A-Za-z0-9 ]+", "", page_title(s)).strip().replace(" ", "_")
    return "%s%s.png" % (base, "_shiny" if shiny else "")


def icon_file(s):
    base = re.sub(r"[^A-Za-z0-9 ]+", "", page_title(s)).strip().replace(" ", "_")
    return "%s_icon.png" % base


# --------------------------------------------------------------- templates
TEMPLATES = {
"Template:Type": """<includeonly>[[{{{1}}} (type)|{{{1}}}]]</includeonly><noinclude>
Links a type name to its page. Usage: <code>{{Type|Grass}}</code>
[[Category:Templates]]</noinclude>""",

"Template:Infobox Pokemon": """<includeonly>{| class="infobox" style="float:right; clear:right; width:22em; \
border:1px solid #a2a9b1; background:#f8f9fa; margin:0 0 1em 1em; font-size:88%"
! colspan="2" style="font-size:120%; background:#dbe3ec" | {{{name}}}
|-
| colspan="2" style="text-align:center" | [[File:{{{image}}}|160px|{{{name}}}]] \
{{#if:{{{shiny|}}}|[[File:{{{shiny}}}|160px|Shiny {{{name}}}]]}}
|-
! Dex no. | {{{number}}}
|-
! Type | {{Type|{{{type1}}}}}{{#if:{{{type2|}}}| / {{Type|{{{type2}}}}}}}
|-
! Species | {{{species|}}} Pokemon
|-
! Height | {{{height}}} m
|-
! Weight | {{{weight}}} kg
|-
! Abilities | {{{abilities|}}}
|-
! Hidden ability | {{{hidden|None}}}
|-
! Catch rate | {{{catchrate}}}
|-
! Base EXP | {{{baseexp}}}
|-
! Growth rate | {{{growth}}}
|-
! Gender | {{{gender}}}
|-
! Egg groups | {{{egggroups|}}}
|-
! Hatch time | {{{hatch}}} steps
|}</includeonly><noinclude>
Infobox used at the top of every Pokemon page.
[[Category:Templates]]</noinclude>""",

"Template:Stats": """<includeonly>{| class="wikitable" style="text-align:right"
! Stat !! Base
|-
| style="text-align:left" | HP || {{{hp}}}
|-
| style="text-align:left" | Attack || {{{attack}}}
|-
| style="text-align:left" | Defense || {{{defense}}}
|-
| style="text-align:left" | Sp. Atk || {{{spatk}}}
|-
| style="text-align:left" | Sp. Def || {{{spdef}}}
|-
| style="text-align:left" | Speed || {{{speed}}}
|-
! style="text-align:left" | Total !! {{{total}}}
|}</includeonly><noinclude>
Base stat table for Pokemon pages.
[[Category:Templates]]</noinclude>""",
}


# --------------------------------------------------------------- helpers
def wt_table(headers, rows, cls="wikitable sortable"):
    out = ['{| class="%s"' % cls, "! " + " !! ".join(headers)]
    for r in rows:
        out.append("|-")
        out.append("| " + " || ".join("" if c is None else str(c) for c in r))
    out.append("|}")
    return "\n".join(out)


def defensive_multiplier(atk, defending):
    m = 1.0
    for d in defending:
        m *= chart.get(atk, {}).get(d, 1.0)
    return m


# --------------------------------------------------------------- pages
def species_page(s):
    types_ = s["types"]
    abil = ", ".join("[[%s]]" % ability_name(a) for a in s["abilities"]) or "None"
    hidden = "[[%s]]" % ability_name(s["hiddenAbility"]) if s["hiddenAbility"] else "None"
    gender = ("Genderless" if s["malePercent"] is None
              else "%s%% male / %s%% female" % (s["malePercent"], s["femalePercent"]))

    L = []
    L.append("{{Infobox Pokemon")
    L.append("| name = %s" % page_title(s))
    L.append("| number = %03d" % s["number"])
    L.append("| image = %s" % file_name(s))
    L.append("| shiny = %s" % file_name(s, True))
    L.append("| type1 = %s" % type_name(types_[0]) if types_ else "| type1 = ")
    if len(types_) > 1:
        L.append("| type2 = %s" % type_name(types_[1]))
    L.append("| species = %s" % (s["kind"] or ""))
    L.append("| height = %s" % s["height"])
    L.append("| weight = %s" % s["weight"])
    L.append("| abilities = %s" % abil)
    L.append("| hidden = %s" % hidden)
    L.append("| catchrate = %s" % s["catchRate"])
    L.append("| baseexp = %s" % s["baseEXP"])
    L.append("| growth = %s" % s["growthRate"])
    L.append("| gender = %s" % gender)
    L.append("| egggroups = %s" % ", ".join(s["eggGroups"]))
    L.append("| hatch = %s" % format(s["stepsToHatch"], ","))
    L.append("}}")
    L.append("")

    tdesc = " / ".join("{{Type|%s}}" % type_name(t) for t in types_)
    L.append("'''%s''' is a %s-type Pokemon introduced in ''Pokemon Empyrean''."
             % (page_title(s), tdesc))
    if s["variant"]:
        L.append("It is a %s regional variant." % s["variant"]
                 if s["variant"] in ("Omuran", "Deshret")
                 else "It is a %s form." % s["variant"])
    if s.get("isFusion") and s.get("megaStone"):
        parent = by_species.get(s["baseSpecies"])
        extra = ""
        if s.get("fusionMove"):
            extra = ", gaining [[%s]]" % move_name(s["fusionMove"])
        L.append("It is a Fusion of [[%s]] with [[%s]]%s."
                 % (page_title(parent) if parent else s["baseSpecies"],
                    item_name(s["megaStone"]), extra))
    if s.get("isMega") and s.get("megaStone"):
        parent = by_species.get(s["baseSpecies"])
        L.append("It Mega Evolves from [[%s]] holding [[%s]]."
                 % (page_title(parent) if parent else s["baseSpecies"],
                    item_name(s["megaStone"])))
    if s.get("isBoss") or s.get("isMutant"):
        gp = meta.get("gp", {})
        boost, cap = gp.get("gpBoost", 0.101), gp.get("maxGP", 5)
        L.append("")
        L.append("''%s Pokemon: its stats are multiplied in battle by Generation "
                 "Power, %.3f<sup>GP</sup>, up to %.2fx at GP %d. A boss's GP is a "
                 "tenth of the player's party total, so what you face scales with "
                 "your own team.''"
                 % ("Boss" if s.get("isBoss") else "Mutant",
                    1 + boost, (1 + boost) ** cap, cap))
    if not s["implemented"]:
        L.append("")
        L.append("''This species exists in the game data but has no sprite and is "
                 "excluded from the randomizer, so it does not appear in normal play.''")
    if s["pokedex"]:
        L.append("")
        L.append("<blockquote>%s</blockquote>" % s["pokedex"])

    # Location comes first: where to catch it is what most readers open the
    # page for.
    L.append("")
    L.append("== Abilities ==")
    rows = []
    for key in s["abilities"]:
        a = by_ability.get(key)
        rows.append(["[[%s]]" % ability_name(key), "Standard",
                     a["description"] if a else ""])
    if s["hiddenAbility"]:
        a = by_ability.get(s["hiddenAbility"])
        rows.append(["[[%s]]" % ability_name(s["hiddenAbility"]), "Hidden",
                     a["description"] if a else ""])
    L.append(wt_table(["Ability", "Slot", "Effect"], rows) if rows
             else "This Pokemon has no ability.")

    L.append("")
    L.append("== Location ==")
    if s["encounters"]:
        L.append("Wild encounter rates. A Pokemon filling several slots in one table "
                 "has them added together here.")
        rows = []
        for e in s["encounters"]:
            loc = by_location.get(e["slug"])
            lvl = ("%d" % e["minLevel"] if e["minLevel"] == e["maxLevel"]
                   else "%d&ndash;%d" % (e["minLevel"], e["maxLevel"]))
            where = "[[%s]]" % location_title(loc) if loc else e["location"]
            if e.get("mapCount", 1) > 1:
                where += " (%d areas)" % e["mapCount"]
            rows.append([where, e["regionName"] or "&mdash;", e["method"], lvl,
                         "%d%%" % e["chance"]])
        L.append(wt_table(["Area", "Region", "Method", "Levels", "Chance"], rows))
    else:
        L.append("Not found in any wild encounter table. It may be obtained by evolution, "
                 "as a gift or static encounter, or from an event.")

    L.append("")
    L.append("== Base stats ==")
    L.append("{{Stats")
    for k, _ in STAT_LABELS:
        L.append("| %s = %s" % (k, s["effectiveStats"][k]))
    L.append("| total = %s" % s["effectiveStatTotal"])
    L.append("}}")
    notes = []
    if s.get("difficultyPercent"):
        notes.append("On Easy these are %.1f%% lower and on Extreme %.1f%% higher."
                     % (abs(s["difficultyPercent"]["easy"]),
                        abs(s["difficultyPercent"]["extreme"])))
    if s.get("fixedHP"):
        notes.append("HP is fixed at %d and does not change with difficulty."
                     % s["fixedHP"])
    if s.get("isBoss"):
        notes.append("As a boss its stats rise further in battle, scaling with "
                     "the player's own party.")
    if notes:
        L.append("")
        L.append("''%s''" % " ".join(notes))

    evs = [("%d %s" % (s["effortPoints"][k], lbl)) for k, lbl in STAT_LABELS
           if s["effortPoints"][k] > 0]
    L.append("")
    L.append("EV yield: %s." % (", ".join(evs) if evs else "none"))

    L.append("")
    L.append("== Type matchups ==")
    buckets = {}
    for t in types:
        if t["isPseudoType"]:
            continue
        m = defensive_multiplier(t["internal"], types_)
        if m != 1.0:
            buckets.setdefault(m, []).append(type_name(t["internal"]))
    if buckets:
        rows = []
        for mult in sorted(buckets, reverse=True):
            label = "Immune" if mult == 0 else ("%gx" % mult)
            rows.append([label, ", ".join("{{Type|%s}}" % x for x in buckets[mult])])
        L.append(wt_table(["Damage taken", "Types"], rows, cls="wikitable"))
    else:
        L.append("This Pokemon takes neutral damage from every type.")

    if s["preEvolutions"] or s["evolutions"]:
        L.append("")
        L.append("== Evolution ==")
        for p in s["preEvolutions"]:
            src = by_species.get(p["from"])
            if src:
                L.append("* Evolves from [[%s]] &mdash; %s" % (page_title(src), p["text"]))
        for e in s["evolutions"]:
            tgt = by_species.get(e["to"])
            if tgt:
                L.append("* Evolves into [[%s]] &mdash; %s" % (page_title(tgt), e["text"]))

    L.append("")
    L.append("== Moves ==")
    L.append("=== By level up ===")
    rows = []
    for lm in sorted(s["levelMoves"], key=lambda x: x["level"]):
        m = by_move.get(lm["move"])
        if not m:
            continue
        rows.append([lm["level"] or "&mdash;", "[[%s]]" % m["displayName"],
                     "{{Type|%s}}" % type_name(m["type"]), m["category"],
                     m["power"] or "&mdash;", m["accuracy"] or "&mdash;", m["pp"]])
    L.append(wt_table(["Lv.", "Move", "Type", "Cat.", "Power", "Acc.", "PP"], rows)
             if rows else "This Pokemon does not learn any moves by levelling up.")

    if s["eggMoves"]:
        L.append("")
        L.append("=== Egg moves ===")
        L.append(", ".join("[[%s]]" % move_name(m) for m in s["eggMoves"]))

    if s["machineMoves"]:
        L.append("")
        L.append("=== TMs, HMs and tutors ===")
        rows = []
        for key in s["machineMoves"]:
            m = by_move.get(key)
            if not m:
                continue
            rows.append(["[[%s]]" % m["displayName"], "{{Type|%s}}" % type_name(m["type"]),
                         m["category"], m["power"] or "&mdash;",
                         m["accuracy"] or "&mdash;", m["pp"], m["machine"] or "Tutor"])
        L.append(wt_table(["Move", "Type", "Cat.", "Power", "Acc.", "PP", "Source"], rows))

    L.append("")
    for t in types_:
        L.append("[[Category:%s-type Pokemon]]" % type_name(t))
    if s["variant"]:
        L.append("[[Category:%s variants]]" % s["variant"])
    if not s["implemented"]:
        L.append("[[Category:Unobtainable Pokemon]]")
    if s.get("isMega"):
        L.append("[[Category:Mega Evolutions]]")
    if s.get("isFusion"):
        L.append("[[Category:Fusions]]")
    if s.get("isBoss"):
        L.append("[[Category:Boss Pokemon]]")
    L.append("[[Category:Pokemon]]")
    return "\n".join(L)


def move_page(m):
    learners_lvl, learners_egg, learners_tm = [], [], []
    for s in species:
        if any(lm["move"] == m["internal"] for lm in s["levelMoves"]):
            lvl = next(lm["level"] for lm in s["levelMoves"] if lm["move"] == m["internal"])
            learners_lvl.append((lvl, s))
        if m["internal"] in s["eggMoves"]:
            learners_egg.append(s)
        if m["internal"] in s["machineMoves"]:
            learners_tm.append(s)
    learners_lvl.sort(key=lambda x: (x[0], x[1]["number"]))

    L = ["'''%s''' is a {{Type|%s}}-type %s move."
         % (m["displayName"], type_name(m["type"]), m["category"].lower())]
    if m["machine"]:
        L.append("It is taught by '''%s'''." % m["machine"])
    L.append("")
    L.append("<blockquote>%s</blockquote>" % m["description"])
    L.append("")
    L.append("== Details ==")
    rows = [
        ["Type", "{{Type|%s}}" % type_name(m["type"])],
        ["Category", m["category"]],
        ["Power", m["power"] or "&mdash;"],
        ["Accuracy", ("%s%%" % m["accuracy"]) if m["accuracy"] else "Never misses"],
        ["PP", m["pp"]],
        ["Priority", ("+%d" % m["priority"]) if m["priority"] > 0 else m["priority"]],
        ["Target", m["targetText"]],
    ]
    if m["effectChance"]:
        rows.append(["Effect chance", "%s%%" % m["effectChance"]])
    flags = [label for key, label in [
        ("makesContact", "Makes contact"), ("protectable", "Blocked by Protect"),
        ("soundMove", "Sound move"), ("punchingMove", "Punching move"),
        ("biteMove", "Bite move"), ("bombMove", "Bomb move"),
        ("powderMove", "Powder move"), ("pulseMove", "Pulse move"),
        ("highCritRate", "High critical-hit ratio"),
    ] if m.get(key)]
    if flags:
        rows.append(["Properties", " &middot; ".join(flags)])
    L.append(wt_table(["Property", "Value"], rows, cls="wikitable"))

    if learners_lvl:
        L.append("")
        L.append("== Learned by level up ==")
        L.append(wt_table(["Lv.", "Pokemon"],
                          [[lvl or "&mdash;", "[[%s]]" % page_title(s)] for lvl, s in learners_lvl]))
    if learners_tm:
        L.append("")
        L.append("== Taught by %s ==" % ("machine" if m["machine"] else "tutor"))
        L.append(", ".join("[[%s]]" % page_title(s) for s in learners_tm))
    if learners_egg:
        L.append("")
        L.append("== Egg move for ==")
        L.append(", ".join("[[%s]]" % page_title(s) for s in learners_egg))

    L.append("")
    L.append("[[Category:Moves]]")
    L.append("[[Category:%s-type moves]]" % type_name(m["type"]))
    return "\n".join(L)


def ability_page(a):
    normal = [s for s in species if a["internal"] in s["abilities"]]
    hidden = [s for s in species if s["hiddenAbility"] == a["internal"]]
    L = ["'''%s''' is an ability in ''Pokemon Empyrean''.%s"
         % (a["displayName"],
            " It is new to Empyrean and does not exist in the official games."
            if a.get("exclusive") else ""), ""]
    L.append("<blockquote>%s</blockquote>" % a["description"])
    if normal:
        L.append("")
        L.append("== Pokemon with this ability ==")
        L.append(", ".join("[[%s]]" % page_title(s) for s in normal))
    if hidden:
        L.append("")
        L.append("== As a hidden ability ==")
        L.append(", ".join("[[%s]]" % page_title(s) for s in hidden))
    L.append("")
    L.append("[[Category:Abilities]]")
    if a.get("exclusive"):
        L.append("[[Category:Empyrean abilities]]")
    return "\n".join(L)


def item_page(i):
    L = ["'''%s''' is an item in ''Pokemon Empyrean'', found in the %s pocket."
         % (i["displayName"], i["pocketName"])]
    if i.get("exclusive"):
        L.append("It is new to Empyrean and does not exist in the official games.")
    L.append("")
    L.append("<blockquote>%s</blockquote>" % i["description"])
    rows = [["Pocket", i["pocketName"]]]
    if i["price"]:
        rows.append(["Price", "%s" % format(i["price"], ",")])
    if i["machine"]:
        rows.append(["Move taught", "[[%s]]" % move_name(i["machine"])])
    L.append("")
    L.append(wt_table(["Property", "Value"], rows, cls="wikitable"))

    if i["machine"]:
        learners = [s for s in species if i["machine"] in s["machineMoves"]]
        if learners:
            L.append("")
            L.append("== Compatible Pokemon ==")
            L.append(", ".join("[[%s]]" % page_title(s) for s in learners))
    if i.get("foundAt"):
        L.append("")
        L.append("== Where to find ==")
        rows = []
        for f in i["foundAt"]:
            loc = by_location.get(f["slug"]) if f.get("slug") else None
            how = f.get("method", "")
            if f.get("conditional"):
                how += " (conditional)"
            qty = "x%d" % f["quantity"] if f.get("quantity", 1) > 1 else ""
            where = "[[%s]]" % location_title(loc) if loc else str(f["mapName"])
            if f.get("mapCount", 1) > 1:
                where += " (%d areas)" % f["mapCount"]
            rows.append([where, how, qty])
        L.append(wt_table(["Location", "How", "Quantity"], rows))

    if i.get("soldAt"):
        L.append("")
        L.append("== Sold at ==")
        places = []
        for f in i["soldAt"]:
            loc = by_location.get(f["slug"]) if f.get("slug") else None
            places.append("[[%s]]" % location_title(loc) if loc else str(f["mapName"]))
        L.append(", ".join(places))

    evo = [s for s in species if any(e["param"] == i["internal"] for e in s["evolutions"])]
    if evo:
        L.append("")
        L.append("== Used to evolve ==")
        L.append(", ".join("[[%s]]" % page_title(s) for s in evo))

    L.append("")
    L.append("[[Category:Items]]")
    L.append("[[Category:%s]]" % i["pocketName"])
    if i.get("exclusive"):
        L.append("[[Category:Empyrean items]]")
    return "\n".join(L)


def party_table(party):
    rows = []
    for mon in party:
        sp = by_species.get(mon["species"])
        tags = []
        if mon.get("shiny"):
            tags.append("shiny")
        if mon.get("gender"):
            tags.append(mon["gender"])
        if mon.get("abilityIndex") is not None:
            tags.append("ability %d" % (mon["abilityIndex"] + 1))
        held = []
        if mon.get("item"):
            held.append("[[%s]]" % item_name(mon["item"]))
        if mon.get("card"):
            held.append(item_name(mon["card"]))
        moves = ", ".join("[[%s]]" % move_name(m) for m in mon.get("moves", []))
        rows.append([
            "[[%s]]" % page_title(sp) if sp else mon["species"],
            " / ".join("{{Type|%s}}" % type_name(t) for t in sp["types"]) if sp else "",
            mon["level"],
            "<br>".join(held) or "&mdash;",
            moves or "\'\'level-up moveset\'\'",
            ", ".join(tags) or "",
        ])
    return wt_table(["Pokemon", "Type", "Level", "Held item", "Moves", "Notes"], rows)


def trainer_page(t):
    L = ["'''%s''' is a trainer in ''Pokemon Empyrean''%s."
         % (t["displayName"], ", found in %s" % t["mapName"] if t["mapName"] else "")]
    L.append("")
    L.append("Class: %s. Team of %d, up to level %d."
             % (t["trainerType"], t["partySize"], t["maxLevel"]))
    if t.get("dynamic"):
        L.append("")
        L.append("''Part of this battle is chosen at run time, so the team below may "
                 "differ in play.''")
    L.append("")
    L.append("== Team ==")
    L.append(party_table(t["party"]))
    L.append("")
    L.append("[[Category:Trainers]]")
    L.append("[[Category:%s]]" % t["trainerType"])
    return "\n".join(L)


def gym_page(g):
    title = g["leader"] or ("Gym %d" % g["gym"])
    L = ["'''%s''' is the Gym %d leader in ''Pokemon Empyrean''%s."
         % (title, g["gym"], ", at %s" % g["mapName"] if g["mapName"] else "")]
    L.append("")
    rows = [["Gym", g["gym"]]]
    if g["badge"]:
        rows.append(["Badge", "%s Badge" % g["badge"]])
    if g["mapName"]:
        rows.append(["Location", g["mapName"]])
    if g["levelCap"]:
        rows.append(["Level cap after winning", g["levelCap"]])
    if g["reward"]:
        rows.append(["Reward", "[[%s]]" % item_name(g["reward"])])
    if g["trainerType"]:
        rows.append(["Class", g["trainerType"]])
    L.append(wt_table(["Property", "Value"], rows, cls="wikitable"))
    L.append("")
    L.append("== Team (Normal) ==")
    L.append(party_table(g["normal"]))
    L.append("")
    L.append("== Team (Extreme) ==")
    L.append("On Extreme difficulty the leader fields a different team.")
    L.append(party_table(g["extreme"]))
    L.append("")
    L.append("[[Category:Gym Leaders]]")
    L.append("[[Category:Trainers]]")
    return "\n".join(L)


def gyms_index_page():
    L = ["''Pokemon Empyrean'' has eight gyms. Each badge raises the soft level cap.", ""]
    rows = []
    for g in gyms:
        rows.append([g["gym"],
                     "[[%s]]" % g["leader"] if g["leader"] else "Unknown",
                     "%s Badge" % g["badge"] if g["badge"] else "&mdash;",
                     g["mapName"] or "&mdash;", g["levelCap"] or "&mdash;",
                     "[[%s]]" % item_name(g["reward"]) if g["reward"] else "&mdash;"])
    L.append(wt_table(["#", "Leader", "Badge", "Location", "Level cap", "Reward"], rows))
    L.append("")
    L.append("[[Category:Gym Leaders]]")
    return "\n".join(L)


def region_image_name(r):
    return "Region_%s.png" % re.sub(r"[^A-Za-z0-9]+", "_", r["displayName"]).strip("_")


def region_page(r):
    linked = [p for p in r["places"] if p["slug"]]
    L = ["'''%s''' is a region in ''Pokemon Empyrean''. Its town map marks %d places, "
         "%d of which have a page here."
         % (r["displayName"], len(r["places"]), len(linked))]
    if r["image"]:
        L.append("")
        L.append("[[File:%s|480px|Map of %s]]" % (region_image_name(r), r["displayName"]))
    L.append("")
    L.append("== Places ==")
    rows = []
    for p in sorted(r["places"], key=lambda x: x["name"]):
        loc = by_location.get(p["slug"]) if p["slug"] else None
        name = "[[%s]]" % location_title(loc) if loc else p["name"]
        enc = "yes" if loc and loc.get("hasEncounters") else "&mdash;"
        rows.append([name, p["description"] or "", len(p["squares"]), enc])
    L.append(wt_table(["Place", "Description", "Map squares", "Wild encounters"], rows))
    L.append("")
    L.append("[[Category:Regions]]")
    return "\n".join(L)


def regions_index_page():
    L = ["The world of ''Pokemon Empyrean'' is split across these regions.", ""]
    rows = []
    for r in map_regions:
        rows.append(["[[%s (region)]]" % r["displayName"], len(r["places"]),
                     len([p for p in r["places"] if p["slug"]])])
    L.append(wt_table(["Region", "Places on the map", "With a page"], rows))
    L.append("")
    L.append("[[Category:Regions]]")
    return "\n".join(L)


def location_page(l):
    species_here = sorted({e["species"] for t in l["tables"] for e in t["entries"]})
    where = " in the %s region" % l["regionName"] if l["regionName"] else ""
    if species_here:
        L = ["'''%s''' is an area in ''Pokemon Empyrean''%s. %d wild species can be "
             "found here across %d encounter table%s."
             % (l["name"], where, len(species_here), len(l["tables"]),
                "" if len(l["tables"]) == 1 else "s")]
    else:
        L = ["'''%s''' is an area in ''Pokemon Empyrean''%s. No wild Pokemon are "
             "found here." % (l["name"], where)]
    siblings = [o for o in locations if o["name"] == l["name"] and o["slug"] != l["slug"]]
    if siblings:
        L.append("")
        L.append("Other areas share this name: %s."
                 % ", ".join("[[%s]]" % location_title(o) for o in siblings))
    for t in l["tables"]:
        L.append("")
        L.append("== %s ==" % t["method"])
        if t["density"] is not None:
            L.append("Encounter density: %d." % t["density"])
        rows = []
        for e in t["entries"]:
            sp = by_species.get(e["species"])
            lvl = ("%d" % e["minLevel"] if e["minLevel"] == e["maxLevel"]
                   else "%d&ndash;%d" % (e["minLevel"], e["maxLevel"]))
            rows.append(["[[%s]]" % page_title(sp) if sp else e["species"],
                         " / ".join("{{Type|%s}}" % type_name(x) for x in sp["types"]) if sp else "",
                         lvl, "%d%%" % e["chance"]])
        L.append(wt_table(["Pokemon", "Type", "Levels", "Chance"], rows))
    loot = [p for p in pickups if p["mapId"] == l["mapId"]]
    if loot:
        L.append("")
        L.append("== Items ==")
        rows = []
        for p in loot:
            how = p["method"] + (" (conditional)" if p["conditional"] else "")
            qty = "x%d" % p["quantity"] if p["quantity"] > 1 else ""
            itm = by_item.get(p["item"])
            label = (item_name(p["item"]) if itm and itm.get("isCard")
                     else "[[%s]]" % item_name(p["item"]))
            rows.append([label, how, qty])
        L.append(wt_table(["Item", "How", "Quantity"], rows))

    marts = [sh for sh in shops if sh["mapId"] == l["mapId"]]
    if marts:
        L.append("")
        L.append("== Shops ==")
        for sh in marts:
            if sh.get("greeting"):
                L.append("")
                L.append("''%s''" % sh["greeting"])
            rows = []
            for key in sh["items"]:
                itm = by_item.get(key)
                label = (item_name(key) if itm and itm.get("isCard")
                         else "[[%s]]" % item_name(key))
                rows.append([label,
                             format(itm["price"], ",") if itm and itm["price"] else "&mdash;"])
            L.append(wt_table(["Item", "Price"], rows))

    trainers_here = [t for t in trainers if t["mapId"] == l["mapId"]]
    if trainers_here:
        L.append("")
        L.append("== Trainers ==")
        rows = []
        for t in trainers_here:
            rows.append(["[[%s]]" % t["displayName"], t["trainerType"],
                         t["partySize"], t["maxLevel"]])
        L.append(wt_table(["Trainer", "Class", "Team", "Max level"], rows))

    L.append("")
    if l["regionName"]:
        L.append("See [[%s (region)]] for the town map." % l["regionName"])
        L.append("")
        L.append("[[Category:%s locations]]" % l["regionName"])
    L.append("[[Category:Locations]]")
    return "\n".join(L)


def type_chart_page():
    real = [t for t in types if not t["isPseudoType"]]
    L = ["''Pokemon Empyrean'' uses %d types. Seven do not exist in the official games: "
         "Light, Data, Gold, Electrolight and the fused Fire/Ground, Water/Ground and "
         "Light/Dark." % len(real), ""]
    L.append("== Full chart ==")
    L.append("Rows are the attacking type, columns the defending type.")
    L.append("")
    header = ["Attack &rarr;"] + [t["name"] for t in real]
    rows = []
    for a in real:
        row = ["'''%s'''" % a["name"]]
        for d in real:
            m = chart.get(a["internal"], {}).get(d["internal"], 1.0)
            if m == 1.0:
                row.append("")
            elif m == 0:
                row.append('style="background:#888; color:#fff" | 0')
            elif m == 0.5:
                row.append('style="background:#9cd6b8" | &frac12;')
            else:
                row.append('style="background:#e79a9a" | 2')
        rows.append(row)
    L.append(wt_table(header, rows, cls="wikitable"))

    L.append("")
    L.append("== Individual types ==")
    for t in real:
        L.append("")
        L.append("=== %s ===" % t["name"])
        weak = [w for w in t["weaknesses"] if w not in t["resistances"]]
        L.append("* Weak to: %s" % (", ".join("{{Type|%s}}" % type_name(w) for w in weak) or "nothing"))
        L.append("* Resists: %s" % (", ".join("{{Type|%s}}" % type_name(w) for w in t["resistances"]) or "nothing"))
        L.append("* Immune to: %s" % (", ".join("{{Type|%s}}" % type_name(w) for w in t["immunities"]) or "nothing"))
    L.append("")
    L.append("[[Category:Game mechanics]]")
    return "\n".join(L)


def type_page(t):
    mons = [s for s in species if t["internal"] in s["types"]]
    atk_moves = [m for m in moves if m["type"] == t["internal"]]
    weak = [w for w in t["weaknesses"] if w not in t["resistances"]]
    L = ["'''%s''' is one of the %d types in ''Pokemon Empyrean''. See the "
         "[[Type chart]] for the full matchup table." % (t["name"], len([x for x in types if not x["isPseudoType"]]))]
    L.append("")
    L.append("== Defending ==")
    L.append("* Weak to: %s" % (", ".join("{{Type|%s}}" % type_name(w) for w in weak) or "nothing"))
    L.append("* Resists: %s" % (", ".join("{{Type|%s}}" % type_name(w) for w in t["resistances"]) or "nothing"))
    L.append("* Immune to: %s" % (", ".join("{{Type|%s}}" % type_name(w) for w in t["immunities"]) or "nothing"))
    L.append("")
    L.append("== Pokemon (%d) ==" % len(mons))
    L.append(", ".join("[[%s]]" % page_title(s) for s in mons) or "None.")
    L.append("")
    L.append("== Moves (%d) ==" % len(atk_moves))
    L.append(", ".join("[[%s]]" % m["displayName"] for m in atk_moves) or "None.")
    L.append("")
    L.append("[[Category:Types]]")
    return "\n".join(L)


def main_page():
    c = meta["counts"]
    return "\n".join([
        "__NOTOC__",
        "Welcome to the '''%s'''." % SITENAME,
        "",
        "This wiki is generated directly from the game files, so the numbers match "
        "the version it was built from.",
        "",
        "== Contents ==",
        "* [[:Category:Pokemon|Pokedex]] &mdash; %d species and %d alternate forms"
        % (c["species"], c["forms"]),
        "* [[:Category:Moves|Moves]] &mdash; %d moves" % c["moves"],
        "* [[:Category:Abilities|Abilities]] &mdash; %d abilities" % c["abilities"],
        "* [[:Category:Items|Items]] &mdash; %d items, including %d cards"
        % (c["items"], c["cards"]),
        "* [[:Category:Locations|Locations]] &mdash; %d areas with wild encounters"
        % c["locations"],
        "* [[Regions]] &mdash; town maps and the places on them",
        "* [[Gyms and badges]] &mdash; all %d gym leaders and their teams" % c["gyms"],
        "* [[:Category:Trainers|Trainers]] &mdash; %d trainer battles" % c["trainers"],
        "* [[Type chart]] &mdash; all %d types" % c["types"],
        "",
        "[[Category:Pokemon Empyrean]]",
    ])


# --------------------------------------------------------------- XML output
XML_HEAD = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" \
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" \
xsi:schemaLocation="http://www.mediawiki.org/xml/export-0.11/ \
http://www.mediawiki.org/xml/export-0.11.xsd" version="0.11" xml:lang="en">
  <siteinfo>
    <sitename>{sitename}</sitename>
    <case>first-letter</case>
    <namespaces>
      <namespace key="0" case="first-letter" />
      <namespace key="10" case="first-letter">Template</namespace>
      <namespace key="14" case="first-letter">Category</namespace>
    </namespaces>
  </siteinfo>
"""


def page_xml(title, text):
    ns = 10 if title.startswith("Template:") else 14 if title.startswith("Category:") else 0
    return (
        "  <page>\n"
        "    <title>%s</title>\n"
        "    <ns>%d</ns>\n"
        "    <revision>\n"
        "      <timestamp>%s</timestamp>\n"
        "      <contributor><username>%s</username></contributor>\n"
        "      <comment>Generated from game data</comment>\n"
        "      <model>wikitext</model>\n"
        "      <format>text/x-wiki</format>\n"
        "      <text xml:space=\"preserve\">%s</text>\n"
        "    </revision>\n"
        "  </page>\n"
    ) % (escape(title), ns, TIMESTAMP, AUTHOR, escape(text))


def write_group(name, pages):
    """Write pages as name.xml, splitting into name-1.xml… if over the size cap."""
    os.makedirs(OUT, exist_ok=True)
    chunks, current, size = [], [], 0
    for title, text in pages:
        blob = page_xml(title, text)
        b = len(blob.encode("utf-8"))
        if current and size + b > MAX_BYTES:
            chunks.append(current)
            current, size = [], 0
        current.append(blob)
        size += b
    if current:
        chunks.append(current)

    written = []
    for idx, chunk in enumerate(chunks, 1):
        fn = "%s.xml" % name if len(chunks) == 1 else "%s-%d.xml" % (name, idx)
        path = os.path.join(OUT, fn)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(XML_HEAD.format(sitename=escape(SITENAME)))
            fh.writelines(chunk)
            fh.write("</mediawiki>\n")
        written.append((fn, os.path.getsize(path)))
    return written


def write_manifest():
    """Every image the wikitext references, with its source path on disk."""
    rows = [("filename", "source_path", "description")]
    for s in species:
        sp = s["sprites"]
        if sp.get("front"):
            rows.append((file_name(s), os.path.join(GFX, *sp["front"].split("/")),
                         "%s battle sprite" % page_title(s)))
        if sp.get("shinyFront"):
            rows.append((file_name(s, True), os.path.join(GFX, *sp["shinyFront"].split("/")),
                         "Shiny %s battle sprite" % page_title(s)))
    for r in map_regions:
        if r.get("filename"):
            rows.append((region_image_name(r),
                         os.path.join(GFX, "Pictures", r["filename"]),
                         "Town map of %s" % r["displayName"]))

    path = os.path.join(OUT, "upload-manifest.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return len(rows) - 1, path


def main():
    if not os.path.isdir(DATA):
        sys.exit("run extract.py first")
    os.makedirs(OUT, exist_ok=True)
    print("Rendering MediaWiki XML to %s\n" % OUT)

    groups = [
        ("empyrean-templates", [("Main Page", main_page())]
            + sorted(TEMPLATES.items())
            + [("Type chart", type_chart_page())]
            + [("%s (type)" % t["name"], type_page(t)) for t in types if not t["isPseudoType"]]),
        ("empyrean-pokemon", [(page_title(s), species_page(s)) for s in species]),
        ("empyrean-moves", [(m["displayName"], move_page(m)) for m in moves]),
        ("empyrean-abilities", [(a["displayName"], ability_page(a)) for a in abilities]),
        ("empyrean-items", [(i["displayName"], item_page(i)) for i in items if not i["isCard"]]),
        ("empyrean-locations", [("Regions", regions_index_page())]
            + [("%s (region)" % r["displayName"], region_page(r)) for r in map_regions]
            + [(location_title(l), location_page(l)) for l in locations]),
        ("empyrean-gyms", [("Gyms and badges", gyms_index_page())]
            + [(g["leader"] or ("Gym %d" % g["gym"]), gym_page(g)) for g in gyms]),
        ("empyrean-trainers", [(t["displayName"], trainer_page(t)) for t in trainers]),
    ]

    total_pages = 0
    for name, pages in groups:
        # Drop duplicate titles: MediaWiki would merge them into one page.
        seen, unique = set(), []
        for title, text in pages:
            if title in seen:
                continue
            seen.add(title)
            unique.append((title, text))
        written = write_group(name, unique)
        total_pages += len(unique)
        for fn, size in written:
            print("  %-28s %6.0f KB" % (fn, size / 1024.0))
        if len(pages) != len(unique):
            print("      (skipped %d duplicate title(s))" % (len(pages) - len(unique)))

    n, path = write_manifest()
    print("\n  upload-manifest.csv          %d images listed" % n)
    print("\n  %d pages total" % total_pages)


if __name__ == "__main__":
    main()
