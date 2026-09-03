"""Region maps and their clickable points, from PBS/townmap.txt.

Point schema is "uussUUUU" in Compiler#pbCompileTownMap:
    Point = x, y, name, description, flyMapId, flyX, flyY, switch

The region images are 480x320 and PScreen_RegionMap draws on a 16x16 grid, so a
point at (x, y) covers the pixel box (x*16, y*16, 16, 16). A place that spans
several squares gets one Point per square, which is what makes the whole route
clickable rather than just one tile.
"""
import csv
import io
import os
import re

import pbs

SQUARE = 16
MAP_W, MAP_H = 480, 320


def parse_points(path):
    """-> [{index, name, filename, points:[...]}]"""
    regions = []
    cur = None
    for raw in pbs.read_text(path).split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(\d+)\]$", line)
        if m:
            cur = {"index": int(m.group(1)), "name": None, "filename": None, "points": []}
            regions.append(cur)
            continue
        if cur is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "Name":
            cur["name"] = value.strip().strip('"')
        elif key == "Filename":
            cur["filename"] = value
        elif key == "Point":
            row = next(csv.reader(io.StringIO(value)))
            row = [c.strip() for c in row] + [""] * (8 - len(row))

            def num(v):
                return int(v) if re.match(r"^-?\d+$", v or "") else None

            x, y = num(row[0]), num(row[1])
            if x is None or y is None:
                continue
            cur["points"].append({
                "x": x, "y": y,
                "name": row[2].strip().strip('"'),
                "description": row[3].strip().strip('"') or None,
                "flyMapId": num(row[4]), "flyX": num(row[5]), "flyY": num(row[6]),
                "switch": num(row[7]),
            })
    return regions


def resolve_maps(pbs_dir, map_names, trainer_map_ids, map_regions=None):
    """Map ids worth giving a page to because a region map names them.

    Returns {mapId: reason}. A place name can belong to several maps — route
    segments, but also the same town in two eras: Asutra City exists in Omuran
    (region 0) and again in Year 3030 (region 1). Resolve per region so each
    era gets its own page, and prefer a map with trainers over an empty
    duplicate.
    """
    map_regions = map_regions or {}
    by_name = {}
    for mid, nm in map_names.items():
        by_name.setdefault(nm.lower(), []).append(mid)

    wanted = {}
    for r in parse_points(os.path.join(pbs_dir, "townmap.txt")):
        for p in r["points"]:
            candidates = by_name.get(p["name"].lower())
            if not candidates:
                continue
            same = [m for m in candidates
                    if map_regions.get(m, (None,))[0] == r["index"]]
            unplaced = [m for m in candidates if m not in map_regions]
            pool = same or unplaced
            if not pool:
                continue
            best = sorted(pool, key=lambda m: (m not in trainer_map_ids, m))[0]
            wanted.setdefault(best, "region map")
    return wanted


def build(pbs_dir, locations, slugify):
    """Attach a location slug to every point we can resolve."""
    regions = parse_points(os.path.join(pbs_dir, "townmap.txt"))

    by_map = {l["mapId"]: l for l in locations}

    # Index by (name, region) as well as by name, so a point on the Year 3030
    # map resolves to the Year 3030 Asutra City rather than the Omuran one.
    # Prefer a segment that actually has encounters when a name repeats.
    def better(prev, cand):
        return prev is None or (not prev.get("hasEncounters") and cand.get("hasEncounters"))

    by_name_region, by_name_unplaced = {}, {}
    for l in locations:
        key = l["name"].lower()
        if l["region"] is None:
            if better(by_name_unplaced.get(key), l):
                by_name_unplaced[key] = l
        else:
            rk = (key, l["region"])
            if better(by_name_region.get(rk), l):
                by_name_region[rk] = l

    out = []
    for r in regions:
        pts = []
        for p in r["points"]:
            # The printed name is what the reader clicked on, so match that
            # first, within this region. Never fall back to a same-named place
            # in another region — that is a different location entirely.
            key = p["name"].lower()
            loc = by_name_region.get((key, r["index"])) or by_name_unplaced.get(key)
            if loc is None and p["flyMapId"] is not None:
                # A point's fly target can land on a neighbouring map ("Cycling
                # Highway" flies to Cape Naraku), so it is only a fallback, and
                # only when it stays in this region.
                cand = by_map.get(p["flyMapId"])
                if cand is not None and cand["region"] in (r["index"], None):
                    loc = cand
            pts.append({
                **p,
                "slug": loc["slug"] if loc else None,
                "mapId": loc["mapId"] if loc else None,
                "left": p["x"] * SQUARE, "top": p["y"] * SQUARE,
                "width": SQUARE, "height": SQUARE,
            })

        # Merge the squares of one place into a single labelled area so the map
        # can show one name per place instead of a label per tile.
        places = {}
        for p in pts:
            key = (p["name"].lower(), p["slug"])
            g = places.setdefault(key, {
                "name": p["name"], "slug": p["slug"], "mapId": p["mapId"],
                "description": p["description"], "squares": [],
            })
            g["squares"].append({"x": p["x"], "y": p["y"]})
            if p["description"] and not g["description"]:
                g["description"] = p["description"]

        out.append({
            "index": r["index"],
            "name": r["name"] or "Region %d" % r["index"],
            "slug": slugify(r["name"] or "region-%d" % r["index"]),
            "filename": r["filename"],
            "image": "regions/%d.png" % r["index"] if r["filename"] else None,
            "width": MAP_W, "height": MAP_H, "square": SQUARE,
            "points": pts,
            "places": sorted(places.values(), key=lambda g: g["name"]),
        })

    # Two regions are both called "Year 3030"; page titles and tab labels have
    # to tell them apart.
    counts = {}
    for r in out:
        counts[r["name"]] = counts.get(r["name"], 0) + 1
    seen = {}
    for r in out:
        if counts[r["name"]] > 1:
            seen[r["name"]] = seen.get(r["name"], 0) + 1
            r["displayName"] = "%s (%d)" % (r["name"], seen[r["name"]])
            r["slug"] = slugify(r["displayName"])
        else:
            r["displayName"] = r["name"]
    return out
