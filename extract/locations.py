"""Wild encounter tables, map names and regions.

encounters.txt is a stateful format: a map id line, an optional density line,
then repeating (encounter-type header, N species rows). The number of rows per
table and each row's probability come from EncounterTypes::EnctypeChances in
PField_Encounters, mirrored below.
"""
import os
import re

import pbs

# EncounterTypes::EnctypeChances, straight out of PField_Encounters.
# Note Cave uses the same 12-slot spread as Land in this game.
ENCOUNTER_CHANCES = {
    "Land":         [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
    "Cave":         [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
    "Water":        [60, 30, 5, 4, 1],
    "RockSmash":    [60, 30, 5, 4, 1],
    "OldRod":       [70, 30],
    "GoodRod":      [60, 20, 20],
    "SuperRod":     [40, 40, 15, 4, 1],
    "HeadbuttLow":  [30, 25, 20, 10, 5, 5, 4, 1],
    "HeadbuttHigh": [30, 25, 20, 10, 5, 5, 4, 1],
    "LandMorning":  [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
    "LandDay":      [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
    "LandNight":    [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
    "BugContest":   [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
}
# EnctypeCompileDens: which of the three numbers on the density line applies.
DENSITY_SLOT = {
    "Land": 0, "Cave": 1, "Water": 2, "LandMorning": 0, "LandDay": 0,
    "LandNight": 0, "BugContest": 0,
}
# How the player triggers each table, for display.
METHOD_LABEL = {
    "Land": "Walking in grass", "Cave": "Walking in a cave",
    "Water": "Surfing", "RockSmash": "Rock Smash",
    "OldRod": "Fishing (Basic Rod)", "GoodRod": "Fishing (Strong Rod)",
    "SuperRod": "Fishing (Elite Rod)",
    "HeadbuttLow": "Headbutt (low)", "HeadbuttHigh": "Headbutt (high)",
    "LandMorning": "Walking in grass (morning)",
    "LandDay": "Walking in grass (day)",
    "LandNight": "Walking in grass (night)",
    "BugContest": "Bug Catching Contest",
}
REGION_NAMES = {}


def parse_encounters(path):
    """-> [{mapId, densities, tables:[{type, slots:[{species,min,max}]}]}]"""
    blocks = []
    cur = None
    table = None
    for raw in pbs.read_text(path).split("\n"):
        line = raw.strip()
        if not line or set(line) <= set("#"):
            continue

        m = re.match(r"^(\d+)\s*(?:#.*)?$", line)
        if m:  # new map section
            cur = {"mapId": int(m.group(1)), "densityLine": None, "tables": []}
            blocks.append(cur)
            table = None
            continue

        if cur is None:
            continue

        if line in ENCOUNTER_CHANCES:
            table = {"type": line, "slots": []}
            cur["tables"].append(table)
            continue

        parts = [p.strip() for p in line.split(",")]
        if all(re.match(r"^\d+$", p) for p in parts) and table is None:
            cur["densityLine"] = [int(p) for p in parts]
            continue

        if table is not None and parts and parts[0]:
            lo = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            hi = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else lo
            table["slots"].append({"species": parts[0], "min": lo, "max": hi})

    # The compiler does `encounters[mapid] = thisenc`, so when a map id appears
    # more than once the last block wins and the earlier ones are dead data.
    # encounters.txt does this for map 724 (three blocks). Match the game.
    deduped = {}
    for b in blocks:
        deduped[b["mapId"]] = b
    return list(deduped.values())


def map_names(root):
    """Map id -> name, from Data/MapInfos.rxdata (authoritative)."""
    import marshal48
    mi = marshal48.load(os.path.join(root, "Data", "MapInfos.rxdata"))
    out = {}
    for k, v in mi.items():
        n = v.ivars.get("name")
        out[int(k)] = n.decode("utf-8", "replace") if isinstance(n, bytes) else str(n)
    return out


def map_regions(pbs_dir):
    """Map id -> (region index, x, y) from metadata.txt MapPosition."""
    out = {}
    for sec, f in pbs.read_sections(os.path.join(pbs_dir, "metadata.txt")):
        if not sec.isdigit() or not f.get("MapPosition"):
            continue
        try:
            r, x, y = [int(v) for v in f["MapPosition"].split(",")[:3]]
        except ValueError:
            continue
        out[int(sec)] = (r, x, y)
    return out


def region_names(pbs_dir):
    """Region index -> name, from townmap.txt."""
    out = {}
    for sec, f in pbs.read_sections(os.path.join(pbs_dir, "townmap.txt")):
        if sec.isdigit() and f.get("Name"):
            out[int(sec)] = f["Name"].strip().strip('"')
    return out


def outdoor_flags(pbs_dir):
    out = {}
    for sec, f in pbs.read_sections(os.path.join(pbs_dir, "metadata.txt")):
        if sec.isdigit():
            out[int(sec)] = f.get("Outdoor", "").lower() == "true"
    return out


def build(root, pbs_dir, slugify, extra_maps=None):
    """Assemble location records plus a species -> encounters index.

    `extra_maps` is {mapId: reason} for places that deserve a page even without
    wild encounters — towns with trainers, and anywhere named on a region map —
    so the clickable region maps have somewhere to point.
    """
    blocks = parse_encounters(os.path.join(pbs_dir, "encounters.txt"))
    names = map_names(root)
    regions = map_regions(pbs_dir)
    rnames = region_names(pbs_dir)
    REGION_NAMES.update(rnames)

    if extra_maps:
        have = {b["mapId"] for b in blocks}
        for mid in sorted(extra_maps):
            if mid not in have:
                blocks.append({"mapId": mid, "densityLine": None, "tables": []})

    locations = []
    used_slugs = {}
    for b in blocks:
        mid = b["mapId"]
        name = names.get(mid) or "Map %03d" % mid
        reg = regions.get(mid)
        tables = []
        for t in b["tables"]:
            chances = ENCOUNTER_CHANCES.get(t["type"], [])
            slots = t["slots"]
            if not slots:
                continue
            # Sum the per-slot chances so a species listed twice reads as one
            # combined rate, the way a player experiences it.
            agg = {}
            for idx, s in enumerate(slots):
                pct = chances[idx] if idx < len(chances) else 0
                key = s["species"]
                if key in agg:
                    agg[key]["chance"] += pct
                    agg[key]["minLevel"] = min(agg[key]["minLevel"], s["min"])
                    agg[key]["maxLevel"] = max(agg[key]["maxLevel"], s["max"])
                    agg[key]["slots"] += 1
                else:
                    agg[key] = {"species": key, "chance": pct, "slots": 1,
                                "minLevel": s["min"], "maxLevel": s["max"]}
            dens = None
            if b["densityLine"] and t["type"] in DENSITY_SLOT:
                i = DENSITY_SLOT[t["type"]]
                if i < len(b["densityLine"]):
                    dens = b["densityLine"][i]
            tables.append({
                "type": t["type"],
                "method": METHOD_LABEL.get(t["type"], t["type"]),
                "density": dens,
                "slotCount": len(slots),
                "expectedSlots": len(chances),
                "entries": sorted(agg.values(), key=lambda e: (-e["chance"], e["species"])),
            })
        base = slugify(name)
        slug = base
        n = 2
        # Several map ids share a name (route segments); keep them separate but
        # give each a stable, readable url.
        while slug in used_slugs:
            slug = "%s-%d" % (base, n)
            n += 1
        used_slugs[slug] = mid

        locations.append({
            "mapId": mid, "name": name, "slug": slug,
            "region": reg[0] if reg else None,
            "regionName": rnames.get(reg[0]) if reg else None,
            "mapX": reg[1] if reg else None, "mapY": reg[2] if reg else None,
            "densityLine": b["densityLine"],
            "tables": tables,
            "hasEncounters": bool(tables),
            "reason": "encounters" if tables else (extra_maps or {}).get(mid, "map"),
        })

    locations.sort(key=lambda l: (l["region"] if l["region"] is not None else 99,
                                  l["name"], l["mapId"]))

    index = {}
    for loc in locations:
        for t in loc["tables"]:
            for e in t["entries"]:
                index.setdefault(e["species"], []).append({
                    "mapId": loc["mapId"], "location": loc["name"],
                    "slug": loc["slug"], "regionName": loc["regionName"],
                    "type": t["type"], "method": t["method"],
                    "chance": e["chance"], "slots": e["slots"],
                    "minLevel": e["minLevel"], "maxLevel": e["maxLevel"],
                })

    # Long routes are split across several maps that share a name. If the
    # encounter is identical on each, a player just sees one place, so collapse
    # the repeats; genuinely different segments still get their own row.
    for key, entries in index.items():
        seen = {}
        for e in entries:
            sig = (e["location"], e["method"], e["chance"],
                   e["minLevel"], e["maxLevel"])
            if sig in seen:
                seen[sig]["mapCount"] += 1
            else:
                e["mapCount"] = 1
                seen[sig] = e
        merged = list(seen.values())
        merged.sort(key=lambda e: (-e["chance"], e["location"]))
        index[key] = merged
    return locations, index
