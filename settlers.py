"""Settlers: small groups from a country that's doing well strike out for empty land and found a country of their own.

Every SETTLE_EVERY days each government that is safe, fed, in good heart and has people to spare may (SETTLE_CHANCE)
send a group of SETTLE_GROUP of its people to a place people used to live (pre-outbreak population at least
SETTLE_HOME_MIN) that is now empty, nobody's, clean (a few stragglers at most near it) and well away from any standing government
(SETTLE_APART - closer than that, ordinary expansion takes care of it) - and from the other settlers' colonies
(none within SETTLE_SPACING tiles, fewer up to SETTLE_SPREAD, none at all that close to one founded in the last
SETTLE_QUIET days: they spread out rather than crowd one spot).  They go over land (same landmass, within
SETTLE_LAND_REACH degrees of its capital) or, from a working port, by sea (within SETTLE_SEA_REACH degrees' voyage) -
so emptied continents get settled again once their zombies are gone.  Old big cities draw them most.

The settlers found a state of their own there (named after the city, its own government - not a province of the old
country), which then grows like any other: births back toward what the land held before, resettling its edges,
annexing the empty land around it, merging with neighbours.  That's how the world fills up again in the endgame.
"""
import numpy as np

import govern
from civilization import box_sum

SETTLE_EVERY = 7
SETTLE_CHANCE = 0.9          # per round, an able government sends a group (x its aggression)
SETTLE_MIN_POP = 1000        # people (map units) it needs at home
SETTLE_GROUP = 250           # people (map units) per group: enough for a town and its fields
SETTLE_HOME_MIN = 20         # the place held at least this many before the outbreak
SETTLE_APART = 7             # tiles from any governed, populated land
SETTLE_SAFE = 8              # at most SETTLE_SAFE_Z zombies (stragglers) within this many tiles
SETTLE_SAFE_Z = 30
SETTLE_CLEAR = 24            # ... and no horde (more than SETTLE_CLEAR_Z zombies) within this many tiles
SETTLE_CLEAR_Z = 400
COLONY_GRACE = 150           # a young colony: its morale doesn't break this long (unless it loses most of its people),
COLONY_FORT = 6              # it has a garrison of this level at its centre, an army of at least COLONY_ARMY,
COLONY_ARMY = 0.4            # food for COLONY_FOOD days - and the old country sends troops to see it through (aid.py)
COLONY_FOOD = 120
COLONY_ROOM = 120            # a colony needs this many free once-settled tiles within ROOM_REACH tiles (room to grow) ...
ROOM_REACH = 12
COLONY_RESERVE = 7           # ... and the land within about this many tiles of it is its to settle (nobody else may
RESERVE_DAYS = 150           #     claim it) for this many days
SETTLE_LAND_REACH = 30.0     # degrees from its capital, over land
SETTLE_SEA_REACH = 35.0      # degrees of voyage from its ports
SETTLE_DANGER = 0.25
SETTLE_MIN_MORALE = 5
SETTLE_COST = 15.0           # materials (ships, tools, food for the road)
SETTLE_MAX_PER_ROUND = 10    # new settlements in the whole world per round
SETTLE_SPACING = 24          # tiles: no new settlement this close to another settlers' colony that still stands ...
SETTLE_SPREAD = 48           # ... and up to this far its pull fades in (colonies spread out instead of clustering);
SETTLE_QUIET = 60            # within this many days of one's founding, nothing at all within SETTLE_SPREAD of it
SETTLE_FAILED = 150          # a colony that fell keeps others away from there (SETTLE_SPREAD) this long after its founding
# (a map's meta "settle_scale" stretches SPACING and SPREAD and divides MAX_PER_ROUND: Middle-earth and Beleriand are
#  small grids of a small world, 2)


def step(world):
    world.last_settlers = 0
    if world.ticks % SETTLE_EVERY or world.ticks < 30:
        return
    able = [c for c in world.civs if _able(world, c)]
    if not able:
        return
    cand = _places(world)
    if not cand.any():
        return
    colonies = []
    for r, k, cid, t in getattr(world, "colonies", []):
        fell = cid >= len(world.civs) or world.civs[cid].collapsed
        if not fell:
            colonies.append((r, k, world.ticks - t < SETTLE_QUIET))
        elif world.ticks - t < SETTLE_FAILED:          # (nobody hurries after a colony that just failed there)
            colonies.append((r, k, True))
    world.pyrng.shuffle(able)
    founded = 0
    most = max(1, int(round(SETTLE_MAX_PER_ROUND / _scale(world))))
    for c in able:
        if founded >= most:
            break
        if world.pyrng.random() >= SETTLE_CHANCE * c.traits.get("aggression", 1.0):
            continue
        target = _target(world, c, cand, colonies)
        if target is None:
            continue
        new = found(world, c, *target)
        if new is not None:
            founded += 1
            colonies.append(target + (True,))
            world.__dict__.setdefault("colonies", []).append(target + (new.id, world.ticks))


def _able(world, c):
    if not c.ai or c.collapsed or c.is_anarchy or not c.m or c.famine or c.capital is None:
        return False
    return (c.m.get("pop", 0) >= SETTLE_MIN_POP and c.morale >= SETTLE_MIN_MORALE and c.materials >= SETTLE_COST
            and c.threat(c.m) < SETTLE_DANGER and c.m.get("damage", 0.0) < 0.5)


def _places(world):
    """Where settlers may go: once-settled land that is empty, nobody's, clean and far from any government."""
    H, O = world.H, world.O
    gov = np.zeros(len(world.civs), dtype=bool)
    for o in world.civs:
        gov[o.id] = bool(o.id and o.ai and not o.collapsed)
    governed = gov[O] & (H > 10)
    ok = ((O == 0) & (H <= 10) & (world.H0 >= SETTLE_HOME_MIN) & world.land & (world.T != 5)
          & (world.Z == 0) & (world.zombie_near(SETTLE_SAFE) <= SETTLE_SAFE_Z)
          & (world.zombie_near(SETTLE_CLEAR) <= SETTLE_CLEAR_Z)
          & (box_sum((O == 0) & (world.H0 >= SETTLE_HOME_MIN) & world.land, ROOM_REACH) >= COLONY_ROOM)
          & (box_sum(governed, SETTLE_APART) == 0))
    import nukes
    poisoned = nukes.poisoned(world)
    if poisoned is not None:
        ok &= ~poisoned
    return ok


def _scale(world):
    meta = getattr(world, "meta", None) or {}
    return float(meta.get("settle_scale", 1.0))


def _gap(world, rr, cc, colonies):
    """Tiles (/ settle_scale) from each place (rr, cc) to the nearest of the standing colonies (inf if none); a young colony (founded
    within SETTLE_QUIET days) counts as on top of anything within SETTLE_SPREAD of it."""
    d = np.full(rr.size, np.inf)
    k_ = _scale(world)
    for r, k, young in colonies:
        dc = np.abs(cc - k)
        if world.wrap:
            dc = np.minimum(dc, world.cols - dc)
        g = np.hypot(rr - r, dc) / k_                    # (in units of the standard spacing)
        if young:
            g = np.where(g < SETTLE_SPREAD, 0.0, g)
        d = np.minimum(d, g)
    return d


def _target(world, c, cand, colonies=()):
    """The place its settlers head for: over land, or by sea from its ports - old big towns first, away from the
    other settlers' colonies."""
    S = world.statics
    rr, cc = np.nonzero(cand)
    home = (world.O0[rr, cc] == c.id) | (world.O0[rr, cc] == c.root)     # (not on its own country's old land: that
    rr, cc = rr[~home], cc[~home]                                         #  it resettles itself - settlers go abroad)
    if rr.size == 0:
        return None
    gap = _gap(world, rr, cc, colonies)
    far = gap >= SETTLE_SPACING
    rr, cc, gap = rr[far], cc[far], gap[far]
    if rr.size == 0:
        return None
    r0, c0 = c.capital
    dc = np.abs(cc - c0)
    if world.wrap:
        dc = np.minimum(dc, world.cols - dc)
    res = float(world.meta.get("res", 0.5)) if hasattr(world, "meta") else 0.5
    land_t, sea_t = SETTLE_LAND_REACH / res, int(SETTLE_SEA_REACH / res)
    by_land = (S.landmass[rr, cc] == S.landmass[r0, c0]) & (np.hypot(rr - r0, dc) <= land_t)
    reach = by_land.copy()
    if c.ports > 0:
        import expeditions                              # (open land - an emptied continent - draws ships from afar)
        opened = expeditions.open_land(world)[rr, cc]
        far_t = int(expeditions.OPEN_REACH / res) if opened.any() else sea_t
        sea = expeditions.sea_steps_cached(world, c, far_t)[rr, cc]
        reach |= (sea <= sea_t) | (opened & (sea <= far_t))
    if not reach.any():
        return None
    rr, cc, gap = rr[reach], cc[reach], gap[reach]
    w = world.H0[rr, cc].astype(np.float64) ** 1.5
    w *= np.clip((gap - SETTLE_SPACING) / (SETTLE_SPREAD - SETTLE_SPACING), 0.05, 1.0)
    j = int(world.rng.choice(rr.size, p=w / w.sum())) if world.stochastic else int(np.argmax(w))
    return int(rr[j]), int(cc[j])


def found(world, parent, r, c):
    """`parent`'s settlers found a new state around (r, c)."""
    import economy
    import expeditions
    if not expeditions.draw_from_home(world, parent, SETTLE_GROUP):
        return None
    civ = world.add_civ(morale=8)
    if civ is None:
        return None
    H, O = world.H, world.O
    region = np.zeros(H.shape, dtype=bool)                # the settlement and its fields: a round patch of tiles,
    for dr, dc in [(a, b) for a in range(-2, 3) for b in range(-2, 3) if abs(a) + abs(b) <= 2]:   # each lived on
        rr, cc = r + dr, c + dc
        if 0 <= rr < H.shape[0] and 0 <= cc < H.shape[1] and world.land[rr, cc] and O[rr, cc] == 0 and world.T[rr, cc] != 5:
            region[rr, cc] = True
    region[r, c] = True
    tiles = [tuple(x) for x in np.argwhere(region) if tuple(x) != (r, c)]
    each = min(20, (SETTLE_GROUP - 30) // max(1, len(tiles)))
    for rr, cc in tiles:
        H[rr, cc] = min(255, H[rr, cc] + each)
    H[r, c] = min(255, H[r, c] + SETTLE_GROUP - each * len(tiles))
    O[region] = civ.id
    world.last_owner[region] = civ.id
    parent.materials -= SETTLE_COST
    civ.successor, civ.founded, civ.split_from = True, world.ticks, parent.id
    civ.root = civ.id                                   # (a country of their own, not a province of the old one)
    civ.gov = govern.choose(world, region, parent)
    civ.capital = (r, c)
    civ.name = govern.state_name(world, civ.gov, region, civ.id, parent, near=(r, c))
    civ.military = max(parent.military * 0.5, COLONY_ARMY)
    civ.strength = max(parent.strength * 0.8, 0.4)
    civ.materials = SETTLE_COST * 3
    civ.food = SETTLE_GROUP * economy.FOOD_PER_PERSON * COLONY_FOOD
    civ.colony_until = world.ticks + COLONY_GRACE
    from civilization import within                     # (room to grow: the land around it is its to settle)
    near = np.zeros(H.shape, dtype=bool)
    near[r, c] = True
    keep = within(world, near, COLONY_RESERVE, through=world.land) & (O == 0) & world.land
    res = world.__dict__.get("colony_reserve")
    if res is None or res.shape != H.shape:
        res = world.colony_reserve = np.zeros(H.shape, dtype=np.int32)
    res[keep & (res == 0)] = civ.id
    world.__dict__.setdefault("reserve_until", {})[civ.id] = world.ticks + RESERVE_DAYS
    civ.peak_pop = float(SETTLE_GROUP)
    site = dict(center=(r, c), tiles=[(r, c)], level=COLONY_FORT, target=COLONY_FORT)   # (its stockade)
    world.D[r, c] = max(int(world.D[r, c]), COLONY_FORT)
    civ.sites.append(site)
    import aid                                          # (the old country sees it through its first months)
    if parent.military >= 0.25 and parent.materials >= 20:
        missions = world.__dict__.setdefault("missions", [])
        world.__dict__.setdefault("un", dict(missions=0, food=0.0))
        missions.append(dict(donor=parent.id, to=civ.id, until=world.ticks + COLONY_GRACE))
    civ.traits.update({k: v for k, v in parent.traits.items() if k in ("caution", "aggression")})
    world.last_settlers = getattr(world, "last_settlers", 0) + SETTLE_GROUP
    world.note(f"settlers from {parent.name} found {civ.name}")
    return civ
