#!/usr/bin/env python
"""Export the sprites the wiki needs out of Graphics/ into the site's public dir.

Battler sheets are copied as-is; party icons are 2-frame strips so only the
first frame is kept; the type badges are sliced out of the single types.png
sheet. Everything is keyed by the slug in pokemon.json so the renderers can
build image paths without another lookup table.
"""
import json
import os
import re
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
GFX = os.path.join(ROOT, "Graphics")
DATA = os.path.join(ROOT, "wiki", "data")
PUBLIC = os.path.join(ROOT, "wiki", "site", "public")

ICON_FRAME = (0, 0, 64, 64)   # party icons are 128x64: two 64x64 frames
TYPE_SHEET_H = 28             # types.png is 64 x (28 * type count)


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def ensure(*parts):
    p = os.path.join(PUBLIC, *parts)
    os.makedirs(p, exist_ok=True)
    return p


def copy_png(src, dst):
    if not os.path.exists(src):
        return False
    shutil.copyfile(src, dst)
    return True


def crop_first_frame(src, dst):
    if not os.path.exists(src):
        return False
    with Image.open(src) as im:
        im = im.convert("RGBA")
        box = ICON_FRAME
        if im.width < box[2] or im.height < box[3]:
            box = (0, 0, min(im.width, 64), min(im.height, 64))
        im.crop(box).save(dst, optimize=True)
    return True


def icon_from_battler(src, dst):
    """Derive a 64x64 party icon from a battler sheet.

    267 of the custom species have a battler but no party icon of their own, so
    trim the transparent margin and scale the sprite to fit an icon-sized box.
    """
    if not os.path.exists(src):
        return False
    with Image.open(src) as im:
        im = im.convert("RGBA")
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
        im.thumbnail((64, 64), Image.LANCZOS)
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        canvas.paste(im, ((64 - im.width) // 2, (64 - im.height) // 2))
        canvas.save(dst, optimize=True)
    return True


def placeholder(size):
    """Neutral "unknown sprite" tile for the species that ship no graphics."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = max(2, size // 10)
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=size // 8,
                        outline=(140, 140, 155, 190), width=max(1, size // 32))
    text = "?"
    try:
        bbox = d.textbbox((0, 0), text)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text,
               fill=(140, 140, 155, 220))
    except Exception:
        pass
    return im


def export_pokemon():
    species = load("pokemon.json")
    sprites_dir = ensure("sprites")
    icons_dir = ensure("icons")
    n_front = n_shiny = n_icon = n_derived = 0
    for s in species:
        sp = s["sprites"]
        front_src = os.path.join(GFX, *sp["front"].split("/")) if sp.get("front") else None
        if front_src and copy_png(front_src, os.path.join(sprites_dir, s["slug"] + ".png")):
            n_front += 1
        if sp.get("shinyFront") and copy_png(os.path.join(GFX, *sp["shinyFront"].split("/")),
                                             os.path.join(sprites_dir, s["slug"] + "-shiny.png")):
            n_shiny += 1
        icon_dst = os.path.join(icons_dir, s["slug"] + ".png")
        if sp.get("icon") and crop_first_frame(os.path.join(GFX, *sp["icon"].split("/")), icon_dst):
            n_icon += 1
        elif front_src and icon_from_battler(front_src, icon_dst):
            n_derived += 1

    # Species with no graphics at all still get a page (flagged unobtainable),
    # so give them a placeholder rather than a broken image.
    ph_big, ph_small = placeholder(160), placeholder(64)
    n_ph = 0
    for s in species:
        for path, img in ((os.path.join(sprites_dir, s["slug"] + ".png"), ph_big),
                          (os.path.join(sprites_dir, s["slug"] + "-shiny.png"), ph_big),
                          (os.path.join(icons_dir, s["slug"] + ".png"), ph_small)):
            if not os.path.exists(path):
                img.save(path, optimize=True)
                n_ph += 1
    print("  pokemon:  %4d fronts, %4d shinies, %4d icons (+%d derived, %d placeholders)"
          % (n_front, n_shiny, n_icon, n_derived, n_ph))


def export_items():
    items = load("items.json")
    out = ensure("items")
    n = 0
    for it in items:
        src = os.path.join(GFX, "Icons", "item%03d.png" % it["id"])
        if copy_png(src, os.path.join(out, "%d.png" % it["id"])):
            n += 1
    print("  items:    %4d icons" % n)


def export_types():
    types = load("types.json")["types"]
    sheet_path = os.path.join(GFX, "Pictures", "types.png")
    if not os.path.exists(sheet_path):
        print("  types:    types.png not found, skipped")
        return
    out = ensure("types")
    n = 0
    with Image.open(sheet_path) as sheet:
        sheet = sheet.convert("RGBA")
        for t in types:
            top = t["id"] * TYPE_SHEET_H
            if top + TYPE_SHEET_H > sheet.height:
                continue
            sheet.crop((0, top, sheet.width, top + TYPE_SHEET_H)).save(
                os.path.join(out, re.sub(r"[^a-z0-9]+", "-", t["internal"].lower()) + ".png"),
                optimize=True)
            n += 1
    print("  types:    %4d badges" % n)


def export_regions():
    """Region map images, named by region index to match regions.json."""
    try:
        regions = load("regions.json")
    except OSError:
        print("  regions:  regions.json not found, skipped")
        return
    out = ensure("regions")
    n = 0
    for r in regions:
        if not r.get("filename"):
            continue
        src = os.path.join(GFX, "Pictures", r["filename"])
        if copy_png(src, os.path.join(out, "%d.png" % r["index"])):
            n += 1
    print("  regions:  %4d maps" % n)


def main():
    if not os.path.isdir(DATA):
        sys.exit("run extract.py first")
    print("Exporting assets to %s\n" % PUBLIC)
    export_pokemon()
    export_items()
    export_types()
    export_regions()
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(PUBLIC) for f in fs)
    print("\n  total: %.1f MB" % (total / 1024.0 / 1024.0))


if __name__ == "__main__":
    main()
