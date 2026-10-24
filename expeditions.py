"""Overseas expeditions: a strong country takes back a lost coast across the sea.

Only a country that can afford it and has a reason to be there: a strong, well-supplied army (EXP_ARMY, EXP_STRENGTH),
a big population (EXP_SIZE x an average government's), no zombie threat at home (danger below EXP_DANGER), not at
war, with working ports on the same sea as the target - and the target not too far from its capital (EXP_REACH
degrees, longer for bigger, stronger countries: China to Indonesia yes, the Dominican Republic to New York no).

The target is a stretch of coast on another landmass, well away from anything the country held at the start (AWAY),
in a country whose government has fallen, that no government holds any more (no governed, populated land within
LOST_RADIUS tiles), and where the horde isn't overwhelming.  The expedition lands there as an offensive base
(offensive.py): the garrison and the settlers come by ship from home, the base sorties against the zombies around it
and settles the ground it clears, and from there the country can keep advancing - but only on that landmass and within
BEACH_REACH degrees of where it landed (world.beach_map, used by World.may_claim).  Such land was never the country's
own, so it may well declare independence later (fracture.independence).

Open land (open_land): where most of a region's once-settled land is empty and nobody's - a continent the zombies
emptied - countries that are doing fine elsewhere come for it: from as far as OPEN_REACH degrees by sea, even a living
country's empty land, even on their own landmass if it is far from home (OPEN_AWAY), more landings at once (OPEN_MAX)
and a wider beachhead (OPEN_BEACH).
"""
import numpy as np

import boats
from civilization import box_sum

CHECK_EVERY = 20
EXP_CHANCE = 0.7             # per check, an able country mounts an expedition (x its aggression)
EXP_ARMY = 0.5
EXP_STRENGTH = 0.4
EXP_SIZE = 1.0
EXP_DANGER = 0.2             # (+ EXP_DANGER_TURNED for a country past its turning point: resolve.py)
EXP_DANGER_TURNED = 0.15
EXP_MATERIALS = 100.0
EXP_MAX = 2                  # overseas landings a country runs at once
EXP_COST = 60.0
EXP_REACH = 25.0             # degrees from the capital (+ up to EXP_REACH_BIG for the biggest, strongest countries)
EXP_REACH_BIG = 30.0
LOST_RADIUS = 8              # no governed, populated land this close: the coast is lost
MAX_HORDE = 2000             # zombies within 4 tiles of the landing site at most
AWAY = 3.0                   # degrees from any land it held at the start, at least (lakes and rivers split a continent
                             # into several landmasses; across the Great Lakes is not overseas)
BEACH_REACH = 15.0           # degrees around the landing within which it may take land on that landmass
SEA_DETOUR = 1.4             # a voyage may be this much longer than the reach (sea lanes aren't straight)
RETRY_TICKS = 150            # a landing that failed isn't tried again within RETRY_DEG for this long
RETRY_DEG = 6.0
EXP_GAP = 60                 # days between one country's landings
# Open land: where most of a region's once-settled land is empty and nobody's (a continent the zombies emptied), the
# rest of the world comes for it - farther, more often and across what would otherwise be its own landmass.
OPEN_RADIUS = 15.0           # degrees: a region is "open" when ...
OPEN_SHARE = 0.55            # ... at least this share of the once-settled land within OPEN_RADIUS is empty and nobody's
OPEN_REACH = 110.0           # degrees of voyage an able country will sail for open land (another continent)
OPEN_AWAY = 20.0             # open land on its own landmass counts as overseas this far from its capital
OPEN_MAX = 2                 # landings at once while there is open land somewhere
OPEN_GAP = 30
OPEN_BEACH = 30.0            # degrees around such a landing it may take


def _deg(world, r0, c0, r1, c1):
    res = float(world.meta.get("res", 0.5))
    dc = np.abs(c1 - c0)
    if world.wrap:
        dc = np.minimum(dc, world.cols - dc)
    b = world.meta.get("bounds")
    lat = (b[3] - (r1 + 0.5) * res) if b else 0.0
    return np.hypot((r1 - r0) * res, dc * res * np.cos(np.radians(lat)))


def able(world, c):
    import war
    if not c.ai or c.collapsed or c.is_anarchy or not c.m or c.famine or c.capital is None:
        return False
    danger = EXP_DANGER + (EXP_DANGER_TURNED if getattr(c, "turned", False) else 0.0)
    return (c.military >= EXP_ARMY and c.strength >= EXP_STRENGTH and c.size(world) >= EXP_SIZE
            and c.materials >= EXP_MATERIALS and c.ports > 0 and c.threat(c.m) < danger
            and c.m.get("damage", 0.0) < 0.5 and getattr(c, "_abroad_ok", True)
            and not war.at_war(world, c.id)
            and sum(1 for b in c.bases if b.get("overseas")) < (OPEN_MAX if any_open(world) else EXP_MAX)
            and world.ticks >= getattr(c, "_exp_next", 0))


def open_land(world):
    """Tiles in an 'open' region: most of the once-settled land around them is empty and nobody's (cached a while)."""
    memo = getattr(world, "_open_land", None)
    if memo is not None and world.ticks - memo[0] < CHECK_EVERY and memo[1].shape == world.H.shape:
        return memo[1]
    gov = np.zeros(len(world.civs), dtype=bool)
    for o in world.civs:
        gov[o.id] = bool(o.id and o.ai and not o.collapsed)
    settled = (world.H0 >= 20) & world.land
    empty = settled & (world.H <= 10) & ~gov[world.O]
    rad = max(2, int(OPEN_RADIUS / float(world.meta.get("res", 0.5))))
    tot = box_sum(settled, rad)
    out = (tot >= 30) & (box_sum(empty, rad) >= OPEN_SHARE * tot)
    world._open_land = (world.ticks, out)
    return out


def any_open(world):
    return bool(open_land(world).any())


def sea_steps_cached(world, c, n):
    """_sea_steps for country c out to at least n steps, kept for 100 days."""
    cache = getattr(c, "_sea_cache", None)
    if cache is None or len(cache) < 3 or world.ticks - cache[0] > 100 or cache[2] < n:
        cache = c._sea_cache = (world.ticks, _sea_steps(world, c, n), n)
    return cache[1]


def step(world):
    if world.ticks % CHECK_EVERY or not world.ports:
        return
    for c in world.civs:
        if able(world, c) and world.pyrng.random() < EXP_CHANCE * c.traits.get("aggression", 1.0):
            target = _target(world, c)
            if target is not None:
                launch(world, c, *target)


def _target(world, c):
    S, C = world.statics, boats.coasts(world)
    H, O = world.H, world.O
    res = float(world.meta.get("res", 0.5))
    home = S.landmass[c.capital]
    # the seas its working ports are on
    seas = {int(C.body[r, k]) for r, k, s in world.ports if O[r, k] == c.id and H[r, k] > 10 and C.body[r, k] > 0}
    if not seas:
        return None
    reach = EXP_REACH + EXP_REACH_BIG * min(1.0, c.strength * c.size(world) / 3.0)
    gov = np.zeros(len(world.civs), dtype=bool)
    for o in world.civs:
        gov[o.id] = bool(o.id and o.ai and not o.collapsed)
    governed = gov[O] & (H > 10)
    cr, cc = C.coast_r, C.coast_c
    opened = open_land(world)[cr, cc]                         # (an emptied continent: the world comes for it)
    far = np.where(opened, max(reach, OPEN_REACH), reach)
    homes = np.unique(S.landmass[world.O0 == c.id])           # (never a landmass it held land on at the start:
    homes = np.union1d(homes, [home])                         #  that's not overseas - e.g. across the Great Lakes)
    d = _deg(world, c.capital[0], c.capital[1], cr, cc)
    abroad = ~np.isin(S.landmass[cr, cc], homes) | (opened & (d >= OPEN_AWAY))
    ok = (np.isin(C.coast_body, list(seas)) & (O[cr, cc] == 0) & abroad
          & (world.zombie_near(4)[cr, cc] <= MAX_HORDE) & (world.T[cr, cc] != 5))
    if not ok.any():
        return None
    ok &= d <= far
    if not ok.any():
        return None
    lost = box_sum(governed, LOST_RADIUS) == 0
    ok &= lost[cr, cc]
    if not ok.any():
        return None
    near_home = box_sum(world.O0 == c.id, max(1, int(AWAY / res))) > 0
    ok &= ~near_home[cr, cc]
    # only land whose own government has fallen (nobody "reclaims" a living country's land) - or open land
    fallen = np.array([o.id == 0 or o.collapsed for o in world.civs])
    ok &= fallen[world.O0[cr, cc]] | opened
    if getattr(world, "_settled_coast", None) is None:   # (only coasts people lived on are worth an expedition)
        world._settled_coast = box_sum(world.H0 >= 20, 3) >= 4
    ok &= world._settled_coast[cr, cc]
    for t, r0, c0 in getattr(c, "_exp_tried", []):        # (not straight back to where a landing just failed)
        if world.ticks - t < RETRY_TICKS:
            ok &= _deg(world, r0, c0, cr, cc) > RETRY_DEG
    if not ok.any():
        return None
    # by sea: the voyage from its ports, not the distance as the crow flies (no sailing round Africa to the Arctic)
    n = int(float(far[ok].max()) * SEA_DETOUR / res)
    sea = sea_steps_cached(world, c, n)
    ok &= sea[cr, cc] <= far * SEA_DETOUR / res
    if not ok.any():
        return None
    # the nearest - but open land is worth a longer voyage than a lone lost coast
    cost = np.where(ok, sea[cr, cc] * np.where(opened, 0.5, 1.0), np.inf)
    j = int(np.argmin(cost))
    return int(cr[j]), int(cc[j])


def _sea_steps(world, c, n):
    """Steps over water from its working ports to every tile (the coast next to the water counts), up to n."""
    from civilization import steps
    water = ~world.statics.land
    start = np.zeros(world.H.shape, dtype=bool)
    for r, k, s in world.ports:
        if world.O[r, k] == c.id and world.H[r, k] > 10:
            start[max(r - 2, 0):r + 3, max(k - 2, 0):k + 3] |= water[max(r - 2, 0):r + 3, max(k - 2, 0):k + 3]
    d = steps(start, n, through=water).astype(np.int32)
    out = d.copy()                                        # a coast tile: one step on from the water beside it
    out[1:] = np.minimum(out[1:], d[:-1] + 1)
    out[:-1] = np.minimum(out[:-1], d[1:] + 1)
    out[:, 1:] = np.minimum(out[:, 1:], d[:, :-1] + 1)
    out[:, :-1] = np.minimum(out[:, :-1], d[:, 1:] + 1)
    return out


def draw_from_home(world, civ, n, keep=30):
    """Take n people from wherever the nation has most to spare (they sail out).  False if it can't."""
    win = world.bbox(civ.id)
    H = world.H[win]
    spare = np.where(world.O[win] == civ.id, np.maximum(H - keep, 0), 0)
    if spare.sum() < n:
        return False
    flat = spare.ravel()
    order = np.argsort(-flat)
    need = n
    for k in order:
        if need <= 0:
            break
        take = int(min(flat[k], need))
        r, c = divmod(int(k), spare.shape[1])
        H[r, c] -= take
        need -= take
    return True


def launch(world, civ, r, c):
    import offensive as off
    if not draw_from_home(world, civ, off.BASE_GARRISON):
        return False
    civ.materials -= EXP_COST
    opened = bool(open_land(world)[r, c])
    civ._exp_next = world.ticks + (OPEN_GAP if opened else EXP_GAP)
    civ._exp_tried = [x for x in getattr(civ, "_exp_tried", []) if world.ticks - x[0] < RETRY_TICKS] + [
        (world.ticks, r, c)]
    H, Z, D, O = world.H, world.Z, world.D, world.O
    Z[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2] = 0
    O[r, c] = civ.id
    H[r, c] = off.BASE_GARRISON
    D[r, c] = off.BASE_LEVEL
    site = dict(center=(r, c), tiles=[(r, c)], level=off.BASE_LEVEL, target=off.BASE_LEVEL, base=True)
    civ.sites.append(site)
    civ.bases.append(dict(center=(r, c), born=world.ticks, site=site, cleared=False, overseas=True,
                          zone=off._zone_mask(world, r, c), order=off._settle_noise(world, r, c)))
    beachhead(world, civ, r, c, OPEN_BEACH if opened else BEACH_REACH)
    import trade                                            # (supply ships from home now and then: trade.py)
    trade.register(world, civ, r, c)
    if getattr(civ, "home_masses", None) is None:            # (its morale is judged on the fighting at home)
        S = world.statics
        civ.home_masses = np.union1d(np.unique(S.landmass[world.O0 == civ.id]), [S.landmass[civ.capital]])
    from fracture import _place
    world.note(f"EXPEDITION: {civ.name} lands an army at {_place(world, (r, c))} "
               + ("to claim the emptied land" if opened else "to take the coast back"))
    return True


def beachhead(world, civ, r, c, reach=BEACH_REACH):
    """Let `civ` take land on that landmass around the landing (world.beach_map, see World.may_claim)."""
    bm = getattr(world, "beach_map", None)
    if bm is None:
        bm = world.beach_map = np.zeros(world.H.shape, dtype=np.int32)
    rr, cc = np.indices(world.H.shape)
    from civilization import jag
    ragged = reach * (1.0 + 0.35 * jag(world) / 1.5)                  # (a ragged edge, not a circle)
    near = (_deg(world, r, c, rr, cc) <= ragged) & (world.statics.landmass == world.statics.landmass[r, c])
    bm[near & (bm == 0)] = civ.id
