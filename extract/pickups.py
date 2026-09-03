"""Item pickups and shop stock, mined out of map events.

Items reach the player through four calls, all shaped the same way:

    Kernel.pbItemBall(PBItems::GREATBALL)          # a ball lying on the ground
    Kernel.pbReceiveItem(PBItems::APRIPLUM, 3)     # handed over by an NPC
    Kernel.pbReceiveItemSilently(PBItems::...)     # same, no fanfare
    $PokemonBag.pbStoreItem(PBItems::POTION, 2)    # straight into the bag

Shops are `pbPokemonMart([...], "greeting")`, where the list is either inline
(often across several lines) or built into a local variable just above the call.
"""
import glob
import os
import re

import marshal48

SCRIPT_CODES = (355, 655)

ITEM_CALLS = {
    "pbItemBall": "Item ball",
    "pbReceiveItem": "Given",
    "pbReceiveItemSilently": "Given",
    "pbStoreItem": "Given",
}
# Longest name first so pbReceiveItemSilently is not matched as pbReceiveItem.
ITEM_CALL_RE = re.compile(
    r"\b(%s)\s*\(\s*(?:PBItems::)?([A-Z0-9_]+)\s*(?:,\s*(\d+))?\s*\)"
    % "|".join(sorted(ITEM_CALLS, key=len, reverse=True)))

MART_RE = re.compile(r"pbPokemonMart\s*\(")
SYMBOL_RE = re.compile(r":([A-Z0-9_]+)")


def page_script(page):
    parts = []
    for c in page.ivars["list"]:
        if c.ivars["code"] not in SCRIPT_CODES:
            continue
        params = c.ivars["parameters"]
        if not params:
            continue
        v = params[0]
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)


def _balanced(text, start, open_ch, close_ch):
    """Index just past the bracket opened at `start`, or None."""
    depth, i = 1, start
    while i < len(text) and depth:
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
        i += 1
    return None if depth else i


def find_items(blob):
    """-> [{item, quantity, method, conditional}]"""
    out = []
    for m in ITEM_CALL_RE.finditer(blob):
        fn, item, qty = m.group(1), m.group(2), m.group(3)
        # Everything after the call on the same line: `... if r == 1` means the
        # pickup only happens in some branch.
        eol = blob.find("\n", m.end())
        tail = blob[m.end():eol if eol != -1 else len(blob)]
        line_start = blob.rfind("\n", 0, m.start()) + 1
        head = blob[line_start:m.start()]
        conditional = bool(re.search(r"\bif\b", tail) or re.search(r"\bif\b", head))
        out.append({
            "item": item,
            "quantity": int(qty) if qty else 1,
            "method": ITEM_CALLS[fn],
            "conditional": conditional,
        })
    return out


def find_shops(blob):
    """-> [{items:[...], greeting}]"""
    shops = []
    for m in MART_RE.finditer(blob):
        end = _balanced(blob, m.end(), "(", ")")
        if end is None:
            continue
        args = blob[m.end():end - 1]
        arg0 = args.lstrip()

        if arg0.startswith("["):
            close = _balanced(args, args.index("[") + 1, "[", "]")
            body = args[args.index("[") + 1:close - 1] if close else ""
            rest = args[close:] if close else ""
        else:
            # pbPokemonMart(items, "...") — resolve the variable assigned above.
            var = re.match(r"(\w+)", arg0)
            body, rest = "", args
            if var:
                assign = None
                for a in re.finditer(r"\b%s\s*=\s*\[" % re.escape(var.group(1)), blob[:m.start()]):
                    assign = a
                if assign:
                    close = _balanced(blob, assign.end(), "[", "]")
                    if close:
                        body = blob[assign.end():close - 1]
                rest = args[var.end():]

        items = SYMBOL_RE.findall(body)
        if not items:
            continue
        greet = re.search(r'"([^"]{3,})"', rest)
        shops.append({
            "items": items,
            "greeting": greet.group(1) if greet else None,
        })
    return shops


def scan(root, map_names):
    """-> (pickups, shops), each already de-duplicated across event pages."""
    pickups, shops = [], []
    seen_p, seen_s = set(), set()

    for f in sorted(glob.glob(os.path.join(root, "Data", "Map[0-9]*.rxdata"))):
        mid = int(re.search(r"Map(\d+)", os.path.basename(f)).group(1))
        try:
            m = marshal48.load(f)
        except Exception:
            continue
        name = map_names.get(mid)
        for _, e in m.ivars["events"].items():
            ename = e.ivars["name"]
            ename = ename.decode("utf-8", "replace") if isinstance(ename, bytes) else str(ename)
            for page in e.ivars["pages"]:
                blob = page_script(page)
                if not blob:
                    continue

                for it in find_items(blob):
                    # The same gift usually appears on several pages of one
                    # event (before/after states); count it once.
                    key = (mid, ename, it["item"], it["method"], it["quantity"])
                    if key in seen_p:
                        continue
                    seen_p.add(key)
                    pickups.append({**it, "mapId": mid, "mapName": name, "event": ename})

                for sh in find_shops(blob):
                    key = (mid, tuple(sh["items"]))
                    if key in seen_s:
                        continue
                    seen_s.add(key)
                    shops.append({**sh, "mapId": mid, "mapName": name, "event": ename})

    pickups.sort(key=lambda p: (p["mapId"], p["item"]))
    shops.sort(key=lambda s: (s["mapId"], s["event"]))
    return pickups, shops


def drop_unknown(pickups, shops, known_items):
    """Remove references to item constants that no longer exist.

    pbPokemonMart resolves its stock with getID(PBItems, ...) and drops
    anything that comes back nil, so a few legacy names in the shop scripts
    (PARLYZHEAL, XDEFEND, XSPECIAL) are not actually on sale. Matching that
    keeps the wiki honest rather than listing stock the player cannot buy.
    """
    missing = set()
    kept_p = []
    for p in pickups:
        if p["item"] in known_items:
            kept_p.append(p)
        else:
            missing.add(p["item"])
    kept_s = []
    for s in shops:
        items = [i for i in s["items"] if i in known_items]
        missing.update(i for i in s["items"] if i not in known_items)
        if items:
            kept_s.append({**s, "items": items})
    return kept_p, kept_s, sorted(missing)


def index_by_item(pickups, shops, locations):
    """item internal -> {'found': [...], 'soldAt': [...]} for the item pages."""
    slug_by_map = {}
    for l in locations:
        slug_by_map.setdefault(l["mapId"], l["slug"])

    found, sold = {}, {}
    for p in pickups:
        found.setdefault(p["item"], []).append({
            "mapId": p["mapId"], "mapName": p["mapName"],
            "slug": slug_by_map.get(p["mapId"]),
            "method": p["method"], "quantity": p["quantity"],
            "conditional": p["conditional"],
        })
    for s in shops:
        for item in s["items"]:
            sold.setdefault(item, []).append({
                "mapId": s["mapId"], "mapName": s["mapName"],
                "slug": slug_by_map.get(s["mapId"]),
            })
    # One shop can list an item twice, one town can have two shops, and long
    # routes span several maps under one name. Collapse to what a player sees:
    # one row per place, with a count when it covers several maps.
    for table in (found, sold):
        for k, v in table.items():
            merged = {}
            for e in v:
                sig = (e["mapName"], e.get("method"), e.get("quantity"))
                if sig in merged:
                    merged[sig]["mapCount"] += 1
                else:
                    e["mapCount"] = 1
                    merged[sig] = e
            table[k] = list(merged.values())
    return found, sold
