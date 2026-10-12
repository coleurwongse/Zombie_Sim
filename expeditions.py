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
"""
import numpy as np

import boats
from civilization import box_sum

CHECK_EVERY = 30
EXP_CHANCE = 0.35            # per check, an able country mounts an expedition (x its aggression)
EXP_ARMY = 0.6
EXP_STRENGTH = 0.5
EXP_SIZE = 1.5
EXP_DANGER = 0.15
EXP_MATERIALS = 150.0
EXP_COST = 60.0
EXP_REACH = 20.0             # degrees from the capital (+ up to EXP_REACH_BIG for the biggest, strongest countries)
EXP_REACH_BIG = 25.0
LOST_RADIUS = 12             # no governed, populated land this close: the coast is lost
MAX_HORDE = 2000             # zombies within 4 tiles of the landing site at most
AWAY = 3.0                   # degrees from any land it held at the start, at least (lakes and rivers split a continent
                             # into several landmasses; across the Great Lakes is not overseas)
BEACH_REACH = 15.0           # degrees around the landing within which it may take land on that landmass


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
    return (c.military >= EXP_ARMY and c.strength >= EXP_STRENGTH and c.size(world) >= EXP_SIZE
            and c.materials >= EXP_MATERIALS and c.ports > 0 and c.danger(c.m)[0] < EXP_DANGER
            and not war.at_war(world, c.id) and not any(b.get("overseas") for b in c.bases))


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
    homes = np.unique(S.landmass[world.O0 == c.id])           # (never a landmass it held land on at the start:
    homes = np.union1d(homes, [home])                         #  that's not overseas - e.g. across the Great Lakes)
    ok = (np.isin(C.coast_body, list(seas)) & (O[cr, cc] == 0) & ~np.isin(S.landmass[cr, cc], homes)
          & (world.zombie_near(4)[cr, cc] <= MAX_HORDE) & (world.T[cr, cc] != 5))
    if not ok.any():
        return None
    d = _deg(world, c.capital[0], c.capital[1], cr, cc)
    ok &= d <= reach
    if not ok.any():
        return None
    lost = box_sum(governed, LOST_RADIUS) == 0
    ok &= lost[cr, cc]
    if not ok.any():
        return None
    near_home = box_sum(world.O0 == c.id, max(1, int(AWAY / float(world.meta.get("res", 0.5))))) > 0
    ok &= ~near_home[cr, cc]
    # only land whose own government has fallen: nobody "reclaims" a living country's land
    fallen = np.array([o.id == 0 or o.collapsed for o in world.civs])
    ok &= fallen[world.O0[cr, cc]]
    if not ok.any():
        return None
    j = int(np.argmin(np.where(ok, d, np.inf)))
    return int(cr[j]), int(cc[j])


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
    H, Z, D, O = world.H, world.Z, world.D, world.O
    Z[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2] = 0
    O[r, c] = civ.id
    H[r, c] = off.BASE_GARRISON
    D[r, c] = off.BASE_LEVEL
    site = dict(center=(r, c), tiles=[(r, c)], level=off.BASE_LEVEL, target=off.BASE_LEVEL, base=True)
    civ.sites.append(site)
    civ.bases.append(dict(center=(r, c), born=world.ticks, site=site, cleared=False, overseas=True,
                          zone=off._zone_mask(world, r, c), order=off._settle_noise(world, r, c)))
    beachhead(world, civ, r, c)
    if getattr(civ, "home_masses", None) is None:            # (its morale is judged on the fighting at home)
        S = world.statics
        civ.home_masses = np.union1d(np.unique(S.landmass[world.O0 == civ.id]), [S.landmass[civ.capital]])
    from fracture import _place
    world.note(f"EXPEDITION: {civ.name} lands an army at {_place(world, (r, c))} to take the coast back")
    return True


def beachhead(world, civ, r, c):
    """Let `civ` take land on that landmass around the landing (world.beach_map, see World.may_claim)."""
    bm = getattr(world, "beach_map", None)
    if bm is None:
        bm = world.beach_map = np.zeros(world.H.shape, dtype=np.int32)
    rr, cc = np.indices(world.H.shape)
    near = (_deg(world, r, c, rr, cc) <= BEACH_REACH) & (world.statics.landmass == world.statics.landmass[r, c])
    bm[near & (bm == 0)] = civ.id
