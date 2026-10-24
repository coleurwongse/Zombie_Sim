"""A small economy: food and materials.

Each civilization has two stockpiles.

  Food       grown on land (mostly grass; also forest, desert, suburbs...) wherever people live and
             zombies aren't taking over; eaten by everyone on its land.  When the stock runs out the
             civilization is in FAMINE: morale keeps sliding and unrest builds in every tile.
  Materials  produced by industry (cities, suburbs, mines in mountains, a little everywhere else)
             wherever the tile isn't being overrun.  Spent on fortifying (building sites), on purges
             (ammunition) and on evacuations (transport).

Imports    a country that couldn't feed itself before the outbreak (mountains, desert, big cities) imported the rest:
           it keeps importing that share of what it eats while world shipping runs (world.trade_index, boats.py),
           less with its borders shut - as the world's trade collapses, import-dependent countries go hungry.

Seasons    (seasons.py) food grows with the season - nothing under the snow - and people under snow eat more and
           need fuel (seasons.FUEL_SHARE of the materials income); a country stores more food the colder its people
           live (seasons.store_days); one out of materials in the snow loses people to the cold (seasons.EXPOSURE).
Technology (tech.py) a district that has lost its machines makes less (tech.TECH_MAT, TECH_FOOD); its far provinces'
           materials reach the treasury only in part (trade.supply); trade routes add to both (trade.TRADE_BONUS).

Overrun or infested tiles produce nothing, so a spreading outbreak starves the very civilization that
needs the most food and materials.  Runs once per tick before people and morale (only when ai=True).
"""
import numpy as np

from terrain import is_land, is_water

import govern

# terrain ids:            ocean grass forest mountain desert ice  urban suburban
from terrain import FOOD_YIELD, MATERIAL_YIELD   # per productive tile per tick, by terrain id (terrain.py)
FOOD_PER_PERSON = 0.0008        # per person per tick
FOOD_START_TICKS = 40           # starting stock = this many ticks of consumption
START_STORE = 0.8               # ... or this share of what a cold country stores for the winter, if more
FOOD_CAP_TICKS = 120            # storage limit
MATERIALS_START = 60.0
MATERIALS_CAP = 400.0           # (for an average-sized government: x its size, see Civilization.size)
MIN_POP = 10                    # a tile needs more than this many people to produce
FOOD_WORKERS = 40               # people needed for a tile's full food output (fewer people, proportionally less)
MATERIAL_WORKERS = 100          # ... and for its full materials output
BLIGHT_CHANCE = 0.004           # per tick, some nation's harvests fail ...
BLIGHT_TICKS = 20               # ... for this long ...
BLIGHT_YIELD = 0.55             # ... producing this share
QUARANTINE_TRADE = (0.95, 0.85) # food / materials kept while the borders are shut
SCAVENGE = 0.002                # materials per person per tick that fresh survivor colonies salvage ...
SCAVENGE_TICKS = 400            # ... tapering off over this long
INFESTED = 3                    # a tile with zombies*INFESTED >= humans produces nothing
STARVE_RATE = 0.04              # share of the people above what the land can feed that die each tick (unowned land)
FAMINE_DEATHS = 0.01            # share of a civilization's people that die each tick while it is in famine
RATION_TICKS = 15               # with less food in store than this many ticks' worth, the government rations ...
RATION = 0.8                    # ... and people eat this share of a normal ration
STANDING_UPKEEP = 0.25          # a realm's standing fortresses (Minas Tirith, Erebor ...) cost this share of a new fort
IMPORT_MAX = 1.0                # a country imports at most this share of its food
IMPORT_CLOSED = 0.6             # ... and with its borders shut only this much of its usual imports arrive


def local_capacity(world):
    """How many people each tile can feed from its own land (0 where there is no farmland)."""
    return FOOD_YIELD[world.T] / FOOD_PER_PERSON


def step(world):
    H, Z, T, O = world.H, world.Z, world.T, world.O
    n = len(world.civs)
    li = world.statics.land_idx if hasattr(world, "statics") else np.arange(H.size)      # (only land produces)
    h, z, t, o = H.ravel()[li], Z.ravel()[li], T.ravel()[li], O.ravel()[li]
    productive = (h > MIN_POP) & (z * INFESTED < h) & (o > 0)
    import nukes
    poisoned = nukes.poisoned(world)
    if poisoned is not None:
        productive &= ~poisoned.ravel()[li]                          # fallout: nothing grows, nothing is made
    o_p, h_p, t_p = o[productive], h[productive], t[productive]
    food_w = np.minimum(h_p, FOOD_WORKERS) / FOOD_WORKERS              # empty farms grow nothing
    mat_w = np.minimum(h_p, MATERIAL_WORKERS) / MATERIAL_WORKERS
    import seasons
    import tech
    import trade
    lp = li[productive]
    fy = FOOD_YIELD[t_p] * food_w
    my = MATERIAL_YIELD[t_p] * mat_w
    year_food = np.bincount(o_p, weights=fy, minlength=n)            # (over the year, before the season)
    fy = fy * seasons.harvest(world).ravel()[lp]
    tf, tm = tech.mult(world, tech.TECH_FOOD), tech.mult(world, tech.TECH_MAT)
    if tf is not None:
        fy = fy * tf.ravel()[lp]
        my = my * tm.ravel()[lp]
    sup = trade.supply(world)
    if sup is not None:
        my = my * (1.0 - trade.SUPPLY_MATERIALS * (1.0 - sup.ravel()[lp]))
    food_prod = np.bincount(o_p, weights=fy, minlength=n)
    mat_prod = np.bincount(o_p, weights=my, minlength=n)
    wload = seasons.winter_load(world)
    cold_share = _cold_share(world)
    people = np.bincount(o, weights=np.maximum(h, 0), minlength=n)
    people[0] = 0
    if world.stochastic and world.rng.random() < BLIGHT_CHANCE:
        live = [c for c in world.civs if c.id and c.ai and not c.collapsed and c.food is not None]
        if live:
            victim = live[int(world.rng.integers(len(live)))]
            victim.blight_until = world.ticks + BLIGHT_TICKS
            world.note(f"blight hits {victim.name}'s harvests")
    for civ in world.civs:
        if civ.is_anarchy or not civ.ai or civ.collapsed:
            continue
        use = float(people[civ.id]) * FOOD_PER_PERSON
        fprod = float(food_prod[civ.id]) * govern.mod(civ, "food")
        if civ.food is None:                      # first tick: stock up (the granaries of a cold country are filled
            # for the winter: seasons.store_days), and work out what it imports
            civ.food = use * max(FOOD_START_TICKS, START_STORE * seasons.store_days(float(cold_share[civ.id])))
            civ.materials = MATERIALS_START
            yp = float(year_food[civ.id]) * govern.mod(civ, "food")
            civ.import_share = min(IMPORT_MAX, max(0.0, 1.03 - yp / use)) if use > 0 else 0.0
        use *= 1.0 + seasons.WINTER_EAT * float(wload[civ.id])          # (the cold: people eat more)
        bonus = getattr(civ, "trade_bonus", 0.0)
        fprod *= 1.0 + 0.5 * bonus
        if getattr(civ, "import_share", 0.0) > 0:
            fprod += civ.import_share * use * world.trade_index * (IMPORT_CLOSED if civ.closed else 1.0)
        mprod = float(mat_prod[civ.id]) * govern.mod(civ, "materials") * (1.0 + bonus)
        civ.rationing = civ.food < RATION_TICKS * use
        if civ.rationing:
            use *= RATION
        fprod *= world.jitter(0.12)                                  # weather
        if world.ticks < civ.blight_until:
            fprod *= BLIGHT_YIELD
        if civ.closed:
            fprod *= QUARANTINE_TRADE[0]
            mprod *= QUARANTINE_TRADE[1]
        if civ.successor and civ.split_from is None:              # survivor colonies live off salvage at first
            age = world.ticks - civ.founded
            mprod += float(people[civ.id]) * SCAVENGE * max(0.0, 1.0 - age / SCAVENGE_TICKS)
        civ.food_use, civ.food_prod = use, fprod
        civ.food_prod_avg = fprod if civ.food_prod_avg is None else 0.95 * civ.food_prod_avg + 0.05 * fprod
        fuel = seasons.FUEL_SHARE * float(wload[civ.id]) * max(mprod, 0.0)     # (heating)
        mprod -= fuel
        civ.fuel = fuel
        civ.mat_income = mprod
        # Storage is in the cities and granaries: it shrinks with the people who live there (and is bigger where the
        # winters are long).
        cap_days = max(FOOD_CAP_TICKS, seasons.store_days(float(cold_share[civ.id])))
        civ.food = min(civ.food + civ.food_prod - use, cap_days * use)
        civ.materials = min(civ.materials + civ.mat_income, max(MATERIALS_CAP * civ.size(world), 60.0))
        civ.famine = civ.food <= 0
        if civ.famine:
            civ.food = 0.0
            mine = (O == civ.id) & (H > 0)
            H[mine] -= np.maximum(1, np.ceil(H[mine] * FAMINE_DEATHS)).astype(np.int32)
        upkeep(world, civ)
        if wload[civ.id] > 0.05 and civ.materials < 1.0:
            exposure(world, civ)
    starve_unowned(world)


def _cold_share(world):
    """Per government id: how cold the places its people live are (seasons.cold, by people; every 30 days)."""
    memo = getattr(world, "_cold_share", None)
    n = len(world.civs)
    if memo is not None and memo[1].size == n and world.ticks - memo[0] < 30:
        return memo[1]
    import seasons
    o = world.O.ravel()
    hp = np.maximum(world.H, 0).ravel().astype(np.float64)
    out = (np.bincount(o, weights=hp * seasons.cold(world).ravel(), minlength=n)
           / np.maximum(np.bincount(o, weights=hp, minlength=n), 1))
    world._cold_share = (world.ticks, out)
    return out


def exposure(world, civ):
    """No fuel in the snow: some of the people under it die of the cold (less where there's still power)."""
    import seasons
    import tech
    win = world.bbox(civ.id)
    sn = seasons.snow(world)[win]
    H = world.H[win]
    mine = (world.O[win] == civ.id) & (H > 0) & (sn > 0)
    if not mine.any():
        return
    t = tech.level(world)[win]
    rate = seasons.EXPOSURE * sn * (1.0 - 0.5 * t)
    dead = np.floor(H * rate + (world.rng.random(H.shape) if world.stochastic else 0.5))
    H -= np.where(mine, np.minimum(dead, H), 0).astype(H.dtype)


def upkeep(world, civ):
    """Fortified sites and bases have to be manned and supplied.  A government that can't pay for them all, or has
    more than its people can man (Civilization.max_sites), gives up the ones it needs least (farthest from any
    zombies; offensive bases last)."""
    import civilization as C
    if not civ.sites:
        civ.upkeep = 0.0
        return
    cost = sum((C.SITE_UPKEEP + C.SITE_UPKEEP_LEVEL * len(s["tiles"]) * s["level"])
               * (STANDING_UPKEEP if s.get("standing") else 1.0) for s in civ.sites)
    civ.upkeep = cost
    civ.materials -= cost
    cap = civ.max_sites()
    extra = [s for s in civ.sites if not s.get("standing")]   # (standing garrisons don't count against the cap)
    if civ.materials >= 0 and len(extra) <= cap:
        return
    near = world.zombie_near(C.FORT_REGION)
    dropped = 0
    while civ.sites and (civ.materials < 0 or len([s for s in civ.sites if not s.get("standing")]) > cap):
        pool = [s for s in civ.sites if not s.get("standing")] or civ.sites
        s = min(pool, key=lambda s: near[s["center"]] + (10 ** 7 if s.get("base") else 0))
        civ.sites.remove(s)
        civ.materials += C.SITE_UPKEEP + C.SITE_UPKEEP_LEVEL * len(s["tiles"]) * s["level"]
        for rc in s["tiles"]:
            world.D[rc] = min(world.D[rc], 3)
        dropped += 1
    civ.materials = max(0.0, civ.materials)
    if dropped and world.ticks - getattr(civ, "_noted_upkeep", -10 ** 6) >= 40:
        civ._noted_upkeep = world.ticks
        world.note(f"{civ.name} can't keep up its forts and abandons {dropped}")


def starve_unowned(world):
    """People outside any civilization live off the land they stand on; above what it can feed they starve."""
    H = world.H
    import seasons
    cap = local_capacity(world) * np.maximum(0.5, seasons.harvest(world))      # (villagers keep a little in store)
    excess = np.where((world.O == 0) & (H > 0), H - cap, 0.0)
    sn = seasons.snow(world)
    if sn.any():                                          # (and huddle round wood fires in the snow)
        nobody = (world.O == 0) & (H > 0) & (sn > 0)
        if nobody.any():
            cold = np.floor(H * seasons.EXPOSURE_WILD * sn + (world.rng.random(H.shape) if world.stochastic else 0.5))
            H -= np.where(nobody, np.minimum(cold, np.maximum(H, 0)), 0).astype(H.dtype)
    dying = np.where(excess > 0, np.maximum(1, np.ceil(excess * STARVE_RATE)), 0).astype(np.int32)
    H -= np.minimum(dying, np.maximum(H, 0))
