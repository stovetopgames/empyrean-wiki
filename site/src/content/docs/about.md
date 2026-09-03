---
title: About this wiki
description: How the Pokémon Empyrean wiki is generated from the game files, and how to rebuild it for a new version.
---

This wiki is **generated from the game's own data files**, not written by hand. Every
stat, learnset, price and type matchup on the site is read out of the game and rendered
automatically, so the whole wiki can be rebuilt in about a minute when the game updates.

## Where the data comes from

| Source | What it provides |
| --- | --- |
| `PBS/pokemon.txt`, `pokemonforms.txt` | Species, forms, stats, learnsets, evolutions, Pokédex entries |
| `PBS/moves.txt` | Move power, accuracy, PP, priority, targets and flags |
| `PBS/abilities.txt` | Ability names and effects |
| `PBS/items.txt` | Items, prices, bag pockets, TM/HM move bindings |
| `PBS/tm.txt` | TM, HM and move tutor compatibility |
| `PBS/types.txt` | The full type chart, including Empyrean's custom types |
| `PBS/encounters.txt`, `metadata.txt` | Wild encounter tables, map regions |
| `PBS/townmap.txt`, `Graphics/Pictures/mapRegion*.png` | Region maps and their clickable places |
| `Data/MapInfos.rxdata`, `Data/Map*.rxdata` | Area names, trainer battles, badge events, item pickups, shop stock |
| `Data/Scripts.rxdata` | Gym teams (both difficulties), gym leaders, level caps |
| `Graphics/Battlers`, `Graphics/Icons`, `Graphics/Pictures` | Sprites, party icons, type badges |

## Accuracy notes

A few details are easy to get wrong by reading the PBS files casually, so they are
worth stating:

- **Type effectiveness precedence.** The game's compiler applies weakness, then
  resistance, then immunity, each overwriting the last. A type listed under both
  `Weaknesses` and `Resistances` therefore ends up resisted. This affects Ice
  attacking Water/Ground, which is **0.5×**, not 2×.
- **Base stat order.** `BaseStats` in the PBS files is HP, Attack, Defense, **Speed**,
  Sp. Atk, Sp. Def — Speed sits in the middle, not at the end.
- **Variant names.** Empyrean reuses the original names for its variants, so 79 species
  share a name with another entry. Regional variants are labelled here as
  *Omuran* and *Deshret*; boss and event forms get their own qualifiers.
- **What counts as "Empyrean's own".** The Abilities and Items pages split new
  content from the standard set. This is read off the id ranges the game's
  author reserved, not guessed: abilities run 1–232 (the official set) and then
  jump to 300+, and items keep the stock list in 1–525, the Gen 7 additions in
  700–706 and the Mega Stones in 726–766. That gives 18 new abilities and 355 new
  items (plus the 2,570 cards). A few stock items are only *renamed* — Stardust is
  "Red Stardust", the Coin Case is the "Token Pouch" — and they keep their
  official id, so they correctly stay out of the new list.
- **Mega and form data.** Most Megas declare their stats, ability and typing in
  the game's Ruby (`MultipleForms.register`), not in the PBS files, and some
  forms exist only there. Both sources are read, so a Mega shows its own
  ability rather than its base species'.
- **Boss-tier stats are not the base stats.** Mutant and Alpha species have
  their base multiplied by 9, Fusions by 5 and Dream species by 3, adjusted by
  difficulty, and 14 named bosses have their HP replaced outright. The stat
  block shows what you actually face on Normal, with a note for the Easy and
  Extreme difference, rather than the raw file values.
- **Shop stock that does not exist.** `pbPokemonMart` drops any item constant
  it cannot resolve, so six legacy names left in the event scripts are not
  really on sale. They are left out here for the same reason.
- **Unobtainable species.** Some species exist in the data with no sprite. The game's
  own randomizer script excludes them, so they are flagged as not obtainable rather
  than presented as catchable.

## Rebuilding after a game update

```bash
python wiki/extract/extract.py        # PBS + scripts -> wiki/data/*.json
python wiki/extract/export_assets.py  # sprites -> wiki/site/public/
cd wiki/site && npm run build         # JSON -> static site in dist/
```

The JSON in `wiki/data/` is the single source of truth. It is plain, documented data,
so it can also drive damage calculators, team builders or tracker tools — and a second
renderer turns the same files into MediaWiki import XML.
