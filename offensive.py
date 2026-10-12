"""The staged offensive: how a nation that has run out of safe land takes back infested land.

It switches on (activity OFFENSIVE, see Civilization.score) once a nation has stopped growing into clean
territory, has a real army and isn't in danger itself.  Then, over and over:

  Stage 1  BASE      pick a strategic spot in infested ground a few tiles beyond its border (mountains, cities and
                     narrow passes are favoured, over-large hordes are avoided), garrison it with troops drawn from
                     its own land, clear the zombies at the spot, and turn it into a heavily fortified strongpoint.
  Stage 2  ERADICATE every few ticks the garrison sorties: a big share of ALL zombies within BASE_RADIUS of the base
                     is destroyed (much harder than the thin border sweeps of RECLAIM; costs materials and army).
  Stage 3  RETAKE    ground that has been cleared is settled from the inside out - people moved in from the nation's
                     land, claimed, given defense - so the border really advances.  When the zone is held the
                     base becomes an ordinary fortified site and the nation looks for the next base further out.

The zone around a base is a rough circle, not a square: how far it reaches in each direction depends on the terrain
(mountains, forest and desert are harder to hold, ice and water not at all) and on a per-base random field, so the
reclaimed land comes out patchy.  Settlers go first where the going is easy and no zombies are left close by.

All of it costs materials, people and army strength, so a poor or tired nation advances slowly or stalls; and a base
is a fortified site like any other: it counts against how many sites the nation can keep up (max_sites) and costs
upkeep every tick (economy.upkeep).
"""
import numpy as np

from terrain import is_land, is_water

from civilization import box_sum, world_corridor, DIRECTIONS

BASE_CHECK_EVERY = 20
BASES_MAX = 3
BASE_MIN_REACH = 3          # a base is at least this far beyond the border ... (tiles)
BASE_MAX_REACH = 11         # ... and at most this far
BASE_SPACING = 9
BASE_RADIUS = 7             # the sortie / retake zone around a base (rough circle, see _zone_mask)
ZONE_NOISE = 0.45           # how ragged the zone is: its reach varies by +-this share of BASE_RADIUS
TERRAIN_REACH = {2: 1.5, 3: 3.0, 4: 1.5, 5: 99.0, 9: 1.0, 10: 1.5, 11: 2.5, 12: 2.0}   # forest, mountain, desert, ice,
                                                    # highlands, tundra, wetlands, rainforest: tiles of reach lost
SETTLE_TERRAIN = {1: 0.0, 2: 1.0, 3: 3.0, 4: 1.5, 6: -0.5, 7: -0.3, 9: 1.0, 10: 2.0, 11: 2.5, 12: 2.0}   # settling cost
                                                                    # by terrain (cities first)
SETTLE_NOISE = 2.0          # random part of the settling order (patchiness)
SETTLE_NEAR_Z = 25          # don't settle a tile with this many zombies within 2 tiles yet
BASE_COST = 30.0            # materials to build one
BASE_GARRISON = 70          # people stationed there (50+ are needed to man a defense-7 site)
BASE_LEVEL = 7
BASE_MAX_HORDE = 2500       # don't plant a base where this many zombies are within 4 tiles
BASE_COOLDOWN = 25          # ticks between founding bases
BASE_TIMEOUT = 320          # a base that hasn't finished its advance in this long is abandoned
EVERY = 4                   # ticks between sorties / retake steps
SORTIE_KILL = 0.45          # base share of zombies destroyed per sortie (+0.45 x army strength)
SORTIE_COST = 0.0025        # materials per zombie
SORTIE_ARMY = 0.0015        # army strength lost per sortie (+ per kill below)
SORTIE_ARMY_KILL = 0.00002
CLEAR_AT = 40               # zombies left in the zone below which it counts as cleared
RETAKE_TILES = 10           # tiles settled per step
RETAKE_PEOPLE = 16          # people moved into each retaken tile
RETAKE_COST = 1.2           # materials per retaken tile
RETAKE_DEFENSE = 5
KEEP_BEHIND = 30            # people always left on the tiles settlers are drawn from
STALL_SAMPLES = 4           # tile counts (10 ticks apart) that must be flat for the nation to count as stalled
STALL_TOLERANCE = 0.03
OFFENSIVE_ARMY = 0.5        # army strength needed to launch
OFFENSIVE_POP = 800
OFFENSIVE_MIN_MATERIALS = BASE_COST + 15


def stalled(civ):
    """The nation has stopped expanding into clean land (its tile count has been flat for a while)."""
    h = civ.tile_hist
    if len(h) < STALL_SAMPLES:
        return False
    recent = list(h)[-STALL_SAMPLES:]
    return max(recent) - min(recent) <= max(2, STALL_TOLERANCE * max(recent))


def ready(civ, world, danger):
    """Can this nation start (or keep up) an offensive right now?"""
    import war
    if world is None:
        return False
    return (civ.military >= OFFENSIVE_ARMY and civ.materials >= OFFENSIVE_MIN_MATERIALS and not civ.famine
            and civ.m.get("pop", 0) >= OFFENSIVE_POP and danger < 0.35 and not war.at_war(world, civ.id)
            and civ.m.get("hordes", 0) > 0 and (civ.bases or (stalled(civ) and _has_target(civ, world))))


def _has_target(civ, world):
    """Is there anywhere worth planting a base?  (cached for CHECK_EVERY ticks - the search is not free)"""
    t, ok = civ.base_check
    if world.ticks - t >= BASE_CHECK_EVERY or t < 0:
        ok = _choose_base(civ, world) is not None
        civ.base_check = (world.ticks, ok)
    return ok


def _draw_people(world, civ, r, c, n, reach=60):
    """Take n people out of the nation's land (leaving KEEP_BEHIND on each tile), nearest tiles to (r, c) first -
    settlers come from wherever the nation has people to spare, not only from the border.  False if it can't."""
    H = world.H
    r0, r1, c0, c1 = max(r - reach, 0), r + reach + 1, max(c - reach, 0), c + reach + 1
    sub = np.where(world.O[r0:r1, c0:c1] == civ.id, H[r0:r1, c0:c1] - KEEP_BEHIND, 0)
    spare = np.argwhere(sub > 0)
    if spare.size == 0 or sub[sub > 0].sum() < n:
        return False
    dist = np.maximum(abs(spare[:, 0] + r0 - r), abs(spare[:, 1] + c0 - c))
    need = n
    for k in np.argsort(dist, kind="stable"):
        if need <= 0:
            break
        rr, cc = int(spare[k, 0]), int(spare[k, 1])
        take = int(min(sub[rr, cc], need))
        H[r0 + rr, c0 + cc] -= take
        need -= take
    return True


def _choose_base(civ, world):
    from civilization import window
    win = window(world, civ.id, BASE_MAX_REACH + 1)
    r_off, c_off = win[0].start or 0, win[1].start or 0
    H, Z, T, O = world.H[win], world.Z[win], world.T[win], world.O[win]
    owned = (O == civ.id) & (H > 10)
    if not owned.any():
        return None
    ring = (box_sum(owned, BASE_MAX_REACH) > 0) & (box_sum(owned, BASE_MIN_REACH - 1) == 0)
    near4 = world.zombie_near(4)[win]
    elig = ring & is_land(T) & (T != 5) & (O == 0) & (Z >= 2) & (near4 <= BASE_MAX_HORDE)
    # only over land: the army marches out from its own land, it doesn't hop across the sea to another island or
    # continent (that was how the Dominican Republic ended up conquering North America)
    mass = world.statics.landmass[win]
    elig &= np.isin(mass, np.unique(mass[owned])) & world.may_claim(civ.id)[win]
    sites = [b["center"] for b in civ.bases] + [s["center"] for s in civ.sites]
    if sites:
        marks = np.zeros(world.H.shape, dtype=bool)
        for rc in sites:
            marks[rc] = True
        elig &= box_sum(marks[win], BASE_SPACING - 1) == 0
    if not elig.any():
        return None
    passable = is_land(T) & (T != 3)
    width = world_corridor(world)[win]
    choke = np.where(passable & (width <= 10), (11 - width) / 10.0, 0.0)
    dist = np.zeros(H.shape)
    for k in range(BASE_MIN_REACH, BASE_MAX_REACH + 1):          # nearer to our own land is easier to supply
        dist += (box_sum(owned, k) == 0)
    value = (1.5 * (T == 3) + 1.0 * (T == 6) + 0.5 * (T == 7) + 1.0 * choke
             + 0.8 * np.clip(world.zombie_near(BASE_RADIUS)[win] / 2000.0, 0, 1) - 0.08 * dist)
    value = np.where(elig, value + 2.0, -np.inf)
    value = value + np.where(elig, world.rng.random(H.shape) * (0.4 if world.stochastic else 0.0), 0)
    r, c = np.unravel_index(int(np.argmax(value)), value.shape)
    return int(r) + r_off, int(c) + c_off


def _found_base(civ, world):
    if len(civ.sites) >= civ.max_sites():
        return False                                    # can't man / supply another strongpoint
    pick = _choose_base(civ, world)
    if pick is None:
        return False
    r, c = pick
    if not _draw_people(world, civ, r, c, BASE_GARRISON):
        return False
    civ.materials -= BASE_COST
    H, Z, D, O, T = world.H, world.Z, world.D, world.O, world.T
    # the spot itself is cleared, taken and fortified; the troops on it hold it
    Z[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2] = 0
    O[r, c] = civ.id
    H[r, c] = BASE_GARRISON
    D[r, c] = BASE_LEVEL
    site = dict(center=(r, c), tiles=[(r, c)], level=BASE_LEVEL, target=BASE_LEVEL, base=True)
    civ.sites.append(site)
    civ.bases.append(dict(center=(r, c), born=world.ticks, site=site, cleared=False,
                          zone=_zone_mask(world, r, c), order=_settle_noise(world, r, c)))
    world.note(f"{civ.name} plants a fortified base at ({r},{c})")
    return True


def _zone(world, r, c):
    r0, r1, c0, c1 = max(r - BASE_RADIUS, 0), r + BASE_RADIUS + 1, max(c - BASE_RADIUS, 0), c + BASE_RADIUS + 1
    return r0, min(r1, world.rows), c0, min(c1, world.cols)


def _field(world, shape, cells=3):
    """A smooth random field in [0, 1] over `shape` (bilinear between a few random values)."""
    if not world.stochastic:
        return np.full(shape, 0.5)
    g = world.rng.random((cells + 1, cells + 1))
    ys = np.linspace(0, cells, shape[0]) if shape[0] > 1 else np.zeros(1)
    xs = np.linspace(0, cells, shape[1]) if shape[1] > 1 else np.zeros(1)
    y0 = np.minimum(ys.astype(int), cells - 1)
    x0 = np.minimum(xs.astype(int), cells - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    a, b = g[y0][:, x0], g[y0][:, x0 + 1]
    c, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
    return a * (1 - fy) * (1 - fx) + b * (1 - fy) * fx + c * fy * (1 - fx) + d * fy * fx


def _zone_mask(world, r, c):
    """The ground a base tries to clear and hold: a ragged circle shaped by terrain."""
    r0, r1, c0, c1 = _zone(world, r, c)
    rr, cc = np.mgrid[r0:r1, c0:c1]
    dist = np.hypot(rr - r, cc - c)
    reach = BASE_RADIUS * (1.0 + ZONE_NOISE * (2 * _field(world, dist.shape) - 1))
    T = world.T[r0:r1, c0:c1]
    for t, lost in TERRAIN_REACH.items():
        reach = np.where(T == t, reach - lost, reach)
    return (dist <= reach) & is_land(T)


def _settle_noise(world, r, c):
    r0, r1, c0, c1 = _zone(world, r, c)
    return SETTLE_NOISE * _field(world, (r1 - r0, c1 - c0), cells=4)


def _sortie(civ, world, b):
    r, c = b["center"]
    r0, r1, c0, c1 = _zone(world, r, c)
    Z = world.Z[r0:r1, c0:c1]
    zone = b.get("zone")
    zone = np.ones(Z.shape, dtype=bool) if zone is None or zone.shape != Z.shape else zone
    total = int(Z[zone].sum())
    if total <= 0 or civ.materials < 1.0:
        return 0
    share = min(0.95, (SORTIE_KILL + 0.45 * civ.military) * world.jitter(0.2))
    kills = np.where(zone, np.minimum(np.ceil(Z * share).astype(np.int32), Z), 0).astype(np.int32)
    cost = float(kills.sum()) * SORTIE_COST
    if cost > civ.materials:
        kills = (kills * (civ.materials / cost)).astype(np.int32)
        cost = float(kills.sum()) * SORTIE_COST
    civ.materials -= cost
    Z -= kills
    n = int(kills.sum())
    civ.kills += n
    civ.military = max(0.0, civ.military - SORTIE_ARMY - n * SORTIE_ARMY_KILL)
    return n


def _retake(civ, world, b):
    """Settle cleared tiles inside the zone, nearest the base first."""
    H, Z, O, D, T = world.H, world.Z, world.O, world.D, world.T
    r, c = b["center"]
    r0, r1, c0, c1 = _zone(world, r, c)
    zone = b.get("zone")
    Tz = T[r0:r1, c0:c1]
    land = is_land(Tz) & (Tz != 5)
    if zone is not None and zone.shape == land.shape:
        land &= zone
    held = land & (O[r0:r1, c0:c1] == civ.id)
    near2 = world.zombie_near(2)[r0:r1, c0:c1]
    free = land & (Z[r0:r1, c0:c1] == 0) & (O[r0:r1, c0:c1] == 0) & (near2 < SETTLE_NEAR_Z)
    # only settle ground that touches ground we already hold (the base first, then outwards)
    pad = box_sum(O[r0:r1, c0:c1] == civ.id, 1) > 0
    cand = np.argwhere(free & pad)
    if cand.size == 0:
        return 0, int(((land & ~held).sum())), not (land & ~held & (Z[r0:r1, c0:c1] == 0)).any()
    d = np.hypot(cand[:, 0] + r0 - r, cand[:, 1] + c0 - c)
    cost = d + np.array([SETTLE_TERRAIN.get(int(t), 1.0) for t in Tz[cand[:, 0], cand[:, 1]]])
    cost += near2[cand[:, 0], cand[:, 1]] / 10.0
    noise = b.get("order")
    if noise is not None and noise.shape == Tz.shape:
        cost += noise[cand[:, 0], cand[:, 1]]
    order = np.argsort(cost, kind="stable")[:RETAKE_TILES]
    done = 0
    for k in order:
        rr, cc = int(cand[k, 0] + r0), int(cand[k, 1] + c0)
        if b.get("overseas"):                           # (settlers for an overseas landing come by ship)
            import expeditions
            drawn = expeditions.draw_from_home(world, civ, RETAKE_PEOPLE)
        else:
            drawn = _draw_people(world, civ, rr, cc, RETAKE_PEOPLE)
        if civ.materials < RETAKE_COST or not drawn:
            break
        civ.materials -= RETAKE_COST
        H[rr, cc] += RETAKE_PEOPLE
        O[rr, cc] = civ.id
        D[rr, cc] = max(D[rr, cc], RETAKE_DEFENSE)
        done += 1
    remaining = int(((land & ~held).sum())) - done
    return done, remaining, False


def step(civ, world, active=True):
    """One tick of the offensive (called from Civilization.act).  With active=False (the nation has pulled back
    because it is in danger itself) only the housekeeping runs: lost or timed-out bases are dropped."""
    if world.ticks % EVERY:
        return
    # drop bases that were lost or took far too long
    live = []
    for b in civ.bases:
        r, c = b["center"]
        if b["site"] not in civ.sites or world.O[r, c] != civ.id:
            world.note(f"{civ.name} loses its base at ({r},{c})")
            continue
        if world.ticks - b["born"] > BASE_TIMEOUT:
            world.note(f"{civ.name} abandons its base at ({r},{c}) (no progress)")
            continue
        live.append(b)
    civ.bases = live
    if not active and not any(b.get("overseas") for b in civ.bases):
        return
    for b in list(civ.bases):
        if not active and not b.get("overseas"):
            continue                                    # (an expedition overseas carries on regardless)
        r, c = b["center"]
        if world.H[r, c] < BASE_GARRISON - 10 and civ.materials >= 2.0:       # resupply the garrison
            world.H[r, c] = min(BASE_GARRISON, world.H[r, c] + 10)
            civ.materials -= 1.0
        left = _sortie(civ, world, b)
        r0, r1, c0, c1 = _zone(world, r, c)
        zone = b.get("zone")
        zz = world.Z[r0:r1, c0:c1]
        if int((zz[zone] if zone is not None and zone.shape == zz.shape else zz).sum()) <= CLEAR_AT:
            b["cleared"] = True
        if b["cleared"]:
            _, remaining, nothing_left = _retake(civ, world, b)
            zone_land = int(b["zone"].sum()) if b.get("zone") is not None else int(
                (is_land(world.T[r0:r1, c0:c1]) & (world.T[r0:r1, c0:c1] != 5)).sum())
            if remaining <= max(2, 0.15 * zone_land) or nothing_left:
                civ.advances += 1
                civ.bases.remove(b)
                world.note(f"{civ.name} completes an advance around ({r},{c}) - {civ.advances} so far")
    if not active:
        return
    if (len(civ.bases) < BASES_MAX and world.ticks >= civ.next_base and civ.materials >= OFFENSIVE_MIN_MATERIALS
            and not any(not b["cleared"] for b in civ.bases)):
        civ.next_base = world.ticks + BASE_COOLDOWN
        _found_base(civ, world)
