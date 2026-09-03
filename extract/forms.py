"""Form data that lives in scripts rather than PBS/pokemonforms.txt.

Most Mega Evolutions and several custom forms are declared in Ruby, not in the
PBS files:

    MultipleForms.register(:SHUCKLE,{
    "getMegaForm"=>proc{|pokemon|
       next 1 if isConst?(pokemon.item,PBItems,:SHUCKLE_STONE)
       next
    },
    "getAbilityList"=>proc{|pokemon|
       next [[getID(PBAbilities,:SEXYBACK),0]] if pokemon.form==1
       next
    },
    "getBaseStats"=>proc{|pokemon|
       next [250,250,150,100,250,150] if pokemon.form==1
       next
    }
    })

pokemonforms.txt has no SHUCKLE-1 at all, so without reading this the form is
missing entirely; where a PBS entry does exist, the script still overrides its
stats, abilities and types. This module turns those blocks into plain data.
"""
import re

# Every script is scanned rather than a fixed list: fusion forms live in
# Pokemon_FusionEvolution, and naming the files individually meant they were
# silently skipped. Anything that registers a form is picked up wherever it is.

REGISTER = re.compile(r"MultipleForms\.register\(:(\w+)\s*,\s*\{")
PROC = re.compile(r'"(\w+)"\s*=>\s*proc\s*\{')
# `next <value> if pokemon.form==N`
NEXT_FORM = re.compile(r"next\s+(.+?)\s+if\s+pokemon\.form\s*==\s*(\d+)", re.S)
# `next N if isConst?(pokemon.item,PBItems,:STONE)`
NEXT_STONE = re.compile(
    r"next\s+(\d+)\s+if\s+isConst\?\(\s*pokemon\.item\s*,\s*PBItems\s*,\s*:(\w+)")
INT_LIST = re.compile(r"^\[\s*(-?\d+(?:\s*,\s*-?\d+)*)\s*\]$")
GETID = re.compile(r"getID\(\s*PB\w+\s*,\s*:(\w+)\s*\)")


def _balanced(text, start, opener="{", closer="}"):
    depth, i = 1, start
    while i < len(text) and depth:
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
        i += 1
    return None if depth else i - 1


def _blocks(src):
    """Yield (species, body) for each MultipleForms.register call."""
    for m in REGISTER.finditer(src):
        end = _balanced(src, m.end())
        if end is None:
            continue
        yield m.group(1), src[m.end():end]


def _procs(body):
    """Yield (key, proc body) for each "key"=>proc{...} in a register block."""
    for m in PROC.finditer(body):
        end = _balanced(body, m.end())
        if end is None:
            continue
        yield m.group(1), body[m.end():end]


def _stats(value):
    m = INT_LIST.match(value.strip())
    if not m:
        return None
    nums = [int(x) for x in m.group(1).split(",")]
    return nums if len(nums) == 6 else None


def _abilities(value):
    """[[getID(PBAbilities,:HUGEPOWER),0]] -> ["HUGEPOWER"]"""
    names = GETID.findall(value)
    return names or None


def parse(scripts):
    """-> {SPECIES: {formNumber: {field: value}}} plus mega stone info."""
    out = {}
    for name, src in scripts.items():
        if "MultipleForms.register" not in src:
            continue
        for species, body in _blocks(src):
            forms = out.setdefault(species, {})
            # `"isFusion"=>proc{ next true }` carries no form test, so it marks
            # every form the block defines. Applied after the procs are read,
            # since it can appear before the forms themselves.
            fusion_block = False
            for key, proc in _procs(body):
                if key == "isFusion":
                    fusion_block = True
                    continue
                if key == "getMegaForm":
                    for num, stone in NEXT_STONE.findall(proc):
                        f = forms.setdefault(int(num), {})
                        f["megaStone"] = stone
                        f["isMega"] = True
                    continue
                if key == "getMegaName":
                    # Names are per form: Charizard has both an X and a Y.
                    for value, num in NEXT_FORM.findall(proc):
                        m = re.search(r'_INTL\("([^"]+)"\)', value)
                        if m:
                            forms.setdefault(int(num), {})["megaName"] = m.group(1)
                    continue

                for value, num in NEXT_FORM.findall(proc):
                    value = value.strip().rstrip(",")
                    f = forms.setdefault(int(num), {})
                    if key in ("getBaseStats", "baseStats"):
                        s = _stats(value)
                        if s:
                            f["baseStats"] = s
                    elif key == "getAbilityList":
                        a = _abilities(value)
                        if a:
                            f["abilities"] = a
                    elif key in ("type1", "type2"):
                        t = GETID.findall(value)
                        if t:
                            f[key] = t[0]
                    elif key in ("height", "weight"):
                        if re.match(r"^-?\d+$", value):
                            # Essentials stores decimetres / hectograms.
                            f[key] = int(value) / 10.0
                    elif key == "evYield":
                        s = _stats(value)
                        if s:
                            f["effortPoints"] = s
                    elif key == "kind":
                        m = re.search(r'_INTL\("([^"]+)"\)', value)
                        if m:
                            f["kind"] = m.group(1)

            if fusion_block:
                # A fusion block can also hold ordinary forms - Aegislash
                # registers Blade Forme alongside its fusion - so only the
                # forms a fusion stone actually triggers count.
                for f in forms.values():
                    if f.get("megaStone"):
                        f["isFusion"] = True
    return out


def fusion_data(scripts):
    """Species that can fuse, and the exclusive move each one gains."""
    src = scripts.get("Pokemon_FusionEvolution", "")
    capable = set()
    m = re.search(r"def isFusionCapable\?(.*?)\nend", src, re.S)
    if m:
        capable = set(re.findall(r"PBSpecies::(\w+)", m.group(1)))
    moves = {}
    m = re.search(r"def getFusionExclusiveMove.*?\{(.*?)\}", src, re.S)
    if m:
        for sp, mv in re.findall(r"PBSpecies::(\w+)\s*=>\s*PBMoves::(\w+)", m.group(1)):
            moves[sp] = mv
    return capable, moves


def stat_scaling(scripts):
    """How PokeBattle_Pokemon inflates boss-tier stats before the usual formula.

    calcStat and calcHP both start with:

        mutmult = mutantStatModifier()          # 0.8 easy / 1.0 / 1.3 extreme
        base *= (9 * mutmult).floor if isMutantSpecies? || isAlphaSpecies?
        base *= (5 * mutmult).floor if isFoeFusion?
        base *= 3 if $DREAM_FIELD && isDreamSpecies?

    and each of those predicates is just the species' Kind field. calcHP also
    short-circuits to a fixed number for named bosses, so their HP has nothing
    to do with the PBS value at all.
    """
    out = {
        "difficulty": {"easy": 0.8, "normal": 1.0, "extreme": 1.3},
        "kindFactor": {"Mutant": 9, "Alpha": 9, "Fusion": 5, "Dream": 3},
        "dreamNeedsField": True,
        "fixedHP": {},
    }

    # Named integer constants, so DEUS_HEALTH etc. can be resolved.
    consts = {}
    for src in scripts.values():
        for m in re.finditer(r"^\s*([A-Z][A-Z0-9_]{2,})\s*=\s*(\d+)\s*$", src, re.M):
            consts.setdefault(m.group(1), int(m.group(2)))

    src = scripts.get("PokeBattle_Pokemon", "")
    m = re.search(r"def calcHP.*?\n(?:.*?\n)*?^  end", src, re.M)
    if not m:
        return out
    body = m.group(0)

    for expr, species in re.findall(
            r"return\s+(?:mul\s*\*\s*)?([A-Za-z0-9_]+)\s+if\s+species\s*==\s*PBSpecies::(\w+)",
            body):
        if expr.isdigit():
            out["fixedHP"][species] = int(expr)
        elif expr in consts:
            out["fixedHP"][species] = consts[expr]
    return out


def boss_species(scripts):
    """The species isBossPokemon? returns true for."""
    src = scripts.get("BossPokemonDataBox", "")
    m = re.search(r"def isBossPokemon\?.*?\n\s*\]\.include\?", src, re.S)
    if not m:
        return set()
    return set(re.findall(r"PBSpecies::(\w+)", m.group(0)))


def gp_constants(scripts):
    """MAXIMUM_GP and GP_BOOST from the GP script, for the scaling note."""
    src = scripts.get("GP", "")
    out = {}
    m = re.search(r"MAXIMUM_GP\s*=\s*(\d+)", src)
    if m:
        out["maxGP"] = int(m.group(1))
    m = re.search(r"GP_BOOST\s*=\s*([\d.]+)", src)
    if m:
        out["gpBoost"] = float(m.group(1))
    return out
