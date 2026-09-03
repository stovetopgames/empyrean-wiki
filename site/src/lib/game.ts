// Loads the JSON produced by wiki/extract/extract.py. Everything the site
// renders comes from here, so a game patch only needs the extractor re-run.
import pokemonJson from '../../../data/pokemon.json';
import movesJson from '../../../data/moves.json';
import abilitiesJson from '../../../data/abilities.json';
import itemsJson from '../../../data/items.json';
import typesJson from '../../../data/types.json';
import locationsJson from '../../../data/locations.json';
import trainersJson from '../../../data/trainers.json';
import regionsJson from '../../../data/regions.json';
import pickupsJson from '../../../data/pickups.json';
import shopsJson from '../../../data/shops.json';
import gymsJson from '../../../data/gyms.json';
import bossesJson from '../../../data/bosses.json';
import metaJson from '../../../data/meta.json';

export type Stats = {
  hp: number; attack: number; defense: number;
  speed: number; spatk: number; spdef: number;
};

export type Species = {
  number: number; internal: string; name: string; displayName: string; slug: string;
  formNumber: number; formName: string | null; baseSpecies: string; variant: string | null;
  types: string[]; baseStats: Stats; baseStatTotal: number; effortPoints: Stats;
  genderRate: string; malePercent: number | null; femalePercent: number | null;
  growthRate: string; baseEXP: number; catchRate: number; baseHappiness: number;
  abilities: string[]; hiddenAbility: string | null; eggGroups: string[];
  stepsToHatch: number; height: number; weight: number;
  color: string | null; habitat: string | null; kind: string | null; pokedex: string;
  regionalNumbers: number[]; wildItems: string[];
  levelMoves: { level: number; move: string }[];
  eggMoves: string[]; machineMoves: string[];
  evolutions: { to: string; method: string; param: string; text: string }[];
  preEvolutions: { from: string; method: string; param: string; text: string }[];
  familyRoot: string; card: string | null;
  encounters: Encounter[];
  trainers: TrainerAppearance[];
  sprites: Record<string, string | null>;
  hasOwnSprite: boolean; spriteFallback: string | null; implemented: boolean;
  isMega: boolean; megaStone: string | null; isBoss: boolean; isMutant: boolean;
  isFusion: boolean; canFuse: boolean; fusionMove: string | null;
  statScaleKind: string | null; fixedHP: number | null;
  statScale: Record<string, number> | null;
  scaledStats: Record<string, Stats> | null;
  effectiveStats: Stats; effectiveStatTotal: number;
  difficultyPercent: Record<string, number> | null;
};

export type Encounter = {
  mapId: number; location: string; slug: string; regionName: string | null;
  type: string; method: string; chance: number; slots: number;
  minLevel: number; maxLevel: number; mapCount: number;
};

export type EncounterEntry = {
  species: string; chance: number; slots: number; minLevel: number; maxLevel: number;
};

export type EncounterTable = {
  type: string; method: string; density: number | null;
  slotCount: number; expectedSlots: number; entries: EncounterEntry[];
};

export type Location = {
  mapId: number; name: string; slug: string;
  region: number | null; regionName: string | null;
  mapX: number | null; mapY: number | null;
  densityLine: number[] | null; tables: EncounterTable[];
  hasEncounters: boolean; reason: string;
};

export type MapPoint = {
  x: number; y: number; name: string; description: string | null;
  flyMapId: number | null; flyX: number | null; flyY: number | null;
  switch: number | null; slug: string | null; mapId: number | null;
  left: number; top: number; width: number; height: number;
};

export type MapPlace = {
  name: string; slug: string | null; mapId: number | null;
  description: string | null; squares: { x: number; y: number }[];
};

export type Region = {
  index: number; name: string; displayName: string; slug: string;
  filename: string | null; image: string | null;
  width: number; height: number; square: number;
  points: MapPoint[]; places: MapPlace[];
};

export type PartyMon = {
  species: string; level: number; moves: string[]; gender: string | null;
  item: string | null; card: string | null; shiny: boolean;
  abilityIndex: number | null;
};

export type Trainer = {
  slug: string; name: string; displayName: string;
  trainerType: string; trainerTypeId: number;
  mapId: number; mapName: string | null; event: string;
  party: PartyMon[]; gym: number | null; dynamic: boolean;
  partySize: number; maxLevel: number;
};

export type Gym = {
  gym: number; leader: string | null; trainerType: string | null;
  mapId: number | null; mapName: string | null;
  badge: string | null; reward: string | null; levelCap: number | null;
  normal: PartyMon[]; extreme: PartyMon[];
};

export type BossSpot = {
  mapId: number; mapName: string | null; level: number; slug?: string | null;
};

export type Boss = {
  id: string; slug: string; title: string; order: number;
  battleKind: 'trainer' | 'wild';
  name?: string; script?: string;
  trainerTypeId?: number | null; trainerType?: string | null;
  mapId: number; mapName: string | null; locationSlug: string | null;
  regionName: string | null;
  party?: PartyMon[]; partner?: string | null; quote?: string | null;
  species?: string; encounters?: BossSpot[]; recurring: boolean; helper?: string | null;
  partySize: number; minLevel: number; maxLevel: number;
};

export type TrainerAppearance = {
  trainer: string; slug: string; mapName: string | null;
  level: number; slot: number;
};

export type Move = {
  id: number; internal: string; name: string; displayName: string; slug: string;
  functionCode: string;
  power: number; type: string; category: string; accuracy: number; pp: number;
  effectChance: number; target: string; targetText: string; priority: number;
  flags: string; description: string; machine: string | null;
  taughtTo: string[]; tutorHeadings: string[]; levelUpLearners: string[];
  makesContact: boolean; protectable: boolean; soundMove: boolean;
  punchingMove: boolean; biteMove: boolean; bombMove: boolean;
  powderMove: boolean; pulseMove: boolean; highCritRate: boolean;
};

export type Ability = {
  id: number; internal: string; name: string; displayName: string; slug: string;
  description: string; exclusive: boolean;
};

export type Item = {
  id: number; internal: string; name: string; displayName: string; slug: string;
  plural: string;
  pocket: number; pocketName: string; price: number; description: string;
  fieldUse: number; battleUse: number; specialItem: number;
  machine: string | null; isCard: boolean; isMachine: boolean; hasIcon: boolean;
  exclusive: boolean;
  foundAt: ItemSource[]; soldAt: ItemSource[];
};

export type ItemSource = {
  mapId: number; mapName: string | null; slug: string | null;
  method?: string; quantity?: number; conditional?: boolean; mapCount: number;
};

export type Pickup = {
  item: string; quantity: number; method: string; conditional: boolean;
  mapId: number; mapName: string | null; event: string;
};

export type Shop = {
  items: string[]; greeting: string | null;
  mapId: number; mapName: string | null; event: string;
};

export type PType = {
  id: number; name: string; internal: string;
  isPseudoType: boolean; isSpecialType: boolean;
  weaknesses: string[]; resistances: string[]; immunities: string[];
};

export const species = pokemonJson as unknown as Species[];
export const moves = movesJson as unknown as Move[];
export const abilities = abilitiesJson as unknown as Ability[];
export const items = itemsJson as unknown as Item[];
export const types = (typesJson as any).types as PType[];
export const typeChart = (typesJson as any).chart as Record<string, Record<string, number>>;
export const locations = locationsJson as unknown as Location[];
export const trainers = trainersJson as unknown as Trainer[];
export const gyms = gymsJson as unknown as Gym[];
export const bosses = bossesJson as unknown as Boss[];
export const regions = regionsJson as unknown as Region[];
export const pickups = pickupsJson as unknown as Pickup[];
export const shops = shopsJson as unknown as Shop[];
export const meta = metaJson as any;

export const speciesByInternal = new Map(species.map((s) => [s.internal, s]));
export const movesByInternal = new Map(moves.map((m) => [m.internal, m]));
export const abilitiesByInternal = new Map(abilities.map((a) => [a.internal, a]));
export const itemsByInternal = new Map(items.map((i) => [i.internal, i]));
export const typesByInternal = new Map(types.map((t) => [t.internal, t]));

export const slug = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'x';

// Slugs and display names are assigned by the extractor so that the static site
// and the MediaWiki export agree on every URL and page title.
export const moveSlug = (m: Move | string) => {
  const mv = typeof m === 'string' ? movesByInternal.get(m) : m;
  return mv ? mv.slug : slug(String(m));
};
export const abilitySlug = (a: Ability | string) => {
  const ab = typeof a === 'string' ? abilitiesByInternal.get(a) : a;
  return ab ? ab.slug : slug(String(a));
};
export const itemSlug = (i: Item | string) => {
  const it = typeof i === 'string' ? itemsByInternal.get(i) : i;
  return it ? it.slug : slug(String(i));
};

export const typeName = (internal: string) => typesByInternal.get(internal)?.name ?? internal;
export const moveName = (internal: string) => movesByInternal.get(internal)?.displayName ?? internal;
export const abilityName = (internal: string) => abilitiesByInternal.get(internal)?.displayName ?? internal;
export const itemName = (internal: string) => itemsByInternal.get(internal)?.displayName ?? internal;
export const speciesName = (internal: string) =>
  speciesByInternal.get(internal)?.displayName ?? internal;

export const STAT_LABELS: [keyof Stats, string][] = [
  ['hp', 'HP'], ['attack', 'Attack'], ['defense', 'Defense'],
  ['spatk', 'Sp. Atk'], ['spdef', 'Sp. Def'], ['speed', 'Speed'],
];

/** Combined damage multiplier taken by a defender with these types. */
export function defensiveMultiplier(attacking: string, defending: string[]): number {
  return defending.reduce((acc, d) => acc * (typeChart[attacking]?.[d] ?? 1), 1);
}

/** Full matchup summary for a defending type combination. */
export function matchups(defending: string[]) {
  const out: Record<string, string[]> = { '4': [], '2': [], '0.5': [], '0.25': [], '0': [] };
  for (const t of types) {
    if (t.isPseudoType) continue;
    const m = defensiveMultiplier(t.internal, defending);
    if (m === 1) continue;
    const key = String(m);
    if (out[key]) out[key].push(t.internal);
    else out[key] = [t.internal];
  }
  return out;
}

/** Every species in the same evolution family, ordered from the root. */
export function family(s: Species): Species[] {
  const root = speciesByInternal.get(s.familyRoot) ?? s;
  const seen = new Set<string>();
  const out: Species[] = [];
  const walk = (node: Species) => {
    if (seen.has(node.internal)) return;
    seen.add(node.internal);
    out.push(node);
    for (const e of node.evolutions) {
      const next = speciesByInternal.get(e.to);
      if (next) walk(next);
    }
  };
  walk(root);
  return out;
}

/** Pokémon that can learn a given move, split by how they learn it. */
export function learners(move: Move) {
  const byLevel: { s: Species; level: number }[] = [];
  const byEgg: Species[] = [];
  const byMachine: Species[] = [];
  for (const s of species) {
    const lm = s.levelMoves.find((x) => x.move === move.internal);
    if (lm) byLevel.push({ s, level: lm.level });
    if (s.eggMoves.includes(move.internal)) byEgg.push(s);
    if (s.machineMoves.includes(move.internal)) byMachine.push(s);
  }
  byLevel.sort((a, b) => a.level - b.level || a.s.number - b.s.number);
  return { byLevel, byEgg, byMachine };
}

export const locationsBySlug = new Map(locations.map((l) => [l.slug, l]));

/** Items lying around or handed over on a given map. */
export function pickupsAt(mapId: number) {
  return pickups.filter((p) => p.mapId === mapId);
}

/** Shops on a given map. */
export function shopsAt(mapId: number) {
  return shops.filter((s) => s.mapId === mapId);
}

/** Trainers standing in a given map, for the location pages. */
export function trainersAt(mapId: number) {
  return trainers.filter((t) => t.mapId === mapId);
}

/** The region map a place appears on, if any, plus its place entry. */
export function regionFor(slug: string) {
  for (const r of regions) {
    const place = r.places.find((p) => p.slug === slug);
    if (place) return { region: r, place };
  }
  return null;
}

/** Locations grouped by region, in the order regions appear on the town map. */
export function locationsByRegion() {
  const groups = new Map<string, Location[]>();
  for (const l of locations) {
    const key = l.regionName ?? 'Other';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(l);
  }
  return [...groups.entries()].sort((a, b) => {
    if (a[0] === 'Other') return 1;
    if (b[0] === 'Other') return -1;
    return b[1].length - a[1].length;
  });
}

export const realItems = items.filter((i) => !i.isCard);
export const cardItems = items.filter((i) => i.isCard);
