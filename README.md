# Pokémon Empyrean Wiki

A wiki generated directly from the game's own files. Nothing is transcribed by
hand, so the whole thing can be rebuilt in about 90 seconds whenever the game
updates — which is the reason the existing hand-maintained wiki fell behind.

```
wiki/
├── build.py              one command to rebuild everything
├── extract/              game files  ->  wiki/data/*.json
│   ├── marshal48.py        reads RPG Maker XP .rxdata (Ruby Marshal 4.8)
│   ├── pbs.py              parsers for the PBS text formats
│   ├── locations.py        wild encounters, map names, regions
│   ├── townmap.py          region maps and their clickable points
│   ├── trainers.py         trainer battles, gym teams, badges
│   ├── pickups.py          item pickups and shop stock
│   ├── forms.py            form data declared in Ruby, not PBS
│   ├── extract.py          the extractor
│   └── export_assets.py    sprites, party icons, type badges
├── data/                 canonical JSON — the single source of truth
├── site/                 renderer 1: Astro + Starlight static site
├── render/mediawiki.py   renderer 2: MediaWiki import XML
└── out/                  generated XML + image upload manifest
```

## Rebuild

```bash
python wiki/build.py           # everything
python wiki/build.py --data    # just re-extract the JSON
python wiki/build.py --site    # data + assets + static site
python wiki/build.py --wiki    # data + MediaWiki XML
```

Requirements: Python 3.9+ with Pillow (`pip install pillow`) and Node 22.12+
(Astro 7 refuses to build on anything older).

Every build also runs `check_links.py`, which fails if any internal link is
broken or omits the base path. A hardcoded `/pokedex/` works locally and 404s
on GitHub Pages, so it needs to break the build rather than reach the site.
In markdown use `<a href={`${base}/...`}>`; only `astro.config.mjs` hero
actions use relative links.

## What gets extracted

| Entity | Count | Source |
| --- | --- | --- |
| Species | 972 | `PBS/pokemon.txt` |
| Alternate forms | 163 (59 Megas) | `pokemonforms.txt` + `MultipleForms.register` |
| Moves | 808 | `PBS/moves.txt` |
| Abilities | 250 (18 new to Empyrean) | `PBS/abilities.txt` |
| Items | 3,497 (355 new to Empyrean, 2,570 cards, 125 machines) | `PBS/items.txt` |
| Types | 26 | `PBS/types.txt` |
| Locations | 251 (124 with wild encounters, 207 tables) | `PBS/encounters.txt` + `Data/MapInfos.rxdata` |
| Region maps | 6, 147 clickable places | `PBS/townmap.txt` + `Graphics/Pictures` |
| Trainer battles | 347 (885 Pokémon) | `Data/Map*.rxdata` |
| Item pickups | 263 across 172 items | `Data/Map*.rxdata` |
| Shops | 98, stocking 231 items | `Data/Map*.rxdata` |
| Gyms | 8, Normal + Extreme teams | `Data/Scripts.rxdata` |
| TM/tutor compatibility | 204 move lists | `PBS/tm.txt` |
| Sprites, icons, type badges | ~2,100 files | `Graphics/` |

## Publishing to GitHub Pages

**This folder is the repo.** Keeping the repo root at `wiki/` means the game's
700 MB of assets can never be committed by accident, and the workflow paths
assume it.

Create an empty repo called `empyrean-wiki` on github.com under the
**stovetopgames** account (no README, no .gitignore), then:

```bash
cd wiki
git remote add origin https://github.com/stovetopgames/empyrean-wiki.git
git push -u origin main
```

Then in the repo: **Settings -> Pages -> Source: GitHub Actions**. The included
workflow builds and deploys on every push to `main`, and the site lands at
`https://stovetopgames.github.io/empyrean-wiki/`.

About 13 MB is committed: `data/*.json`, `site/public/` and the source. The
extractor is *not* run in CI, because it needs the game files; run
`python build.py` locally after a change and commit the updated JSON and
sprites.

### Beta mode: reachable by link, invisible to search

Set a repository variable **`NOINDEX`** to `1` (Settings -> Secrets and
variables -> Actions -> Variables). The build then adds
`<meta name="robots" content="noindex, nofollow">` to every page and ships a
`robots.txt` that disallows everything. Remove the variable and re-run the
workflow to go public.

Be clear about what this is: the site is still **publicly reachable** by anyone
with the URL. It keeps the wiki out of Google, but it is not a login. GitHub
Pages has no access control except on Enterprise Cloud, and a private repo only
hides the *source*, not the published site.

If you need people to actually authenticate, deploy the same `site/dist/` to
**Cloudflare Pages** and put **Cloudflare Access** in front of it. The Zero
Trust free tier covers a small team, and gates the site behind an email
one-time-code or a Google/GitHub login. Netlify and Vercel both offer password
protection, but only on their paid tiers.

## Importing into MediaWiki (wiki.gg, Miraheze, self-hosted)

`python wiki/build.py --wiki` writes `wiki/out/`:

- `empyrean-templates.xml` — Main Page, `Template:Infobox Pokemon`,
  `Template:Stats`, `Template:Type`, the type chart and per-type pages.
  **Import this first**, so the other pages have their templates.
- `empyrean-pokemon-*.xml`, `empyrean-moves-*.xml`, `empyrean-abilities.xml`,
  `empyrean-items.xml`, `empyrean-locations.xml`, `empyrean-gyms.xml`,
  `empyrean-trainers.xml` — 3,606 content pages, chunked under the ~2 MB
  `Special:Import` upload cap. With shell access,
  `php maintenance/importDump.php <file>` skips the chunking concern.
- `upload-manifest.csv` — every image the pages reference and its path on
  disk. XML dumps never contain files, so upload these separately
  (`Special:Upload`, `Extension:SimpleBatchUpload`, or pywikibot's
  `upload.py`).

Page titles match the static site's, so both renderers stay consistent.

## Accuracy notes

Details that are easy to get wrong when reading the PBS files by eye:

- **Type effectiveness precedence.** `Compiler#pbCompileTypes` assigns weakness,
  then resistance, then immunity, each overwriting the last. A type listed under
  both `Weaknesses` and `Resistances` therefore ends up **resisted**. This
  affects exactly one matchup: Ice attacking Water/Ground is 0.5×, not 2×.
- **Base stat order** is HP, Attack, Defense, **Speed**, Sp. Atk, Sp. Def —
  Speed sits in the middle.
- **Variant naming.** Empyrean reuses vanilla names for its variants, so 79
  species share a name. The extractor qualifies them from their internal-name
  prefix: `OM_` → Omuran, `DR_` → Deshret, `DATA_` → Data, `B_` → Boss, and so
  on. The unprefixed entry keeps the bare name.
- **Unobtainable species.** 42 species have no sprite; the game's own
  `Randomizer` script excludes them ("I don't have backsprites for ..."). They
  are flagged `implemented: false` and marked on their pages rather than being
  presented as catchable.
- **Duplicate data.** `moves.txt` contains the `LEAFAGE` row twice, and
  `encounters.txt` defines map 724 three times. The game keeps the last
  definition in both cases (`encounters[mapid] = thisenc`), and so does this.
- **Encounter rates** come from `EncounterTypes::EnctypeChances`. Cave uses the
  twelve-slot Land spread here, not the five-slot one. All 124 maps and the
  full 26x26 type chart are validated against the game's own compiled
  `Data/encounters.dat` and `Data/types.dat`.
- **Trainer teams** are read out of the event scripts (99.2% of `createTrainer`
  calls resolve). The three that do not are Net Fortress battles whose party
  comes from a server.
- **Region map hotspots** come from `townmap.txt` `Point` entries, one per
  16x16 square (`SQUAREWIDTH` in `PScreen_RegionMap`). A point is matched to a
  page by its printed name first; its fly target is only a fallback, because
  the two can differ — "Cycling Highway" flies you to Cape Naraku. 196 of 264
  points resolve to a page.
- **New vs standard content.** `exclusive` on each ability and item marks
  Empyrean's own additions, derived from the reserved id ranges the author used
  (abilities 300+; items outside 1–525, 700–706 and 726–766). The ranges are
  constants at the top of `extract.py`, so they are easy to correct if the game
  reorganises them.
- **Forms are half-defined in Ruby.** Most Megas and every Fusion set their
  stats, ability and typing in `MultipleForms.register` rather than in
  `pokemonforms.txt`, and 38 forms (Mega Shuckle among them) exist *only*
  there. Every script is scanned for those blocks, not a hardcoded list -
  fusions live in `Pokemon_FusionEvolution` and were missed when it was. Reading just the PBS
  files gives a Mega its base species' stats and makes its ability look unused,
  which is what players reported. `forms.py` parses those blocks.
- **Unreachable form leftovers.** `pokemonforms.txt` keeps entries the game can
  no longer produce: `CHARIZARD-3` is a second "Mega Charizard Y" but
  `getMegaForm` only ever returns 1 or 2. Forms with no sprite whose name a
  script-defined Mega already claims are dropped.
- **Boss-tier stats are not the PBS stats.** `calcStat` and `calcHP` multiply
  the base by 9 for a Mutant or Alpha, 5 for a Fusion and 3 for a Dream species
  (all read off the `Kind` field), scaled again by difficulty: x0.8 easy, x1.3
  extreme. `calcHP` also replaces HP outright for 14 named bosses - Zineom is
  10,000 HP, Corruption 9,999 - so their HP has no relation to the PBS value.
  The stat block shows the Normal-difficulty result for those 60 species, with
  a line noting the Easy and Extreme difference, since that is the number a
  player actually meets. `baseStats` in the JSON keeps the raw PBS values;
  `effectiveStats` is what the pages render.
- **Dead shop stock.** `pbPokemonMart` resolves its list with
  `getID(PBItems, ...)` and silently drops anything that comes back nil, so six
  legacy constants in the event scripts (`PARLYZHEAL`, `XDEFEND`, `XSPECIAL`
  and friends) are not actually on sale. They are dropped here too rather than
  listing stock a player cannot buy.
- **Locations are a superset of encounter areas.** A place gets a page if it
  has wild encounters, has trainers, has an item to pick up or a shop, or is
  named on a region map, so the maps and item pages have somewhere to point. `hasEncounters` distinguishes them.

## Using the data elsewhere

`wiki/data/*.json` is plain, documented JSON with stable keys, so it can also
drive a damage calculator, team builder or tracker without touching the game
files. Every entity carries a unique `slug` and `displayName`, and species
records include resolved learnsets, evolution text and sprite paths.
