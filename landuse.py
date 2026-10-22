"""Land use: the land changes with the people on it.

A country at peace with the zombies (safe, fed, nothing threatening it) that has filled its land up builds on it:
  clearing     forest (and jungle, slower) next to its farmland is cleared for fields (CLEAR_CHANCE);
  suburbs      full farmland next to a town fills up with houses: it becomes suburbs (SUBURB_CHANCE);
  cities       crowded suburbs in the middle of a town become city (CITY_CHANCE);
  new towns    now and then a full farming district grows into a market town - where a town makes sense: on the coast,
               on the ruins of an old city, by the hills (a strongpoint), on good land, away from other towns - one
               or two per country at a time, at irregular distances (TOWN_*), with a ragged first footprint;
  suburbs grow outward unevenly, more where the land and the lie of it favour them (SUBURB_RAGGED) - towns
               don't come out as a lattice of identical crosses;
  villages     a village nobody governs that has grown full becomes a town of its own (VILLAGE_TOWN);
- never past URBAN_MAX of its land built up (or what it had before, if more): the continent doesn't become one city.
Land nobody lives on goes the other way, wherever it is:
  ruins        a city empty for RUIN_DAYS is a ruin - suburbs at best; suburbs empty for FADE_DAYS are fields again;
  wild         fields empty for WILD_DAYS next to woods are woods again.
How many people a tile is rebuilt to (restart.home) follows its land: what it held before the outbreak to begin with,
then what its new land holds (FARM_HOME, SUBURB_HOME, CITY_HOME; a ruin less than the city it was) - so a country
rebuilds where it builds, not just where its people happened to live before.
"""
import numpy as np

from terrain import GRASS, FOREST, RAINFOREST, URBAN, SUBURBAN
from civilization import box_sum

EVERY = 25
CLEAR_CHANCE = 0.05        # per check, a forest tile next to 3+ full fields (rainforest: half as often)
SUBURB_CHANCE = 0.06       # per check, a full farm tile next to 2+ built-up tiles
CITY_CHANCE = 0.03         # per check, a full suburb next to 4+ built-up tiles, at least one of them city
TOWN_CHANCE = 0.006        # per check, per country: a new town (at most TOWN_MAX), on the best site going ...
TOWN_MAX = 2
TOWN_APART = 3             # ... never this close to a built-up tile, and less likely the more is built within TOWN_FAR
TOWN_FAR = 9
TOWN_COAST, TOWN_RUIN, TOWN_HILLS = 1.5, 1.2, 0.6     # (what makes a good site, against 1.0 for plain farmland)
TOWN_TILES = (1, 4)        # tiles of its first footprint
SUBURB_RAGGED = 0.8        # suburbs grow x (1 +- this), varying from place to place (civilization.fine_jag)
VILLAGE_TOWN = 0.02        # per check, a full village (VILLAGE_TOWN_POP people within 2 tiles) that becomes a town
VILLAGE_TOWN_POP = 150
URBAN_MAX = 0.08           # built-up share of a country's land it never builds past (unless it had more before)
FULL = 0.85                # a tile counts as full at this share of what it is rebuilt to
COUNTRY_FULL = 0.7         # a country builds once its people fill this share of what its land is rebuilt to
SAFE_THREAT = 0.1          # ... and its danger is below this
RUIN_DAYS = 300
FADE_DAYS = 500
WILD_DAYS = 900
WILD_CHANCE = 0.1
HIT = 0.15                 # a country rebuilds this way once it has lost this share of its people (or is a state
                           # founded since the outbreak): before that it lives the way it always did
FARM_HOME, SUBURB_HOME, CITY_HOME, WOOD_HOME = 55, 140, 220, 25


def home(world):
    """How many people each tile is rebuilt to (created from the pre-outbreak population on first use)."""
    h = getattr(world, "home_cap", None)
    if h is None or h.shape != world.H.shape:
        h = world.home_cap = np.asarray(world.H0, dtype=np.int32).copy()
    return h


def recovering(c):
    """A living government rebuilding after the outbreak: it has lost HIT of its people at some point (or was founded
    since).  Kept up to date here (and by restart.villages)."""
    if not (c.id and c.ai and not c.collapsed and c.m and c.m.get("n")):
        return False
    c._worst_damage = max(getattr(c, "_worst_damage", 0.0), c.m.get("damage", 0.0))
    return c._worst_damage >= HIT or getattr(c, "founded", 0) > 0


def _changed(world, mask):
    """Terrain changed on `mask` (land to land only): refresh what's worked out from it."""
    S = world.statics
    from terrain import MOVE
    S.urban = world.T == URBAN
    S.move = MOVE[np.clip(world.T, 0, len(MOVE) - 1)].ravel()
    world._horde_statics = None
    world._line_terrain = None


def _count(mask, wrap):
    """How many of each tile's 8 neighbours are in `mask`."""
    return box_sum(mask, 1) - mask.astype(np.int32)


def _site_value(world, cand, built, hm):
    """How good a place each candidate is for a town: coast, ruins of an old city, hills nearby, good land, room."""
    S = world.statics
    from terrain import PROTECTION
    from civilization import fine_jag
    coast = box_sum(~S.land, 1) > 0
    h0 = getattr(world, "H0", None)
    ruin = (h0 >= 150) if h0 is not None else np.zeros(cand.shape, dtype=bool)
    hills = box_sum(PROTECTION[world.T] >= 3, 2) > 0
    v = (1.0 + TOWN_COAST * coast + TOWN_RUIN * ruin + TOWN_HILLS * hills + 0.5 * fine_jag(world)
         + np.minimum(hm, 110) / 110.0)
    crowd = box_sum(built, TOWN_FAR).astype(np.float64)
    return np.where(cand & (box_sum(built, TOWN_APART) == 0), v / (1.0 + 0.5 * crowd), 0.0)


def _footprint(world, r, c):
    """A new town's first tiles: a short random walk from (r, c) over farmland - ragged, not a cross."""
    lo, hi = TOWN_TILES
    n = world.pyrng.randint(lo, hi) if world.stochastic else lo
    tiles = [(r, c)]
    for _ in range(n - 1):
        y, x = world.pyrng.choice(tiles) if world.stochastic else tiles[-1]
        dy, dx = world.pyrng.choice(((-1, 0), (1, 0), (0, -1), (0, 1), (-1, 1), (1, -1), (1, 1), (-1, -1)))
        y, x = y + dy, (x + dx) % world.cols if world.wrap else x + dx
        if 0 <= y < world.rows and 0 <= x < world.cols and world.T[y, x] == GRASS and (y, x) not in tiles:
            tiles.append((y, x))
    return tiles


def _new_towns(world, cand, built, builders, hm):
    """At most TOWN_MAX new towns per building country this check, each on the best site going (some luck)."""
    out = np.zeros(cand.shape, dtype=bool)
    if not cand.any():
        return out
    O = world.O
    value = _site_value(world, cand, built, hm)
    idx = np.flatnonzero(value.ravel() > 0)
    if idx.size == 0:
        return out
    owner = O.ravel()[idx]
    score = value.ravel()[idx] * (world.rng.random(idx.size) + 0.3 if world.stochastic else 1.0)
    for cid in np.unique(owner):
        if not builders[cid]:
            continue
        sel = idx[owner == cid]
        sc = score[owner == cid]
        k = 0
        for j in np.argsort(-sc):
            if k >= TOWN_MAX or (world.stochastic and world.pyrng.random() >= TOWN_CHANCE * min(len(sel), 400) / 20):
                break
            r, c = divmod(int(sel[j]), world.cols)
            if out[max(r - TOWN_FAR, 0):r + TOWN_FAR + 1, max(c - TOWN_FAR, 0):c + TOWN_FAR + 1].any():
                continue
            for y, x in _footprint(world, r, c):
                out[y, x] = True
            k += 1
    return out


def _village_towns(world, hm, rnd):
    """Villages nobody governs that have grown full become towns (VILLAGE_TOWN)."""
    H, T, O = world.H, world.T, world.O
    full = (O == 0) & (T == GRASS) & (H >= FULL * np.maximum(hm, 1)) & (H > 30)
    if not full.any():
        return np.zeros(H.shape, dtype=bool)
    town = (full & (box_sum(np.where(O == 0, np.maximum(H, 0), 0), 2) >= VILLAGE_TOWN_POP)
            & (world.zombie_near(6) == 0) & (box_sum((T == URBAN) | (T == SUBURBAN), TOWN_APART) == 0)
            & (rnd < VILLAGE_TOWN))
    T[town] = SUBURBAN
    hm[town] = np.maximum(hm[town], SUBURB_HOME)
    if town.any() and world.pyrng.random() < 0.2:
        from fracture import _place
        r, c = np.argwhere(town)[0]
        world.note(f"the village near {_place(world, (int(r), int(c)))} has grown into a town")
    return town


def step(world):
    if world.ticks % EVERY or getattr(world, "H0", None) is None or not world.ai:
        return
    H, T, O = world.H, world.T, world.O
    hm = home(world)
    n = len(world.civs)
    age = getattr(world, "_empty_age", None)
    if age is None or age.shape != H.shape:
        age = world._empty_age = np.zeros(H.shape, dtype=np.int32)
    empty = (H <= 10) & world.land
    age[:] = np.where(empty, np.minimum(age + EVERY, 30000), 0)
    rnd = world.rng.random(H.shape) if world.stochastic else np.full(H.shape, 0.5)
    changed = np.zeros(H.shape, dtype=bool)

    # ---- the empty land goes back
    ruin = (T == URBAN) & (age >= RUIN_DAYS)
    fade = (T == SUBURBAN) & (age >= FADE_DAYS)
    woods = (T == FOREST) | (T == RAINFOREST)
    wild = ((T == GRASS) & (age >= WILD_DAYS) & (_count(woods, world.wrap) >= 3) & (rnd < WILD_CHANCE)
            & (hm <= FARM_HOME))
    T[ruin] = SUBURBAN
    hm[ruin] = np.minimum(hm[ruin], SUBURB_HOME)
    T[fade] = GRASS
    hm[fade] = np.minimum(hm[fade], FARM_HOME)
    T[wild] = FOREST
    hm[wild] = np.minimum(hm[wild], WOOD_HOME)
    changed |= ruin | fade | wild
    if ruin.sum() >= 3 and world.pyrng.random() < 0.3:
        from fracture import _place
        r, c = np.argwhere(ruin)[0]
        world.note(f"the empty city of {_place(world, (int(r), int(c)))} is falling into ruin")

    # ---- countries at peace build
    builders = np.zeros(n, dtype=bool)
    built = (T == URBAN) | (T == SUBURBAN)
    tiles = np.bincount(O.ravel(), weights=(world.land & (O > 0)).ravel(), minlength=n)
    bshare = np.bincount(O.ravel(), weights=(built & (O > 0)).ravel(), minlength=n) / np.maximum(tiles, 1)
    pop = np.bincount(O.ravel(), weights=np.maximum(H, 0).ravel(), minlength=n)
    room = np.bincount(O.ravel(), weights=(hm * (O > 0)).ravel(), minlength=n)
    first = getattr(world, "_built0", None)            # (what each country had built up when we first saw it)
    if first is None:
        first = bshare.copy()
    elif first.size < n:
        first = np.concatenate([first, bshare[first.size:]])
    world._built0 = first
    for c in world.civs:
        if (recovering(c) and not c.famine and c.threat(c.m) < SAFE_THREAT
                and pop[c.id] >= COUNTRY_FULL * room[c.id]):
            builders[c.id] = True
    changed |= _village_towns(world, hm, rnd)
    if not builders.any():
        if changed.any():
            _changed(world, changed)
        return
    cap = np.maximum(URBAN_MAX, first)
    can = builders[O] & (bshare[O] < cap[O]) & (world.zombie_near(3) == 0)
    full = (H >= FULL * np.maximum(hm, 1)) & (H > 10)
    farms = (T == GRASS) & full
    nb_built = _count(built, world.wrap)
    nb_city = _count(T == URBAN, world.wrap)
    nb_farm = _count(farms, world.wrap)
    from civilization import fine_jag
    rag = np.clip(1.0 + SUBURB_RAGGED * fine_jag(world), 0.1, 2.0)
    clear = can & woods & (nb_farm >= 3) & (rnd < np.where(T == RAINFOREST, CLEAR_CHANCE / 2, CLEAR_CHANCE))
    # (suburbs: more likely the more built-up neighbours, and more here than there)
    suburb = can & farms & (nb_built >= 1) & (rnd < SUBURB_CHANCE * rag * np.minimum(nb_built, 4) / 2.5)
    city = can & (T == SUBURBAN) & full & (nb_built >= 4) & (nb_city >= 1) & (rnd < CITY_CHANCE * rag)
    town = _new_towns(world, can & farms & (hm >= 40), built, builders, hm)
    T[clear] = GRASS
    hm[clear] = np.maximum(hm[clear], FARM_HOME)
    T[suburb | town] = SUBURBAN
    hm[suburb | town] = np.maximum(hm[suburb | town], SUBURB_HOME)
    T[city] = URBAN
    hm[city] = np.maximum(hm[city], CITY_HOME)
    changed |= clear | suburb | city | town
    if town.any():
        from fracture import _place
        for r, c in np.argwhere(town)[:2]:
            world.note(f"{world.civs[int(O[r, c])].name} builds a new town near {_place(world, (int(r), int(c)))}")
    if changed.any():
        _changed(world, changed)
